"""可解释的技术面评分。

把多个经典指标各自打分（-1 ~ +1），再加权合成 -100 ~ +100 的综合分，
并为每项给出中文解读。向量化实现，可直接用于回测。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List

import numpy as np
import pandas as pd

from . import indicators as ind

WEIGHTS: Dict[str, float] = {
    "trend": 0.25,
    "macd": 0.20,
    "adx": 0.15,
    "rsi": 0.15,
    "boll": 0.10,
    "kdj": 0.10,
    "volume": 0.05,
}

COMPONENT_NAMES = {
    "trend": "均线趋势",
    "macd": "MACD动能",
    "adx": "ADX趋势强度",
    "rsi": "RSI强弱",
    "boll": "布林带位置",
    "kdj": "KDJ随机指标",
    "volume": "量价配合",
}


@dataclass
class SignalItem:
    key: str
    name: str
    score: float      # -1 ~ +1
    weight: float
    detail: str


def _sign(s: pd.Series) -> pd.Series:
    return np.sign(s).where(s.notna())


def component_scores(data: pd.DataFrame) -> pd.DataFrame:
    """输入 add_indicators 之后的表，输出每个指标分量的得分序列。"""
    c = data["close"]
    out = pd.DataFrame(index=data.index)

    # 1) 均线趋势：价格与 MA20/MA60 的相对位置及均线排列
    out["trend"] = (
        _sign(c - data["sma20"]) + _sign(data["sma20"] - data["sma60"]) + _sign(c - data["sma60"])
    ) / 3

    # 2) MACD：柱体方向 + 是否在放大
    h = data["hist"]
    dh = h.diff()
    macd_score = np.select([(h > 0) & (dh > 0), h > 0, (h < 0) & (dh < 0), h < 0], [1.0, 0.5, -1.0, -0.5], 0.0)
    out["macd"] = pd.Series(macd_score, index=data.index).where(h.notna() & dh.notna())

    # 3) ADX：趋势明显时跟随 DI 方向，震荡市不给方向
    direction = _sign(data["plus_di"] - data["minus_di"])
    a = data["adx"]
    out["adx"] = (direction * np.select([a > 25, a > 20], [1.0, 0.5], 0.0)).where(a.notna())

    # 4) RSI：超买超卖偏逆向，中间区域偏顺势
    r = data["rsi14"]
    rsi_score = np.select(
        [r >= 80, r >= 70, r >= 50, r > 30, r > 20],
        [-1.0, -0.5, 0.3, -0.3, 0.5],
        1.0,
    )
    out["rsi"] = pd.Series(rsi_score, index=data.index).where(r.notna())

    # 5) 布林带：突破上/下轨视为短期过度延伸
    pb = data["bb_pct_b"]
    boll_score = np.select([pb > 1, pb < 0], [-0.6, 0.6], (pb - 0.5) * 0.6)
    out["boll"] = pd.Series(boll_score, index=data.index).where(pb.notna())

    # 6) KDJ：金叉/死叉，低位金叉、高位死叉加分
    k, d = data["kdj_k"], data["kdj_d"]
    golden = (k > d) & (k.shift(1) <= d.shift(1))
    dead = (k < d) & (k.shift(1) >= d.shift(1))
    kdj_score = np.select(
        [golden & (k < 30), golden, dead & (k > 70), dead, k > d, k < d],
        [1.0, 0.6, -1.0, -0.6, 0.3, -0.3],
        0.0,
    )
    out["kdj"] = pd.Series(kdj_score, index=data.index).where(k.notna() & k.shift(1).notna())

    # 7) 量价：放量上涨/放量下跌
    if "vol_sma20" in data:
        vr = data["volume"] / data["vol_sma20"].replace(0, np.nan)
        ret = c.pct_change()
        vol_score = np.where(vr > 1.2, np.sign(ret) * 0.8, np.sign(ret) * 0.2)
        out["volume"] = pd.Series(vol_score, index=data.index).where(vr.notna() & ret.notna())

    return out


def composite_score(components: pd.DataFrame) -> pd.Series:
    """按权重合成综合分（-100 ~ +100），缺失的分量会自动重新归一化权重。"""
    w = pd.Series({k: WEIGHTS[k] for k in components.columns})
    valid = components.notna()
    num = (components.fillna(0) * w).sum(axis=1)
    den = (valid * w).sum(axis=1).replace(0, np.nan)
    score = 100 * num / den
    # 关键分量尚未就绪（预热期）时不出分
    return score.where(valid[["trend", "macd", "rsi"]].all(axis=1))


def technical_score_series(df: pd.DataFrame) -> pd.Series:
    """便捷函数：直接从 OHLCV 得到综合技术分序列。"""
    return composite_score(component_scores(ind.add_indicators(df)))


def score_label(score: float) -> str:
    if np.isnan(score):
        return "数据不足"
    if score >= 40:
        return "强烈看多"
    if score >= 15:
        return "偏多"
    if score > -15:
        return "中性"
    if score > -40:
        return "偏空"
    return "强烈看空"


def _fmt(x: float, nd: int = 2) -> str:
    return "N/A" if x is None or np.isnan(x) else f"{x:.{nd}f}"


def explain_latest(data: pd.DataFrame, comps: pd.DataFrame) -> List[SignalItem]:
    """对最新一根K线的各分量生成中文解读。"""
    row = data.iloc[-1]
    prev = data.iloc[-2]
    sc = comps.iloc[-1]
    items: List[SignalItem] = []

    def add(key: str, detail: str) -> None:
        if key in sc and not np.isnan(sc[key]):
            items.append(SignalItem(key, COMPONENT_NAMES[key], float(sc[key]), WEIGHTS[key], detail))

    c = row["close"]
    pos20 = "上方" if c > row["sma20"] else "下方"
    pos60 = "上方" if c > row["sma60"] else "下方"
    arrange = "MA20 在 MA60 之上（多头排列）" if row["sma20"] > row["sma60"] else "MA20 在 MA60 之下（空头排列）"
    long_term = ""
    if not np.isnan(row.get("sma200", np.nan)):
        long_term = f"；长期看价格位于 MA200 {'上方' if c > row['sma200'] else '下方'}"
    add("trend", f"价格位于 MA20 {pos20}、MA60 {pos60}，{arrange}{long_term}")

    h, ph = row["hist"], prev["hist"]
    cross = ""
    if h > 0 >= ph:
        cross = "，刚刚出现金叉"
    elif h < 0 <= ph:
        cross = "，刚刚出现死叉"
    state = "红柱" if h > 0 else "绿柱"
    trend_h = "放大" if abs(h) > abs(ph) else "缩小"
    add("macd", f"MACD {state}{trend_h}（DIF={_fmt(row['macd'], 4)}, DEA={_fmt(row['signal'], 4)}）{cross}")

    a = row["adx"]
    dir_txt = "多方占优" if row["plus_di"] > row["minus_di"] else "空方占优"
    if a > 25:
        adx_txt = f"ADX={_fmt(a, 1)}，趋势明显，{dir_txt}"
    elif a > 20:
        adx_txt = f"ADX={_fmt(a, 1)}，趋势初现，{dir_txt}"
    else:
        adx_txt = f"ADX={_fmt(a, 1)}，无明显趋势（震荡市），均线类信号可靠性下降"
    add("adx", adx_txt)

    r = row["rsi14"]
    if r >= 80:
        rsi_txt = "严重超买，警惕回调"
    elif r >= 70:
        rsi_txt = "超买区，追高需谨慎"
    elif r >= 50:
        rsi_txt = "强势区"
    elif r > 30:
        rsi_txt = "弱势区"
    elif r > 20:
        rsi_txt = "超卖区，可能出现反弹"
    else:
        rsi_txt = "严重超卖，反弹概率上升"
    add("rsi", f"RSI(14)={_fmt(r, 1)}，{rsi_txt}")

    pb = row["bb_pct_b"]
    if pb > 1:
        bb_txt = "价格突破布林上轨，短期过度延伸"
    elif pb < 0:
        bb_txt = "价格跌破布林下轨，短期超跌"
    elif pb >= 0.5:
        bb_txt = "价格运行在布林中轨与上轨之间"
    else:
        bb_txt = "价格运行在布林中轨与下轨之间"
    bw_hist = data["bb_bandwidth"].iloc[-120:]
    if len(bw_hist.dropna()) > 20 and row["bb_bandwidth"] <= bw_hist.quantile(0.1):
        bb_txt += "；带宽处于近期低位（收口），可能酝酿方向选择"
    add("boll", f"%b={_fmt(pb)}，{bb_txt}")

    k, d, j = row["kdj_k"], row["kdj_d"], row["kdj_j"]
    if k > d and prev["kdj_k"] <= prev["kdj_d"]:
        kdj_txt = "KDJ 金叉" + ("（低位）" if k < 30 else "")
    elif k < d and prev["kdj_k"] >= prev["kdj_d"]:
        kdj_txt = "KDJ 死叉" + ("（高位）" if k > 70 else "")
    else:
        kdj_txt = "K 线在 D 线之上" if k > d else "K 线在 D 线之下"
    add("kdj", f"K={_fmt(k, 1)}, D={_fmt(d, 1)}, J={_fmt(j, 1)}，{kdj_txt}")

    if "vol_sma20" in data:
        vr = row["volume"] / row["vol_sma20"] if row["vol_sma20"] else np.nan
        up = c >= prev["close"]
        if vr > 1.2:
            v_txt = f"放量{'上涨' if up else '下跌'}（量比≈{_fmt(vr)}）"
        else:
            v_txt = f"量能平稳（量比≈{_fmt(vr)}），{'上涨' if up else '下跌'}力度一般"
        add("volume", v_txt)

    return items


@dataclass
class TechnicalView:
    score: float
    label: str
    items: List[SignalItem]
    series: pd.Series    # 历史综合分，用于回测与画图
    data: pd.DataFrame   # 带指标的行情表


def technical_view(df: pd.DataFrame) -> TechnicalView:
    data = ind.add_indicators(df)
    comps = component_scores(data)
    series = composite_score(comps)
    score = float(series.iloc[-1])
    return TechnicalView(score=score, label=score_label(score), items=explain_latest(data, comps), series=series, data=data)
