"""简单的向量化回测。

约定：t 日收盘根据信号确定仓位，赚取 t→t+1 的收益（即仓位整体滞后一根K线），
每次调仓按换手量扣除交易成本。这是相对乐观的近似，实盘还需考虑滑点、
涨跌停、T+1、隔夜利息（外汇 swap）等因素。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict

import numpy as np
import pandas as pd


@dataclass
class BacktestResult:
    equity: pd.Series
    benchmark: pd.Series
    position: pd.Series
    metrics: Dict[str, float]
    benchmark_metrics: Dict[str, float]


def score_to_position(
    score: pd.Series, entry: float = 20.0, exit: float = 0.0, allow_short: bool = False
) -> pd.Series:
    """带滞回的信号→仓位转换：分数超过 entry 开仓，回落到 exit 平仓。"""
    if exit > entry:
        raise ValueError("exit 不能大于 entry")
    pos = np.zeros(len(score))
    cur = 0.0
    for i, s in enumerate(score.to_numpy(dtype=float)):
        if np.isnan(s):
            cur = 0.0
        elif cur == 0:
            if s >= entry:
                cur = 1.0
            elif allow_short and s <= -entry:
                cur = -1.0
        elif cur > 0 and s < exit:
            cur = -1.0 if (allow_short and s <= -entry) else 0.0
        elif cur < 0 and s > -exit:
            cur = 1.0 if s >= entry else 0.0
        pos[i] = cur
    return pd.Series(pos, index=score.index, name="position")


def performance(returns: pd.Series, periods_per_year: int = 252, position: pd.Series | None = None) -> Dict[str, float]:
    """根据逐期收益计算常用绩效指标。"""
    returns = returns.fillna(0.0)
    n = len(returns)
    if n == 0:
        return {}
    equity = (1 + returns).cumprod()
    total = float(equity.iloc[-1] - 1)
    years = n / periods_per_year
    cagr = float(equity.iloc[-1] ** (1 / years) - 1) if years > 0 and equity.iloc[-1] > 0 else float("nan")
    vol = float(returns.std(ddof=0) * np.sqrt(periods_per_year))
    sharpe = float(returns.mean() / returns.std(ddof=0) * np.sqrt(periods_per_year)) if returns.std(ddof=0) > 0 else 0.0
    dd = equity / equity.cummax() - 1
    max_dd = float(dd.min())
    m: Dict[str, float] = {
        "total_return": total,
        "cagr": cagr,
        "annual_vol": vol,
        "sharpe": sharpe,
        "max_drawdown": max_dd,
        "calmar": float(cagr / abs(max_dd)) if max_dd < 0 and not np.isnan(cagr) else float("nan"),
    }
    if position is not None:
        held = position.reindex(returns.index).fillna(0)
        in_mkt = held != 0
        active = returns[in_mkt]
        m["exposure"] = float(in_mkt.mean())
        m["win_rate"] = float((active > 0).mean()) if len(active) else float("nan")
        m["trades"] = int(((held != held.shift(1)) & (held != 0)).sum())
    return m


def run_backtest(
    close: pd.Series,
    position: pd.Series,
    cost_bps: float = 5.0,
    periods_per_year: int = 252,
) -> BacktestResult:
    """position 取值 -1/0/1，表示 t 日收盘后的目标仓位。"""
    position = position.reindex(close.index).fillna(0.0)
    held = position.shift(1).fillna(0.0)
    ret = close.pct_change().fillna(0.0)
    turnover = held.diff().abs().fillna(held.abs())
    strat = held * ret - turnover * cost_bps / 1e4
    bench = ret.copy()
    return BacktestResult(
        equity=(1 + strat).cumprod().rename("strategy"),
        benchmark=(1 + bench).cumprod().rename("buy_and_hold"),
        position=held.rename("position"),
        metrics=performance(strat, periods_per_year, held),
        benchmark_metrics=performance(bench, periods_per_year),
    )
