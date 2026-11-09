import numpy as np
import pandas as pd
import pytest

from marketcast.data import (
    DataError,
    data_quality_warnings,
    fix_yahoo_fx_bars,
    load_csv,
    load_data,
    normalize_symbol,
    standardize,
)


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("AAPL", ("AAPL", "stock")),
        ("eurusd", ("EURUSD=X", "forex")),
        ("EUR/USD", ("EURUSD=X", "forex")),
        ("USDJPY=X", ("USDJPY=X", "forex")),
        ("600519", ("600519.SS", "stock")),
        ("000001", ("000001.SZ", "stock")),
        ("300750", ("300750.SZ", "stock")),
        ("700", ("0700.HK", "stock")),
        ("09988", ("9988.HK", "stock")),
        ("600519.SS", ("600519.SS", "stock")),
    ],
)
def test_normalize_symbol(raw, expected):
    assert normalize_symbol(raw) == expected


def test_normalize_symbol_forced_forex():
    assert normalize_symbol("XAUUSD", "forex") == ("XAUUSD=X", "forex")


def test_load_csv_chinese_gbk(tmp_path):
    df = pd.DataFrame(
        {
            "日期": pd.bdate_range("2024-01-01", periods=5).strftime("%Y-%m-%d"),
            "开盘": [10, 11, 12, 13, 14],
            "最高": [10.5, 11.5, 12.5, 13.5, 14.5],
            "最低": [9.5, 10.5, 11.5, 12.5, 13.5],
            "收盘": [10.2, 11.2, 12.2, 13.2, 14.2],
            "成交量": [100, 200, 300, 400, 500],
        }
    )
    path = tmp_path / "a.csv"
    df.to_csv(path, index=False, encoding="gbk")
    out = load_csv(path)
    assert list(out.columns) == ["open", "high", "low", "close", "volume"]
    assert isinstance(out.index, pd.DatetimeIndex)
    assert out["close"].iloc[-1] == pytest.approx(14.2)


def test_standardize_fixes_high_low_and_sorts():
    idx = pd.to_datetime(["2024-01-03", "2024-01-02"])
    raw = pd.DataFrame({"Open": [10, 9], "High": [9, 9.5], "Low": [11, 8], "Close": [10.5, 9.2]}, index=idx)
    out = standardize(raw)
    assert out.index.is_monotonic_increasing
    assert (out["high"] >= out[["open", "close"]].max(axis=1)).all()
    assert (out["low"] <= out[["open", "close"]].min(axis=1)).all()
    assert (out["volume"] == 0).all()


def test_standardize_requires_close():
    with pytest.raises(DataError):
        standardize(pd.DataFrame({"date": ["2024-01-01"], "open": [1]}))


def test_load_data_demo_is_deterministic():
    a, name, at = load_data("DEMO", demo=True)
    b, _, _ = load_data("DEMO", demo=True)
    pd.testing.assert_frame_equal(a, b)
    assert name == "DEMO" and at == "stock"


def test_load_data_too_short(tmp_path, stock_df):
    path = tmp_path / "short.csv"
    stock_df.iloc[:50].to_csv(path)
    with pytest.raises(DataError):
        load_data(csv=path)


def _yahoo_like_fx(n=600, seed=0):
    """模拟 Yahoo 外汇日线：close 是开盘快照，high/low 覆盖全天。"""
    rng = np.random.default_rng(seed)
    intraday = 1.1 * np.exp(np.cumsum(rng.normal(0, 0.002, size=n * 24)))
    days = intraday.reshape(n, 24)
    idx = pd.bdate_range("2020-01-01", periods=n)
    return pd.DataFrame(
        {
            "open": days[:, 0],
            "high": days.max(axis=1),
            "low": days.min(axis=1),
            "close": days[:, 0],  # 快照
            "volume": 0.0,
        },
        index=idx,
    )


def test_yahoo_fx_lookahead_detected_and_fixed():
    raw = _yahoo_like_fx()
    assert any("前视偏差" in w for w in data_quality_warnings(raw))
    fixed = fix_yahoo_fx_bars(raw)
    assert not any("前视偏差" in w for w in data_quality_warnings(fixed))
    # 修正后每根K线依然包住开收盘
    assert (fixed["high"] >= fixed[["open", "close"]].max(axis=1) - 1e-12).all()
    assert (fixed["low"] <= fixed[["open", "close"]].min(axis=1) + 1e-12).all()


def test_fix_yahoo_fx_leaves_normal_data_alone(fx_df):
    pd.testing.assert_frame_equal(fix_yahoo_fx_bars(fx_df), fx_df)
