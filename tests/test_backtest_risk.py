import numpy as np
import pandas as pd
import pytest

from marketcast.backtest import performance, run_backtest, score_to_position
from marketcast.risk import RiskConfig, build_risk_plan


def test_score_to_position_hysteresis():
    s = pd.Series([0, 25, 15, 5, -1, -25, -10, 30], dtype=float)
    long_only = score_to_position(s, entry=20, exit=0)
    assert long_only.tolist() == [0, 1, 1, 1, 0, 0, 0, 1]
    both = score_to_position(s, entry=20, exit=0, allow_short=True)
    assert both.tolist() == [0, 1, 1, 1, 0, -1, -1, 1]


def test_backtest_uses_next_bar_return():
    close = pd.Series([100.0, 110, 121, 121], index=pd.bdate_range("2024-01-01", periods=4))
    pos = pd.Series([1.0, 0, 0, 0], index=close.index)  # 第一天收盘买入，第二天收盘卖出
    bt = run_backtest(close, pos, cost_bps=0)
    assert bt.equity.iloc[-1] == pytest.approx(1.10)
    assert bt.benchmark.iloc[-1] == pytest.approx(1.21)


def test_backtest_costs_reduce_return():
    close = pd.Series(np.linspace(100, 120, 50), index=pd.bdate_range("2024-01-01", periods=50))
    pos = pd.Series(np.tile([1.0, 0.0], 25), index=close.index)
    free = run_backtest(close, pos, cost_bps=0).equity.iloc[-1]
    costly = run_backtest(close, pos, cost_bps=20).equity.iloc[-1]
    assert costly < free


def test_performance_drawdown():
    r = pd.Series([0.1, -0.5, 0.2])
    m = performance(r)
    assert m["max_drawdown"] == pytest.approx(-0.5)
    assert m["total_return"] == pytest.approx(1.1 * 0.5 * 1.2 - 1)


def test_risk_plan_long():
    plan = build_risk_plan("AAPL", "stock", price=100, atr=2, direction="long", cfg=RiskConfig(capital=100_000, risk_pct=0.01))
    assert plan.stop_loss == pytest.approx(96)
    assert plan.take_profit == pytest.approx(108)
    assert plan.units == 250  # 1000 / 4
    assert plan.risk_amount == pytest.approx(1000)


def test_risk_plan_short_forex_lot_and_leverage():
    plan = build_risk_plan("EURUSD=X", "forex", price=1.1, atr=0.001, direction="short", cfg=RiskConfig(capital=10_000, risk_pct=0.01))
    assert plan.stop_loss > plan.entry > plan.take_profit
    assert plan.units % 1000 == 0
    assert plan.leverage <= 10 + 1e-9  # 默认最大 10 倍


def test_risk_plan_a_share_lot():
    plan = build_risk_plan("600519.SS", "stock", price=1500, atr=30, direction="long", cfg=RiskConfig(capital=1_000_000))
    assert plan.units % 100 == 0 and plan.units > 0


def test_risk_plan_none_without_direction():
    assert build_risk_plan("AAPL", "stock", 100, 2, "none") is None
