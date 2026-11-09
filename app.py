"""可视化面板：streamlit run app.py"""

from __future__ import annotations

import warnings

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from marketcast.analysis import DISCLAIMER, AnalysisConfig, analyze
from marketcast.data import DataError, load_data, standardize
from marketcast.models import FEATURE_NAMES_CN, MODEL_CHOICES
from marketcast.report import render_markdown
from marketcast.risk import RiskConfig, price_decimals

warnings.filterwarnings("ignore", category=UserWarning)

# 系列配色：固定顺序，不随数据变化
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#6250d6"]
MUTED = "#898781"
COLOR_SCHEMES = {
    "红涨绿跌（A股习惯）": ("#e34948", "#1baf7a"),
    "绿涨红跌（国际习惯）": ("#1baf7a", "#e34948"),
    "红涨蓝跌（色盲友好）": ("#e34948", "#2a78d6"),
}
MODEL_CN = {"ensemble": "集成模型", "logistic": "逻辑回归", "random_forest": "随机森林", "gradient_boosting": "梯度提升"}
BT_CN = {"technical": "技术评分策略", "ml": "机器学习策略（样本外）"}

st.set_page_config(page_title="股票外汇预测辅助", page_icon="📈", layout="wide")


@st.cache_data(ttl=3600, show_spinner=False)
def _load(symbol: str, asset_type: str, period: str, demo: bool):
    return load_data(symbol=symbol, asset_type=asset_type, period=period, demo=demo, cache_dir=".marketcast_cache")


@st.cache_data(ttl=3600, show_spinner=False)
def _analyze(df: pd.DataFrame, name: str, asset_type: str, cfg: AnalysisConfig):
    return analyze(df, name, asset_type, cfg)


def _base_layout(fig: go.Figure, height: int) -> go.Figure:
    fig.update_layout(
        height=height,
        margin=dict(l=8, r=8, t=24, b=8),
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.01, x=0, traceorder="normal"),
        font=dict(family='system-ui, -apple-system, "Segoe UI", sans-serif'),
    )
    fig.update_xaxes(showspikes=True, spikemode="across", spikethickness=1, spikedash="solid", spikecolor=MUTED)
    return fig


def price_chart(a, bars: int, up: str, down: str) -> go.Figure:
    d = a.data.iloc[-bars:]
    score = a.tech_series.reindex(d.index)
    has_vol = "vol_sma20" in d
    rows = ["价格"] + (["成交量"] if has_vol else []) + ["RSI(14)", "MACD", "技术评分"]
    heights = [0.46] + ([0.1] if has_vol else []) + [0.13, 0.15, 0.16]
    fig = make_subplots(rows=len(rows), cols=1, shared_xaxes=True, vertical_spacing=0.035, row_heights=heights, subplot_titles=rows)

    fig.add_trace(go.Scatter(x=d.index, y=d["bb_upper"], line=dict(width=0), hoverinfo="skip", showlegend=False), 1, 1)
    fig.add_trace(
        go.Scatter(x=d.index, y=d["bb_lower"], line=dict(width=0), fill="tonexty", fillcolor="rgba(137,135,129,0.14)",
                   name="布林带", hoverinfo="skip"), 1, 1,
    )
    fig.add_trace(
        go.Candlestick(x=d.index, open=d["open"], high=d["high"], low=d["low"], close=d["close"], name="K线",
                       increasing=dict(line=dict(color=up, width=1), fillcolor=up),
                       decreasing=dict(line=dict(color=down, width=1), fillcolor=down)), 1, 1,
    )
    fig.add_trace(go.Scatter(x=d.index, y=d["sma20"], name="MA20", line=dict(color=SERIES[0], width=2)), 1, 1)
    fig.add_trace(go.Scatter(x=d.index, y=d["sma60"], name="MA60", line=dict(color=SERIES[1], width=2)), 1, 1)

    r = 2
    if has_vol:
        colors = [up if c >= o else down for o, c in zip(d["open"], d["close"])]
        fig.add_trace(go.Bar(x=d.index, y=d["volume"], marker_color=colors, name="成交量", showlegend=False), r, 1)
        r += 1

    fig.add_trace(go.Scatter(x=d.index, y=d["rsi14"], name="RSI", line=dict(color=SERIES[0], width=2), showlegend=False), r, 1)
    for lvl in (30, 70):
        fig.add_hline(y=lvl, line=dict(color=MUTED, width=1), row=r, col=1)
    fig.update_yaxes(range=[0, 100], row=r, col=1)
    r += 1

    hist_colors = [up if v >= 0 else down for v in d["hist"].fillna(0)]
    fig.add_trace(go.Bar(x=d.index, y=d["hist"], marker_color=hist_colors, name="MACD柱", showlegend=False), r, 1)
    fig.add_trace(go.Scatter(x=d.index, y=d["macd"], name="DIF", line=dict(color=SERIES[0], width=2), showlegend=False), r, 1)
    fig.add_trace(go.Scatter(x=d.index, y=d["signal"], name="DEA", line=dict(color=SERIES[1], width=2), showlegend=False), r, 1)
    r += 1

    fig.add_trace(go.Scatter(x=d.index, y=score, name="技术评分", line=dict(color=SERIES[3], width=2), showlegend=False), r, 1)
    fig.add_hline(y=0, line=dict(color=MUTED, width=1), row=r, col=1)
    fig.update_yaxes(range=[-100, 100], row=r, col=1)

    fig.update_xaxes(rangeslider_visible=False, rangebreaks=[dict(bounds=["sat", "mon"])])
    return _base_layout(fig, 900)


def component_chart(a, up: str, down: str) -> go.Figure:
    items = list(reversed(a.tech_items))
    fig = go.Figure(
        go.Bar(
            x=[i.score for i in items], y=[i.name for i in items], orientation="h",
            marker_color=[up if i.score >= 0 else down for i in items],
            customdata=[[i.weight, i.detail] for i in items],
            hovertemplate="%{y}：%{x:+.2f}（权重 %{customdata[0]:.2f}）<br>%{customdata[1]}<extra></extra>",
        )
    )
    fig.update_xaxes(range=[-1.05, 1.05], zeroline=True, zerolinecolor=MUTED, title="得分（-1 看空 ~ +1 看多）")
    _base_layout(fig, 320)
    fig.update_layout(hovermode="closest")
    return fig


def importance_chart(a) -> go.Figure:
    feats = list(reversed(a.ml_top_features))
    fig = go.Figure(
        go.Bar(x=[v for _, v in feats], y=[FEATURE_NAMES_CN.get(n, n) for n, _ in feats], orientation="h",
               marker_color=SERIES[0], hovertemplate="%{y}：%{x:.3f}<extra></extra>")
    )
    fig.update_xaxes(title="随机森林特征重要性")
    _base_layout(fig, 300)
    fig.update_layout(hovermode="closest")
    return fig


def equity_chart(bt) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=bt.equity.index, y=bt.equity, name="策略", line=dict(color=SERIES[0], width=2)))
    fig.add_trace(go.Scatter(x=bt.benchmark.index, y=bt.benchmark, name="买入持有", line=dict(color=MUTED, width=2)))
    fig.update_yaxes(title="净值（初始 = 1）")
    return _base_layout(fig, 360)


def _metric_table(bt) -> pd.DataFrame:
    names = {
        "total_return": ("总收益", "pct"), "cagr": ("年化收益", "pct"), "annual_vol": ("年化波动", "pct"),
        "sharpe": ("夏普比率", "num"), "max_drawdown": ("最大回撤", "pct"), "calmar": ("卡玛比率", "num"),
        "exposure": ("持仓时间占比", "pct"), "win_rate": ("持仓日胜率", "pct"), "trades": ("开仓次数", "int"),
    }

    def fmt(v, kind):
        if v is None or pd.isna(v):
            return "—"
        return f"{v:.2%}" if kind == "pct" else (f"{int(v)}" if kind == "int" else f"{v:.2f}")

    rows = []
    for k, (label, kind) in names.items():
        rows.append({"指标": label, "策略": fmt(bt.metrics.get(k), kind), "买入持有": fmt(bt.benchmark_metrics.get(k), kind)})
    return pd.DataFrame(rows).set_index("指标")


# ---------------- 侧边栏 ----------------
with st.sidebar:
    st.header("参数设置")
    source = st.radio("数据源", ["在线行情（Yahoo）", "上传 CSV", "演示数据"], horizontal=False)
    uploaded = None
    if source == "上传 CSV":
        uploaded = st.file_uploader("CSV 需包含 日期/开盘/最高/最低/收盘/成交量 列（中英文均可）", type=["csv"])
    symbol = st.text_input("代码", value="AAPL" if source != "演示数据" else "DEMO",
                           help="美股 AAPL；A股 600519 / 000001；港股 0700；外汇 EURUSD / USDJPY")
    asset_label = st.selectbox("资产类型", ["自动识别", "股票", "外汇"])
    asset_type = {"自动识别": "auto", "股票": "stock", "外汇": "forex"}[asset_label]
    period = st.selectbox("历史数据长度", ["2y", "5y", "10y", "max"], index=1)
    horizon = st.slider("预测周期（K线数）", 1, 20, 5)
    model = st.selectbox("机器学习模型", MODEL_CHOICES, format_func=lambda m: MODEL_CN.get(m, m))
    short_label = st.selectbox("允许做空", ["自动（外汇是/股票否）", "是", "否"])
    allow_short = {"自动（外汇是/股票否）": None, "是": True, "否": False}[short_label]

    st.subheader("风控")
    capital = st.number_input("账户资金", min_value=1000.0, value=100_000.0, step=10_000.0)
    risk_pct = st.slider("单笔风险（占资金 %）", 0.25, 5.0, 1.0, 0.25) / 100
    atr_mult = st.slider("止损 = N 倍 ATR", 0.5, 5.0, 2.0, 0.5)
    rr = st.slider("盈亏比", 0.5, 5.0, 2.0, 0.5)

    st.subheader("显示")
    scheme = st.selectbox("涨跌配色", list(COLOR_SCHEMES))
    bars = st.slider("图表显示K线数", 60, 1000, 250, 10)
    run = st.button("开始分析", type="primary")

st.title("📈 股票外汇预测辅助系统")
st.caption(DISCLAIMER)

if not run and "analysis" not in st.session_state:
    st.info("在左侧设置参数后点击「开始分析」。")
    st.stop()

if run:
    try:
        with st.spinner("正在获取数据并分析…"):
            if source == "上传 CSV":
                if uploaded is None:
                    st.warning("请先上传 CSV 文件")
                    st.stop()
                df = standardize(pd.read_csv(uploaded))
                name = symbol or uploaded.name
                at = asset_type if asset_type != "auto" else "stock"
            else:
                df, name, at = _load(symbol, asset_type, period, source == "演示数据")
            cfg = AnalysisConfig(
                horizon=horizon, model=model, allow_short=allow_short,
                risk=RiskConfig(capital=capital, risk_pct=risk_pct, atr_stop_mult=atr_mult, reward_risk=rr),
            )
            st.session_state["analysis"] = _analyze(df, name, at, cfg)
    except (DataError, ValueError) as exc:
        st.error(f"分析失败：{exc}")
        st.stop()

a = st.session_state["analysis"]
up, down = COLOR_SCHEMES[scheme]
nd = price_decimals(a.last_close, a.asset_type)

# ---------------- 概览 ----------------
st.subheader(f"{a.symbol} · 截至 {a.as_of:%Y-%m-%d}")
c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("收盘价", f"{a.last_close:,.{nd}f}", f"{a.change_pct:+.2%}", delta_color="off")
c2.metric("综合结论", a.combined_label, f"综合分 {a.combined_score:+.1f}", delta_color="off", delta_arrow="off")
c3.metric("技术面评分", f"{a.tech_score:+.1f}", a.tech_label, delta_color="off", delta_arrow="off")
c4.metric(f"未来{a.horizon}期上涨概率", f"{a.ml_proba_up:.1%}",
          "模型有一定预测力" if a.ml_validation.has_edge else "模型预测力不足", delta_color="off", delta_arrow="off")
c5.metric("置信度", a.confidence)

st.info(f"**操作参考：** {a.suggestion}　|　未来 {a.horizon} 根K线约 90% 波动区间："
        f"{a.expected_range[0]:,.{nd}f} ~ {a.expected_range[1]:,.{nd}f}")
for w in a.warnings:
    st.warning(w)

tab_chart, tab_tech, tab_ml, tab_bt, tab_risk = st.tabs(["行情图表", "技术信号", "机器学习", "历史回测", "风控建议"])

with tab_chart:
    st.plotly_chart(price_chart(a, bars, up, down))

with tab_tech:
    st.plotly_chart(component_chart(a, up, down))
    st.dataframe(
        pd.DataFrame([{"指标": i.name, "得分": round(i.score, 2), "权重": i.weight, "解读": i.detail} for i in a.tech_items]),
        hide_index=True, 
    )
    st.caption("综合技术分 = Σ(得分 × 权重) / Σ权重 × 100。仅反映当前形态，不代表未来走势。")

with tab_ml:
    v = a.ml_validation
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("样本外准确率", f"{v.accuracy:.1%}")
    m2.metric("朴素基准准确率", f"{v.baseline_accuracy:.1%}", help="始终预测训练集中更常见的方向")
    m3.metric("AUC", f"{v.auc:.3f}", help="0.5 等于随机猜测")
    m4.metric("测试样本数", f"{v.n_test}")
    left, right = st.columns([1, 1])
    with left:
        st.markdown("**滚动验证各折表现**")
        folds = pd.DataFrame(v.folds).rename(columns={"start": "开始", "end": "结束", "accuracy": "准确率", "auc": "AUC", "n": "样本数"})
        folds["准确率"] = folds["准确率"].map("{:.1%}".format)
        folds["AUC"] = folds["AUC"].map("{:.3f}".format)
        st.dataframe(folds, hide_index=True)
    with right:
        st.plotly_chart(importance_chart(a))
    st.caption("采用时间顺序的扩展窗口验证，训练集与测试集之间留出预测周期长度的间隔，防止信息泄露。")

with tab_bt:
    if not a.backtests:
        st.write("未运行回测。")
    for key, bt in a.backtests.items():
        st.markdown(f"**{BT_CN.get(key, key)}**（{bt.equity.index[0]:%Y-%m-%d} ~ {bt.equity.index[-1]:%Y-%m-%d}）")
        left, right = st.columns([2, 1])
        left.plotly_chart(equity_chart(bt))
        right.dataframe(_metric_table(bt))
    st.caption("回测按收盘价成交并扣除交易成本（股票 10bp、外汇 2bp），未考虑滑点、涨跌停、T+1、隔夜利息等。")

with tab_risk:
    rp = a.risk_plan
    if rp is None:
        st.write("当前没有明确的开仓方向，不给出仓位建议。")
    else:
        unit = "单位" if a.asset_type == "forex" else "股"
        st.dataframe(
            pd.DataFrame(
                {
                    "项目": ["方向", "参考入场", "止损", "止盈", "ATR(14)", f"建议数量（{unit}）", "名义市值", "杠杆", "触发止损预计亏损"],
                    "数值": [
                        "做多" if rp.direction == "long" else "做空", f"{rp.entry:,.{nd}f}", f"{rp.stop_loss:,.{nd}f}",
                        f"{rp.take_profit:,.{nd}f}", f"{rp.atr:,.{nd}f}", f"{rp.units:,.0f}", f"{rp.position_value:,.2f}",
                        f"{rp.leverage:.2f}x", f"{rp.risk_amount:,.2f}",
                    ],
                }
            ),
            hide_index=True, 
        )
        if rp.note:
            st.warning(rp.note)

st.download_button("下载 Markdown 报告", render_markdown(a), file_name=f"{a.symbol}_report.md", mime="text/markdown")
