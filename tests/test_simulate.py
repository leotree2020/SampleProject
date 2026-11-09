import numpy as np
import pandas as pd
import pytest

from marketcast.cli import main
from marketcast.data import generate_synthetic
from marketcast.sim_report import render_html, text_summary
from marketcast.simulate import SimConfig, point_in_time_signals, simulate


@pytest.fixture(scope="module")
def long_df():
    return generate_synthetic(n=1100, seed=5)


def _cfg(**kw):
    base = dict(start="2025-03-03", end="2025-09-30", model="logistic", refit_every=42, n_splits=3)
    base.update(kw)
    return SimConfig(**base)


def test_signals_do_not_use_future_data(long_df):
    cfg = _cfg()
    full = point_in_time_signals(long_df, cfg, allow_short=False)
    cut = point_in_time_signals(long_df.loc[: "2025-10-15"], cfg, allow_short=False)
    cols = ["proba_up", "tech_score", "combined", "direction", "pred_price"]
    pd.testing.assert_frame_equal(full[cols], cut[cols])


def test_simulate_stock_long_only(long_df):
    r = simulate(long_df, "TEST", "stock", _cfg())
    d = r.daily
    assert set(d["direction"].unique()) <= {0, 1}
    assert (d["units"] >= 0).all()
    assert d["equity_bh"].iloc[-1] == pytest.approx(5000 * d["close"].iloc[-1] / d["close"].iloc[0] * (1 - 0.001))
    # 风控仓位：单笔亏损不应明显超过 1% 风险预算（跳空止损除外，这里留余量）
    if not r.trades.empty:
        assert r.trades["盈亏"].min() > -5000 * 0.03
        assert (r.trades["平仓日"] >= r.trades["开仓日"]).all()
    # 预测表的目标日期在预测日之后
    assert (r.forecast.index > r.forecast["origin"]).all()
    fc = r.metrics["forecast"]
    assert 0 <= fc["direction_hit_rate"] <= 1
    assert "TEST" in text_summary(r)


def test_simulate_forex_allows_short():
    df = generate_synthetic(n=1100, seed=9, asset_type="forex")
    r = simulate(df, "EURUSD=X", "forex", _cfg())
    assert r.daily["direction"].min() >= -1
    assert np.isfinite(r.metrics["risk_plan"]["final_equity"])
    if not r.trades.empty:
        assert (r.trades["数量"] % 1000 == 0).all()


def test_stop_loss_is_respected():
    """价格单边下跌时，多头仓位应在止损价附近离场，而不是一直亏下去。"""
    from marketcast.simulate import _simulate_risk_plan

    idx = pd.bdate_range("2024-01-01", periods=40)
    close = pd.Series(np.r_[np.full(20, 100.0), np.linspace(100, 60, 20)], index=idx)
    df = pd.DataFrame({"open": close, "high": close + 0.5, "low": close - 0.5, "close": close, "volume": 1e6})
    sig = pd.DataFrame({"direction": 1}, index=idx[15:])
    cfg = SimConfig(start=str(idx[15].date()), end=str(idx[-1].date()), capital=5000)
    eq, units, trades = _simulate_risk_plan(df, sig, cfg, "TEST", "stock", cost_bps=0)
    assert not trades.empty
    first = trades.iloc[0]
    assert first["平仓原因"].startswith("止损")
    assert first["盈亏"] >= -5000 * 0.01 * 1.5  # 约等于 1% 风险预算


def test_render_html(long_df):
    pytest.importorskip("plotly")
    r = simulate(long_df, "TEST", "stock", _cfg(refit_every=84))
    page = render_html([r], notes=["说明"])
    assert page.startswith("<!doctype html>") and "TEST" in page and "plotly" in page.lower()


def test_cli_simulate_demo(tmp_path, capsys):
    out = tmp_path / "sim.html"
    code = main([
        "simulate", "DEMO", "--demo", "--start", "2025-06-02", "--end", "2025-09-30",
        "--model", "logistic", "--refit-every", "63", "--html", str(out),
    ])
    assert code == 0
    assert "买入持有" in capsys.readouterr().out
