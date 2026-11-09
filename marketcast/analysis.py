"""分析总入口：把技术面、机器学习、回测与风控整合成一份结论。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from . import models
from .backtest import BacktestResult, run_backtest, score_to_position
from .data import FOREX, data_quality_warnings
from .features import make_dataset
from .risk import RiskConfig, RiskPlan, build_risk_plan
from .signals import SignalItem, technical_view

DISCLAIMER = "本系统输出仅为基于历史数据的统计分析，不构成任何投资建议。市场有风险，投资需谨慎。"


@dataclass
class AnalysisConfig:
    horizon: int = 5                 # 预测未来多少根K线
    model: str = models.ENSEMBLE
    n_splits: int = 5
    allow_short: Optional[bool] = None   # None：外汇允许做空，股票不允许
    cost_bps: Optional[float] = None     # None：股票 10bp，外汇 2bp
    run_backtest: bool = True
    tech_entry: float = 20.0
    ml_entry: float = 0.55           # 上涨概率超过该值才开多（对称地低于 1-ml_entry 开空）
    risk: RiskConfig = field(default_factory=RiskConfig)


@dataclass
class Analysis:
    symbol: str
    asset_type: str
    as_of: pd.Timestamp
    last_close: float
    change_pct: float
    horizon: int

    tech_score: float
    tech_label: str
    tech_items: List[SignalItem]

    ml_proba_up: float
    ml_validation: models.ValidationResult
    ml_top_features: List[Tuple[str, float]]

    combined_score: float
    combined_label: str
    confidence: str
    suggestion: str

    expected_range: Tuple[float, float]   # 未来 horizon 期约 90% 概率的价格区间
    risk_plan: Optional[RiskPlan]
    backtests: Dict[str, BacktestResult]
    warnings: List[str]

    # 供画图使用
    data: pd.DataFrame = field(repr=False, default=None)
    tech_series: pd.Series = field(repr=False, default=None)


def _combined_label(score: float) -> str:
    if score >= 30:
        return "看多"
    if score >= 10:
        return "略偏多"
    if score > -10:
        return "中性 / 观望"
    if score > -30:
        return "略偏空"
    return "看空"


def analyze(
    df: pd.DataFrame,
    symbol: str,
    asset_type: str,
    cfg: AnalysisConfig | None = None,
) -> Analysis:
    cfg = cfg or AnalysisConfig()
    allow_short = cfg.allow_short if cfg.allow_short is not None else asset_type == FOREX
    cost_bps = cfg.cost_bps if cfg.cost_bps is not None else (2.0 if asset_type == FOREX else 10.0)
    warnings: List[str] = data_quality_warnings(df)

    # ---------- 技术面 ----------
    tv = technical_view(df)
    data = tv.data
    last = data.iloc[-1]
    close = float(last["close"])
    change = float(close / data["close"].iloc[-2] - 1)

    # ---------- 机器学习 ----------
    ds = make_dataset(df, cfg.horizon)
    if len(ds.X) < 300:
        warnings.append(f"可用于训练的样本仅 {len(ds.X)} 条，机器学习结果稳定性较差，建议使用更长的历史数据")
    val = models.walk_forward(ds, cfg.model, cfg.n_splits)
    fc = models.predict_latest(ds, cfg.model)
    ml_score = (fc.proba_up - 0.5) * 200  # 映射到 -100~100

    # ---------- 综合 ----------
    if val.has_edge:
        w_ml = 0.5
    else:
        w_ml = 0.2
        warnings.append(
            f"模型样本外准确率 {val.accuracy:.1%}、AUC {val.auc:.3f}，未明显优于朴素基准（{val.baseline_accuracy:.1%}），"
            "机器学习信号权重已下调，仅供参考"
        )
    tech = tv.score if np.isfinite(tv.score) else 0.0
    combined = (1 - w_ml) * tech + w_ml * ml_score
    agree = np.sign(tech) == np.sign(ml_score) and abs(tech) >= 10 and abs(ml_score) >= 5
    if not agree and abs(tech) >= 15 and abs(ml_score) >= 5:
        warnings.append("技术面与机器学习方向不一致，信号可信度较低")

    if abs(combined) >= 30 and agree and val.has_edge:
        confidence = "较高"
    elif abs(combined) >= 15 and (agree or val.has_edge):
        confidence = "中等"
    else:
        confidence = "较低"

    label = _combined_label(combined)
    if combined >= 10:
        direction = "long"
        suggestion = "可考虑逢低轻仓做多，严格设置止损" if confidence != "较高" else "趋势偏多，可按计划分批建仓，严格设置止损"
    elif combined <= -10:
        if allow_short:
            direction = "short"
            suggestion = "可考虑轻仓做空，严格设置止损" if confidence != "较高" else "趋势偏空，可按计划做空，严格设置止损"
        else:
            direction = "none"
            suggestion = "偏空，持仓者可考虑减仓或设置保护性止损，空仓者暂不入场"
    else:
        direction = "none"
        suggestion = "信号不明确，建议观望"

    # ---------- 波动区间 ----------
    logret = np.log(data["close"]).diff().dropna()
    sigma = float(logret.iloc[-60:].std())
    band = 1.645 * sigma * np.sqrt(cfg.horizon)
    expected_range = (close * float(np.exp(-band)), close * float(np.exp(band)))

    # ---------- 风控 ----------
    risk_plan = build_risk_plan(symbol, asset_type, close, float(last["atr14"]), direction, cfg.risk)

    # ---------- 回测 ----------
    backtests: Dict[str, BacktestResult] = {}
    if cfg.run_backtest:
        ppy = 260 if asset_type == FOREX else 252
        tech_pos = score_to_position(tv.series, entry=cfg.tech_entry, exit=0.0, allow_short=allow_short)
        backtests["technical"] = run_backtest(data["close"], tech_pos, cost_bps, ppy)

        oof = val.oof_proba.dropna()
        if len(oof) > 20:
            ml_sig = (oof - 0.5) * 200
            ml_pos = score_to_position(ml_sig, entry=(cfg.ml_entry - 0.5) * 200, exit=0.0, allow_short=allow_short)
            # 只在样本外区间上回测，避免用训练数据评估
            close_oos = data["close"].loc[oof.index[0] :]
            backtests["ml"] = run_backtest(close_oos, ml_pos, cost_bps, ppy)

    if asset_type == FOREX:
        warnings.append("外汇杠杆交易风险极高，回测未计入隔夜利息（swap）与点差扩大")

    return Analysis(
        symbol=symbol,
        asset_type=asset_type,
        as_of=data.index[-1],
        last_close=close,
        change_pct=change,
        horizon=cfg.horizon,
        tech_score=tv.score,
        tech_label=tv.label,
        tech_items=tv.items,
        ml_proba_up=fc.proba_up,
        ml_validation=val,
        ml_top_features=fc.top_features,
        combined_score=float(combined),
        combined_label=label,
        confidence=confidence,
        suggestion=suggestion,
        expected_range=expected_range,
        risk_plan=risk_plan,
        backtests=backtests,
        warnings=warnings,
        data=data,
        tech_series=tv.series,
    )
