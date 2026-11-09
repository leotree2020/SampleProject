"""逐日历史模拟（point-in-time）：检验「如果当时就用这个工具，结果会怎样」。

与 analysis.analyze 中基于全部历史的回测不同，这里严格模拟实盘：
- 每隔 ``refit_every`` 根K线重新训练一次模型，只使用当天收盘前已经知道结果的样本
- 模型是否「有预测力」也只用当时可得的数据做滚动验证来判断
- 每天收盘按工具的综合结论决定方向，按工具给出的风控方案（ATR 止损止盈、
  1% 风险仓位）下单，盘中触及止损/止盈即按该价位成交
- 同时记录工具对未来 ``horizon`` 根K线的价格预测，用于和实际价格对比
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from . import indicators as ind
from . import models
from .backtest import performance, run_backtest
from .data import FOREX
from .features import build_features, make_dataset
from .risk import RiskConfig, default_lot_size, default_max_leverage
from .signals import technical_score_series


@dataclass
class SimConfig:
    start: str
    end: str
    capital: float = 5000.0          # 账户资金（账户货币）
    fx_rate: float = 1.0             # 1 单位账户货币可兑换多少标的计价货币（如 USD→CNY 约 6.4）
    horizon: int = 5
    model: str = models.ENSEMBLE
    n_splits: int = 5
    refit_every: int = 21            # 约每月重新训练一次
    allow_short: Optional[bool] = None
    cost_bps: Optional[float] = None
    direction_threshold: float = 10.0  # 与 analysis 中给出开仓方向的阈值一致
    risk: RiskConfig = field(default_factory=RiskConfig)


@dataclass
class SimulationResult:
    symbol: str
    asset_type: str
    cfg: SimConfig
    daily: pd.DataFrame       # 每日：价格、信号、仓位、三种资金曲线
    forecast: pd.DataFrame    # 按目标日期：预测价格、90% 区间、实际价格
    trades: pd.DataFrame      # 逐笔交易
    metrics: Dict[str, Dict[str, float]]


def point_in_time_signals(df: pd.DataFrame, cfg: SimConfig, allow_short: bool) -> pd.DataFrame:
    """逐日生成工具当时会给出的信号（不使用任何未来数据）。"""
    test_dates = df.index[(df.index >= pd.Timestamp(cfg.start)) & (df.index <= pd.Timestamp(cfg.end))]
    if len(test_dates) == 0:
        raise ValueError("模拟区间内没有数据")

    feats = build_features(df)
    first_valid = feats.dropna().index.min()
    feats = feats.loc[first_valid:].ffill()
    if test_dates[0] <= first_valid:
        raise ValueError("模拟开始日期之前的历史数据不足，请提供更早的数据")

    tech = technical_score_series(df)
    logret = np.log(df["close"]).diff()
    sigma = logret.rolling(60).std()

    rows: List[dict] = []
    for i in range(0, len(test_dates), cfg.refit_every):
        chunk = test_dates[i : i + cfg.refit_every]
        refit_pos = df.index.get_loc(chunk[0])
        # 只用截至重训当天收盘已知的数据：最后一个标签的目标日 <= 当天
        ds = make_dataset(df.iloc[: refit_pos + 1], cfg.horizon)
        val = models.walk_forward(ds, cfg.model, cfg.n_splits)
        proba = models.fit_predict(cfg.model, ds.X, ds.y, feats.loc[chunk])
        typical_move = float(ds.fwd_ret.iloc[-500:].abs().mean())
        for d, p in zip(chunk, proba):
            rows.append(
                {
                    "date": d,
                    "proba_up": float(p),
                    "has_edge": val.has_edge,
                    "val_auc": val.auc,
                    "typical_move": typical_move,
                }
            )

    sig = pd.DataFrame(rows).set_index("date")
    sig["tech_score"] = tech.reindex(sig.index)
    w_ml = np.where(sig["has_edge"], 0.5, 0.2)
    ml_score = (sig["proba_up"] - 0.5) * 200
    sig["combined"] = (1 - w_ml) * sig["tech_score"].fillna(0) + w_ml * ml_score
    th = cfg.direction_threshold
    direction = np.where(sig["combined"] >= th, 1, np.where((sig["combined"] <= -th) & allow_short, -1, 0))
    sig["direction"] = direction.astype(int)

    close = df["close"].reindex(sig.index)
    sig["pred_return"] = (2 * sig["proba_up"] - 1) * sig["typical_move"]
    sig["pred_price"] = close * (1 + sig["pred_return"])
    band = 1.645 * sigma.reindex(sig.index) * np.sqrt(cfg.horizon)
    sig["band_low"] = close * np.exp(-band)
    sig["band_high"] = close * np.exp(band)
    return sig


def _forecast_table(df: pd.DataFrame, sig: pd.DataFrame, horizon: int) -> pd.DataFrame:
    """把「t 日对 t+h 日的预测」挪到目标日期，与实际价格对齐。"""
    pos = df.index.get_indexer(sig.index) + horizon
    ok = pos < len(df)
    target = df.index[pos[ok]]
    out = pd.DataFrame(
        {
            "origin": sig.index[ok],
            "origin_close": df["close"].reindex(sig.index[ok]).to_numpy(),
            "pred_price": sig["pred_price"].to_numpy()[ok],
            "band_low": sig["band_low"].to_numpy()[ok],
            "band_high": sig["band_high"].to_numpy()[ok],
            "proba_up": sig["proba_up"].to_numpy()[ok],
            "actual": df["close"].iloc[pos[ok]].to_numpy(),
        },
        index=target,
    )
    out.index.name = "target_date"
    return out


def _simulate_risk_plan(
    df: pd.DataFrame, sig: pd.DataFrame, cfg: SimConfig, symbol: str, asset_type: str, cost_bps: float
) -> tuple[pd.Series, pd.Series, pd.DataFrame]:
    """按工具风控方案逐笔交易：收盘开仓，盘中触及止损/止盈成交，信号改变则收盘平仓。"""
    atr = ind.atr(df["high"], df["low"], df["close"]).reindex(sig.index)
    data = df.reindex(sig.index)
    rc = cfg.risk
    lot = rc.lot_size or default_lot_size(symbol, asset_type)
    max_lev = rc.max_leverage or default_max_leverage(asset_type)
    cost = cost_bps / 1e4

    realized = cfg.capital * cfg.fx_rate  # 以标的计价货币记账
    side, units, entry, stop, target, entry_date = 0, 0.0, 0.0, 0.0, 0.0, None
    equity, held, trades = [], [], []

    def close_pos(price: float, date, reason: str) -> None:
        nonlocal realized, side, units
        pnl = side * units * (price - entry) - units * price * cost
        realized += pnl
        trades.append(
            {
                "开仓日": entry_date, "平仓日": date, "方向": "做多" if side > 0 else "做空",
                "数量": units, "开仓价": entry, "平仓价": price,
                "盈亏": (pnl - units * entry * cost) / cfg.fx_rate,  # 含开平仓成本，换算为账户货币
                "平仓原因": reason,
            }
        )
        side, units = 0, 0.0

    dates = list(sig.index)
    for k, d in enumerate(dates):
        o, h, l, c = data.loc[d, ["open", "high", "low", "close"]]
        # 1) 盘中先检查止损（保守：同日同时触及时按止损处理），再检查止盈
        if side != 0 and k > 0:
            if side > 0:
                if o <= stop:
                    close_pos(o, d, "止损(跳空)")
                elif l <= stop:
                    close_pos(stop, d, "止损")
                elif o >= target:
                    close_pos(o, d, "止盈(跳空)")
                elif h >= target:
                    close_pos(target, d, "止盈")
            else:
                if o >= stop:
                    close_pos(o, d, "止损(跳空)")
                elif h >= stop:
                    close_pos(stop, d, "止损")
                elif o <= target:
                    close_pos(o, d, "止盈(跳空)")
                elif l <= target:
                    close_pos(target, d, "止盈")

        want = int(sig.loc[d, "direction"])
        last_day = k == len(dates) - 1
        # 2) 收盘：信号改变或模拟结束则平仓
        if side != 0 and (want != side or last_day):
            close_pos(c, d, "模拟结束" if last_day and want == side else "信号改变")
        # 3) 收盘：按风控方案开新仓
        a = atr.loc[d]
        if side == 0 and want != 0 and not last_day and np.isfinite(a) and a > 0:
            stop_dist = a * rc.atr_stop_mult
            q = realized * rc.risk_pct / stop_dist
            q = min(q, realized * max_lev / c)
            q = np.floor(q / lot) * lot
            if q > 0:
                side, units, entry, entry_date = want, float(q), float(c), d
                stop = c - want * stop_dist
                target = c + want * stop_dist * rc.reward_risk
                realized -= units * c * cost

        mtm = realized + (side * units * (c - entry) if side else 0.0)
        equity.append(mtm / cfg.fx_rate)
        held.append(side * units)

    return (
        pd.Series(equity, index=sig.index, name="equity_risk"),
        pd.Series(held, index=sig.index, name="units"),
        pd.DataFrame(trades),
    )


def _trade_stats(trades: pd.DataFrame) -> Dict[str, float]:
    if trades.empty:
        return {"trades": 0, "trade_win_rate": float("nan"), "stops": 0, "targets": 0}
    return {
        "trades": int(len(trades)),
        "trade_win_rate": float((trades["盈亏"] > 0).mean()),
        "stops": int(trades["平仓原因"].str.startswith("止损").sum()),
        "targets": int(trades["平仓原因"].str.startswith("止盈").sum()),
    }


def simulate(df: pd.DataFrame, symbol: str, asset_type: str, cfg: SimConfig) -> SimulationResult:
    allow_short = cfg.allow_short if cfg.allow_short is not None else asset_type == FOREX
    cost_bps = cfg.cost_bps if cfg.cost_bps is not None else (2.0 if asset_type == FOREX else 10.0)
    ppy = 260 if asset_type == FOREX else 252

    sig = point_in_time_signals(df, cfg, allow_short)
    close = df["close"].reindex(sig.index)

    eq_risk, units, trades = _simulate_risk_plan(df, sig, cfg, symbol, asset_type, cost_bps)
    full = run_backtest(close, sig["direction"].astype(float), cost_bps, ppy)
    eq_full = full.equity * cfg.capital
    eq_bh = cfg.capital * close / close.iloc[0] * (1 - cost_bps / 1e4)

    daily = pd.DataFrame(
        {
            "close": close,
            "tech_score": sig["tech_score"],
            "proba_up": sig["proba_up"],
            "has_edge": sig["has_edge"],
            "combined": sig["combined"],
            "direction": sig["direction"],
            "units": units,
            "equity_risk": eq_risk,
            "equity_full": eq_full,
            "equity_bh": eq_bh,
        }
    )
    fc = _forecast_table(df, sig, cfg.horizon)

    # ---------- 指标 ----------
    def eq_metrics(eq: pd.Series) -> Dict[str, float]:
        m = performance(eq.pct_change().fillna(0), ppy)
        m["final_equity"] = float(eq.iloc[-1])
        m["pnl"] = float(eq.iloc[-1] - cfg.capital)
        return m

    risk_m = eq_metrics(eq_risk)
    risk_m.update(_trade_stats(trades))
    risk_m["exposure"] = float((units != 0).mean())
    full_m = eq_metrics(eq_full)
    full_m["exposure"] = float((sig["direction"] != 0).mean())
    bh_m = eq_metrics(eq_bh)

    up = (fc["actual"] > fc["origin_close"]).astype(int)
    pred_up = (fc["proba_up"] >= 0.5).astype(int)
    from sklearn.metrics import roc_auc_score

    forecast_m = {
        "n": int(len(fc)),
        "direction_hit_rate": float((up == pred_up).mean()),
        "actual_up_rate": float(up.mean()),
        "naive_hit_rate": float(max(up.mean(), 1 - up.mean())),  # 事后看总猜多数方向能达到的命中率
        "auc": float(roc_auc_score(up, fc["proba_up"])) if up.nunique() > 1 else float("nan"),
        "mae_model": float((fc["pred_price"] - fc["actual"]).abs().mean()),
        "mae_naive": float((fc["origin_close"] - fc["actual"]).abs().mean()),
        "band_coverage": float(((fc["actual"] >= fc["band_low"]) & (fc["actual"] <= fc["band_high"])).mean()),
        "edge_share": float(sig["has_edge"].mean()),
    }

    return SimulationResult(
        symbol=symbol,
        asset_type=asset_type,
        cfg=cfg,
        daily=daily,
        forecast=fc,
        trades=trades,
        metrics={"risk_plan": risk_m, "full_position": full_m, "buy_hold": bh_m, "forecast": forecast_m},
    )
