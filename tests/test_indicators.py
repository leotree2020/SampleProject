import numpy as np
import pandas as pd
import pytest

from marketcast import indicators as ind


def test_sma_matches_manual():
    s = pd.Series([1.0, 2, 3, 4, 5])
    out = ind.sma(s, 3)
    assert np.isnan(out.iloc[1])
    assert out.iloc[-1] == pytest.approx(4.0)


def test_rsi_bounds_and_extremes(stock_df):
    r = ind.rsi(stock_df["close"]).dropna()
    assert ((r >= 0) & (r <= 100)).all()
    rising = pd.Series(np.arange(1, 50, dtype=float))
    assert ind.rsi(rising).iloc[-1] == pytest.approx(100.0)
    flat = pd.Series(np.full(40, 5.0))
    assert ind.rsi(flat).iloc[-1] == pytest.approx(50.0)


def test_macd_hist_is_difference(stock_df):
    m = ind.macd(stock_df["close"]).dropna()
    np.testing.assert_allclose(m["hist"], m["macd"] - m["signal"])


def test_bollinger_ordering(stock_df):
    bb = ind.bollinger(stock_df["close"]).dropna()
    assert (bb["upper"] >= bb["mid"]).all() and (bb["mid"] >= bb["lower"]).all()


def test_atr_positive(stock_df):
    a = ind.atr(stock_df["high"], stock_df["low"], stock_df["close"]).dropna()
    assert (a > 0).all()


def test_kdj_and_adx_ranges(stock_df):
    k = ind.kdj(stock_df["high"], stock_df["low"], stock_df["close"]).dropna()
    assert k["k"].between(0, 100).all() and k["d"].between(0, 100).all()
    a = ind.adx(stock_df["high"], stock_df["low"], stock_df["close"]).dropna()
    assert a["adx"].between(0, 100).all()


def test_indicators_have_no_lookahead(stock_df):
    """截断未来数据后，历史指标值不应改变。"""
    full = ind.add_indicators(stock_df)
    cut = ind.add_indicators(stock_df.iloc[:600])
    cols = [c for c in cut.columns if c not in ("obv",)]
    pd.testing.assert_frame_equal(full.iloc[:600][cols], cut[cols])


def test_forex_has_no_volume_indicators(fx_df):
    out = ind.add_indicators(fx_df)
    assert "vol_sma20" not in out and "obv" not in out
