"""常用技术指标（纯 pandas 实现，无第三方依赖）。

所有函数只使用当前及之前的数据，不存在未来函数。
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def sma(series: pd.Series, n: int) -> pd.Series:
    """简单移动平均。"""
    return series.rolling(n, min_periods=n).mean()


def ema(series: pd.Series, n: int) -> pd.Series:
    """指数移动平均。"""
    return series.ewm(span=n, adjust=False, min_periods=n).mean()


def _wilder(series: pd.Series, n: int) -> pd.Series:
    return series.ewm(alpha=1.0 / n, adjust=False, min_periods=n).mean()


def rsi(close: pd.Series, n: int = 14) -> pd.Series:
    """相对强弱指数 RSI（Wilder 平滑），取值 0~100。"""
    delta = close.diff()
    avg_gain = _wilder(delta.clip(lower=0), n)
    avg_loss = _wilder(-delta.clip(upper=0), n)
    rs = avg_gain / avg_loss.replace(0, np.nan)
    out = 100 - 100 / (1 + rs)
    # 只涨不跌 -> 100；完全不动 -> 50
    out = out.mask((avg_loss == 0) & (avg_gain > 0), 100.0)
    out = out.mask((avg_loss == 0) & (avg_gain == 0), 50.0)
    return out


def macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.DataFrame:
    """MACD：返回 macd(DIF)、signal(DEA)、hist(柱)。"""
    dif = ema(close, fast) - ema(close, slow)
    dea = dif.ewm(span=signal, adjust=False, min_periods=signal).mean()
    return pd.DataFrame({"macd": dif, "signal": dea, "hist": dif - dea})


def bollinger(close: pd.Series, n: int = 20, k: float = 2.0) -> pd.DataFrame:
    """布林带：mid/upper/lower，以及 %b（价格在带内位置）和带宽。"""
    mid = sma(close, n)
    std = close.rolling(n, min_periods=n).std(ddof=0)
    upper = mid + k * std
    lower = mid - k * std
    width = upper - lower
    pct_b = (close - lower) / width.replace(0, np.nan)
    return pd.DataFrame(
        {"mid": mid, "upper": upper, "lower": lower, "pct_b": pct_b, "bandwidth": width / mid}
    )


def true_range(high: pd.Series, low: pd.Series, close: pd.Series) -> pd.Series:
    prev = close.shift(1)
    return pd.concat([high - low, (high - prev).abs(), (low - prev).abs()], axis=1).max(axis=1)


def atr(high: pd.Series, low: pd.Series, close: pd.Series, n: int = 14) -> pd.Series:
    """平均真实波幅 ATR（Wilder 平滑）。"""
    return _wilder(true_range(high, low, close), n)


def kdj(high: pd.Series, low: pd.Series, close: pd.Series, n: int = 9, m1: int = 3, m2: int = 3) -> pd.DataFrame:
    """KDJ 随机指标（国内常用参数 9,3,3）。"""
    llv = low.rolling(n, min_periods=n).min()
    hhv = high.rolling(n, min_periods=n).max()
    rng = (hhv - llv).replace(0, np.nan)
    rsv = ((close - llv) / rng * 100).where(rng.notna() | llv.isna(), 50.0)
    k = rsv.ewm(alpha=1.0 / m1, adjust=False).mean()
    d = k.ewm(alpha=1.0 / m2, adjust=False).mean()
    return pd.DataFrame({"k": k, "d": d, "j": 3 * k - 2 * d})


def adx(high: pd.Series, low: pd.Series, close: pd.Series, n: int = 14) -> pd.DataFrame:
    """平均趋向指数 ADX 及 +DI / -DI。ADX>25 通常代表趋势明显。"""
    up = high.diff()
    down = -low.diff()
    plus_dm = pd.Series(np.where((up > down) & (up > 0), up, 0.0), index=high.index)
    minus_dm = pd.Series(np.where((down > up) & (down > 0), down, 0.0), index=high.index)
    atr_ = atr(high, low, close, n).replace(0, np.nan)
    plus_di = 100 * _wilder(plus_dm, n) / atr_
    minus_di = 100 * _wilder(minus_dm, n) / atr_
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    return pd.DataFrame({"plus_di": plus_di, "minus_di": minus_di, "adx": _wilder(dx, n)})


def obv(close: pd.Series, volume: pd.Series) -> pd.Series:
    """能量潮 OBV。"""
    direction = np.sign(close.diff()).fillna(0)
    return (direction * volume).cumsum()


def has_volume(df: pd.DataFrame) -> bool:
    """外汇等品种通常没有真实成交量，此时跳过量能相关指标。"""
    vol = df["volume"]
    return bool(len(vol)) and float((vol > 0).mean()) > 0.8


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """在行情表上附加全部技术指标列（返回新表）。"""
    out = df.copy()
    c, h, l = out["close"], out["high"], out["low"]
    for n in (5, 10, 20, 60, 120, 200):
        out[f"sma{n}"] = sma(c, n)
    out["ema12"] = ema(c, 12)
    out["ema26"] = ema(c, 26)
    out["rsi6"] = rsi(c, 6)
    out["rsi14"] = rsi(c, 14)
    out = out.join(macd(c))
    out = out.join(bollinger(c).add_prefix("bb_"))
    out["atr14"] = atr(h, l, c, 14)
    out = out.join(kdj(h, l, c).add_prefix("kdj_"))
    out = out.join(adx(h, l, c))
    if has_volume(out):
        out["obv"] = obv(c, out["volume"])
        out["vol_sma20"] = sma(out["volume"], 20)
    return out
