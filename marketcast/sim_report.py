"""历史模拟结果的文本摘要与 HTML 报告（HTML 需要 plotly）。"""

from __future__ import annotations

import html
import math
from typing import List

from .risk import price_decimals
from .simulate import SimulationResult

# 颜色按角色固定：工具输出=蓝，全仓变体=橙，实际行情/基准=灰
TOOL = "#2a78d6"
FULL = "#eb6834"
ACTUAL = "#52514e"
BENCH = "#898781"
GRID = "#e1e0d9"
BAND = "rgba(42,120,214,0.13)"

DISCLAIMER = "历史模拟不代表未来表现，不构成任何投资建议。"


def _pct(x: float, signed: bool = True) -> str:
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return "—"
    return f"{x:+.1%}" if signed else f"{x:.1%}"


def _money(x: float) -> str:
    return f"${x:,.0f}"


def text_summary(r: SimulationResult) -> str:
    m = r.metrics
    rp, fp, bh, fc = m["risk_plan"], m["full_position"], m["buy_hold"], m["forecast"]
    nd = price_decimals(float(r.daily["close"].iloc[0]), r.asset_type)
    lines = [
        f"{r.symbol}  {r.cfg.start} ~ {r.cfg.end}  初始资金 {_money(r.cfg.capital)}",
        f"  标的涨跌：{r.daily['close'].iloc[0]:,.{nd}f} → {r.daily['close'].iloc[-1]:,.{nd}f}（{_pct(bh['total_return'])}）",
        f"  跟随工具（风控仓位）：{_money(rp['final_equity'])}（{_pct(rp['total_return'])}，最大回撤 {_pct(rp['max_drawdown'])}，"
        f"{rp['trades']} 笔交易，胜率 {_pct(rp['trade_win_rate'], False)}，持仓时间 {_pct(rp['exposure'], False)}）",
        f"  跟随工具（全仓）：    {_money(fp['final_equity'])}（{_pct(fp['total_return'])}，最大回撤 {_pct(fp['max_drawdown'])}）",
        f"  买入持有：            {_money(bh['final_equity'])}（{_pct(bh['total_return'])}，最大回撤 {_pct(bh['max_drawdown'])}）",
        f"  {r.cfg.horizon}日方向预测命中率 {_pct(fc['direction_hit_rate'], False)}（事后最优常数猜测 {_pct(fc['naive_hit_rate'], False)}），"
        f"AUC {fc['auc']:.3f}",
        f"  预测价格平均误差 {fc['mae_model']:,.{nd}f}，「价格不变」预测误差 {fc['mae_naive']:,.{nd}f}；"
        f"90% 区间实际覆盖率 {_pct(fc['band_coverage'], False)}",
    ]
    return "\n".join(lines)


def _figure(r: SimulationResult):
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots

    d, fc, h = r.daily, r.forecast, r.cfg.horizon
    nd = price_decimals(float(d["close"].iloc[0]), r.asset_type)
    fig = make_subplots(
        rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.07, row_heights=[0.45, 0.33, 0.22],
        subplot_titles=[
            f"实际价格 vs 工具预测价格（每个预测点 = {h} 个交易日前对该日的预测）",
            f"账户资金（初始 {_money(r.cfg.capital)}）",
            "工具综合分（≥10 做多，≤-10 做空/离场）",
        ],
    )
    # 价格：90% 区间、预测、实际
    fig.add_trace(go.Scatter(x=fc.index, y=fc["band_high"], line=dict(width=0), hoverinfo="skip", showlegend=False), 1, 1)
    fig.add_trace(
        go.Scatter(x=fc.index, y=fc["band_low"], line=dict(width=0), fill="tonexty", fillcolor=BAND,
                   name="预测90%区间", hoverinfo="skip"), 1, 1,
    )
    fig.add_trace(
        go.Scatter(x=fc.index, y=fc["pred_price"], name="工具预测价格", line=dict(color=TOOL, width=2),
                   hovertemplate=f"预测 %{{y:,.{nd}f}}<extra></extra>"), 1, 1,
    )
    fig.add_trace(
        go.Scatter(x=d.index, y=d["close"], name="实际价格", line=dict(color=ACTUAL, width=2),
                   hovertemplate=f"实际 %{{y:,.{nd}f}}<extra></extra>"), 1, 1,
    )
    t = r.trades
    if not t.empty:
        for side, symbol_name, label in (("做多", "triangle-up", "开多"), ("做空", "triangle-down", "开空")):
            sub = t[t["方向"] == side]
            if len(sub):
                fig.add_trace(
                    go.Scatter(x=sub["开仓日"], y=sub["开仓价"], mode="markers", name=label,
                               marker=dict(symbol=symbol_name, size=10, color=TOOL, line=dict(color="#fcfcfb", width=1.5)),
                               hovertemplate=f"{label} %{{y:,.{nd}f}}<extra></extra>"), 1, 1,
                )
        fig.add_trace(
            go.Scatter(x=t["平仓日"], y=t["平仓价"], mode="markers", name="平仓",
                       marker=dict(symbol="x-thin", size=9, color=ACTUAL, line=dict(color=ACTUAL, width=2)),
                       customdata=t[["平仓原因", "盈亏"]].to_numpy(),
                       hovertemplate=f"平仓 %{{y:,.{nd}f}}（%{{customdata[0]}}，盈亏 $%{{customdata[1]:,.0f}}）<extra></extra>"), 1, 1,
        )

    # 资金曲线
    fig.add_trace(go.Scatter(x=d.index, y=d["equity_risk"], name="跟随工具（风控仓位）", line=dict(color=TOOL, width=2),
                             hovertemplate="风控仓位 $%{y:,.0f}<extra></extra>"), 2, 1)
    fig.add_trace(go.Scatter(x=d.index, y=d["equity_full"], name="跟随工具（全仓）", line=dict(color=FULL, width=2),
                             hovertemplate="全仓 $%{y:,.0f}<extra></extra>"), 2, 1)
    fig.add_trace(go.Scatter(x=d.index, y=d["equity_bh"], name="买入持有", line=dict(color=BENCH, width=2),
                             hovertemplate="买入持有 $%{y:,.0f}<extra></extra>"), 2, 1)
    fig.add_hline(y=r.cfg.capital, line=dict(color=GRID, width=1), row=2, col=1)

    # 综合分
    fig.add_trace(go.Scatter(x=d.index, y=d["combined"], name="综合分", line=dict(color=TOOL, width=2), showlegend=False,
                             hovertemplate="综合分 %{y:+.0f}<extra></extra>"), 3, 1)
    for lvl in (10, -10):
        fig.add_hline(y=lvl, line=dict(color=BENCH, width=1), row=3, col=1)
    fig.update_yaxes(range=[-100, 100], row=3, col=1)

    fig.update_layout(
        height=920, margin=dict(l=10, r=10, t=60, b=10), hovermode="x unified",
        paper_bgcolor="#fcfcfb", plot_bgcolor="#fcfcfb",
        font=dict(family='system-ui, -apple-system, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif',
                  color="#0b0b0b", size=13),
        legend=dict(orientation="h", yanchor="bottom", y=1.04, x=0, traceorder="normal"),
    )
    fig.update_annotations(font=dict(size=13, color="#52514e"), xanchor="left", x=0)
    fig.update_xaxes(gridcolor=GRID, linecolor="#c3c2b7", showspikes=True, spikemode="across",
                     spikethickness=1, spikedash="solid", spikecolor=BENCH)
    fig.update_yaxes(gridcolor=GRID, linecolor="#c3c2b7", zeroline=False)
    fig.update_yaxes(tickprefix="$", row=2, col=1)
    return fig


def _tiles(r: SimulationResult) -> str:
    m = r.metrics
    rp, fp, bh, fc = m["risk_plan"], m["full_position"], m["buy_hold"], m["forecast"]
    tiles = [
        ("跟随工具（风控仓位）", _money(rp["final_equity"]), f"{_pct(rp['total_return'])} · 最大回撤 {_pct(rp['max_drawdown'])}"),
        ("跟随工具（全仓）", _money(fp["final_equity"]), f"{_pct(fp['total_return'])} · 最大回撤 {_pct(fp['max_drawdown'])}"),
        ("买入持有", _money(bh["final_equity"]), f"{_pct(bh['total_return'])} · 最大回撤 {_pct(bh['max_drawdown'])}"),
        (f"{r.cfg.horizon}日方向命中率", _pct(fc["direction_hit_rate"], False),
         f"总猜多数方向 {_pct(fc['naive_hit_rate'], False)} · AUC {fc['auc']:.2f}"),
    ]
    cells = "".join(
        f'<div class="tile"><div class="tl">{html.escape(a)}</div><div class="tv">{html.escape(b)}</div>'
        f'<div class="ts">{html.escape(c)}</div></div>'
        for a, b, c in tiles
    )
    return f'<div class="tiles">{cells}</div>'


def _trades_table(r: SimulationResult) -> str:
    t = r.trades
    if t.empty:
        return "<p class='muted'>模拟期间没有交易。</p>"
    nd = price_decimals(float(r.daily["close"].iloc[0]), r.asset_type)
    rows = "".join(
        "<tr>"
        f"<td>{row['开仓日']:%Y-%m-%d}</td><td>{row['平仓日']:%Y-%m-%d}</td><td>{row['方向']}</td>"
        f"<td class='n'>{row['数量']:,.0f}</td><td class='n'>{row['开仓价']:,.{nd}f}</td>"
        f"<td class='n'>{row['平仓价']:,.{nd}f}</td><td class='n'>{row['盈亏']:+,.2f}</td><td>{row['平仓原因']}</td>"
        "</tr>"
        for _, row in t.iterrows()
    )
    return (
        f"<details><summary>逐笔交易（{len(t)} 笔）</summary><div class='tw'><table>"
        "<thead><tr><th>开仓日</th><th>平仓日</th><th>方向</th><th>数量</th><th>开仓价</th><th>平仓价</th>"
        "<th>盈亏($)</th><th>平仓原因</th></tr></thead>"
        f"<tbody>{rows}</tbody></table></div></details>"
    )


_CSS = """
:root{color-scheme:light;--bg:#f9f9f7;--card:#fcfcfb;--ink:#0b0b0b;--ink2:#52514e;--muted:#898781;--line:#e1e0d9}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font-family:system-ui,-apple-system,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;line-height:1.6}
main{max-width:1180px;margin:0 auto;padding:24px 16px 48px}
h1{font-size:26px;margin:0 0 4px}
h2{font-size:20px;margin:0 0 4px}
.muted{color:var(--muted)}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:20px;margin:20px 0}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:12px;margin:16px 0}
.tile{border:1px solid var(--line);border-radius:10px;padding:12px 14px}
.tl{font-size:13px;color:var(--ink2)}
.tv{font-size:26px;font-weight:600}
.ts{font-size:13px;color:var(--muted)}
table{border-collapse:collapse;width:100%;font-size:14px}
th,td{padding:6px 10px;border-bottom:1px solid var(--line);text-align:left;white-space:nowrap}
td.n,th.n{text-align:right;font-variant-numeric:tabular-nums}
.tw{overflow-x:auto}
details{margin-top:12px}
summary{cursor:pointer;color:var(--ink2)}
ul{padding-left:20px}
"""


def render_html(results: List[SimulationResult], title: str = "熊市行情历史模拟", notes: List[str] | None = None) -> str:
    """把一个或多个模拟结果渲染为单个 HTML 页面（plotly.js 内嵌，可离线打开）。"""
    import plotly.io as pio

    summary_rows = "".join(
        "<tr>"
        f"<td>{html.escape(r.symbol)}</td><td>{r.cfg.start} ~ {r.cfg.end}</td>"
        f"<td class='n'>{_pct(r.metrics['buy_hold']['total_return'])}</td>"
        f"<td class='n'>{_money(r.metrics['risk_plan']['final_equity'])}（{_pct(r.metrics['risk_plan']['total_return'])}）</td>"
        f"<td class='n'>{_money(r.metrics['full_position']['final_equity'])}（{_pct(r.metrics['full_position']['total_return'])}）</td>"
        f"<td class='n'>{_money(r.metrics['buy_hold']['final_equity'])}</td>"
        f"<td class='n'>{_pct(r.metrics['forecast']['direction_hit_rate'], False)} / {_pct(r.metrics['forecast']['naive_hit_rate'], False)}</td>"
        "</tr>"
        for r in results
    )
    parts = [
        "<!doctype html><html lang='zh-CN'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width, initial-scale=1'>"
        f"<title>{html.escape(title)}</title><style>{_CSS}</style></head><body><main>",
        f"<h1>{html.escape(title)}</h1>",
        f"<p class='muted'>每个交易日只使用当天收盘前可得的数据（模型约每 {results[0].cfg.refit_every} 个交易日重训一次）。"
        f"初始资金 {_money(results[0].cfg.capital)}。{DISCLAIMER}</p>",
        "<div class='card'><h2>汇总</h2><div class='tw'><table><thead><tr><th>标的</th><th>模拟区间</th><th class='n'>标的涨跌</th>"
        "<th class='n'>跟随工具（风控仓位）</th><th class='n'>跟随工具（全仓）</th><th class='n'>买入持有</th>"
        "<th class='n'>方向命中率（对照）</th></tr></thead>"
        f"<tbody>{summary_rows}</tbody></table></div>",
    ]
    if notes:
        parts.append("<ul>" + "".join(f"<li>{html.escape(n)}</li>" for n in notes) + "</ul>")
    parts.append("</div>")

    for i, r in enumerate(results):
        fig_html = pio.to_html(_figure(r), full_html=False, include_plotlyjs=(i == 0), config={"displaylogo": False, "responsive": True})
        fc = r.metrics["forecast"]
        nd = price_decimals(float(r.daily["close"].iloc[0]), r.asset_type)
        parts += [
            "<div class='card'>",
            f"<h2>{html.escape(r.symbol)}</h2><p class='muted'>{r.cfg.start} ~ {r.cfg.end} · {len(r.daily)} 个交易日</p>",
            _tiles(r),
            fig_html,
            f"<p class='muted'>预测价格平均误差 {fc['mae_model']:,.{nd}f}，对照「价格保持不变」的平均误差 {fc['mae_naive']:,.{nd}f}；"
            f"90% 预测区间实际覆盖率 {_pct(fc['band_coverage'], False)}；模型被判定「有预测力」的时间占比 {_pct(fc['edge_share'], False)}。</p>",
            _trades_table(r),
            "</div>",
        ]
    parts.append("</main></body></html>")
    return "".join(parts)
