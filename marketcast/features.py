"""机器学习特征工程与预测目标构造。

特征只使用 t 时刻及以前的数据；目标为 t 之后 ``horizon`` 根K线的收益，
两者严格错开，避免前视偏差（look-ahead bias）。
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from . import indicators as ind


def build_features(df: pd.DataFrame) -> pd.DataFrame:
    """构造特征矩阵（每行对应一根K线收盘时可知的信息）。"""
    c, h, l, o = df["close"], df["high"], df["low"], df["open"]
    f = pd.DataFrame(index=df.index)

    logret = np.log(c).diff()
    for n in (1, 3, 5, 10, 20, 60):
        f[f"ret_{n}"] = c.pct_change(n)
    f["vol_10"] = logret.rolling(10).std()
    f["vol_20"] = logret.rolling(20).std()
    f["vol_ratio"] = f["vol_10"] / f["vol_20"]

    for n in (5, 10, 20, 60):
        f[f"close_sma{n}"] = c / ind.sma(c, n) - 1
    f["sma5_sma20"] = ind.sma(c, 5) / ind.sma(c, 20) - 1
    f["sma20_sma60"] = ind.sma(c, 20) / ind.sma(c, 60) - 1

    f["rsi_6"] = ind.rsi(c, 6) / 100
    f["rsi_14"] = ind.rsi(c, 14) / 100

    m = ind.macd(c)
    f["macd"] = m["macd"] / c
    f["macd_hist"] = m["hist"] / c
    f["macd_hist_chg"] = m["hist"].diff() / c

    bb = ind.bollinger(c)
    f["bb_pct_b"] = bb["pct_b"]
    f["bb_width"] = bb["bandwidth"]

    f["atr_pct"] = ind.atr(h, l, c) / c

    k = ind.kdj(h, l, c)
    f["kdj_k"] = k["k"] / 100
    f["kdj_j"] = k["j"] / 100
    f["kdj_kd"] = (k["k"] - k["d"]) / 100

    a = ind.adx(h, l, c)
    f["adx"] = a["adx"] / 100
    f["di_diff"] = (a["plus_di"] - a["minus_di"]) / 100

    rng = (h - l).replace(0, np.nan)
    f["hl_range"] = (h - l) / c
    f["close_pos"] = ((c - l) / rng).fillna(0.5)
    f["gap"] = o / c.shift(1) - 1
    f["dist_high_20"] = c / h.rolling(20).max() - 1
    f["dist_low_20"] = c / l.rolling(20).min() - 1

    if ind.has_volume(df):
        v = df["volume"].astype(float)
        vmean = v.rolling(20).mean()
        vstd = v.rolling(20).std().replace(0, np.nan)
        f["volume_z"] = (v - vmean) / vstd
        f["volume_ratio_5_20"] = v.rolling(5).mean() / vmean.replace(0, np.nan)
        f["obv_slope"] = ind.obv(c, v).diff(10) / (vmean.replace(0, np.nan) * 10)

    return f.replace([np.inf, -np.inf], np.nan)


def forward_return(close: pd.Series, horizon: int) -> pd.Series:
    """t 时刻之后 horizon 根K线的收益率（最后 horizon 行为 NaN）。"""
    return close.shift(-horizon) / close - 1


@dataclass
class Dataset:
    X: pd.DataFrame          # 有标签的特征（用于训练/验证）
    y: pd.Series             # 方向标签：1=上涨，0=下跌/持平
    fwd_ret: pd.Series       # 对应的未来收益
    X_latest: pd.DataFrame   # 最新一行特征（标签未知，用于预测）
    horizon: int


def make_dataset(df: pd.DataFrame, horizon: int = 5) -> Dataset:
    if horizon < 1:
        raise ValueError("horizon 必须 >= 1")
    feats = build_features(df)
    # 预热期之后偶发的缺失值（如成交量为 0 导致除零）用前值填充
    first_valid = feats.dropna().index.min()
    if first_valid is pd.NaT or first_valid is None:
        raise ValueError("数据太短，无法计算全部特征")
    feats = feats.loc[first_valid:].ffill().dropna()

    fwd = forward_return(df["close"], horizon).reindex(feats.index)
    labeled = fwd.notna()
    X = feats[labeled]
    y = (fwd[labeled] > 0).astype(int)
    return Dataset(X=X, y=y, fwd_ret=fwd[labeled], X_latest=feats.iloc[[-1]], horizon=horizon)
