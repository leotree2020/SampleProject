"""把分析结果渲染为文本 / Markdown / JSON。"""

from __future__ import annotations

import json
import math
from typing import Any, Dict, List

from .analysis import DISCLAIMER, Analysis
from .data import FOREX
from .models import FEATURE_NAMES_CN
from .risk import price_decimals

_DIR_CN = {"long": "做多", "short": "做空"}


def display_width(s: str) -> int:
    """终端显示宽度（中文等宽字符算 2）。"""
    return sum(2 if ord(ch) > 0x2E7F else 1 for ch in s)


def ljust(s: str, width: int) -> str:
    return s + " " * max(0, width - display_width(s))


def format_table(rows: List[List[str]], indent: str = "") -> List[str]:
    """按显示宽度对齐的纯文本表格。"""
    widths = [max(display_width(r[i]) for r in rows) for i in range(len(rows[0]))]
    return [indent + "  ".join(ljust(c, w) for c, w in zip(r, widths)).rstrip() for r in rows]


def _pct(x: float, signed: bool = False) -> str:
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return "N/A"
    return f"{x:+.2%}" if signed else f"{x:.2%}"


def _num(x: float, nd: int = 2) -> str:
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return "N/A"
    return f"{x:,.{nd}f}"


def _bt_rows(a: Analysis) -> List[List[str]]:
    rows = []
    names = {"technical": "技术评分策略", "ml": "机器学习策略(样本外)"}
    for key, bt in a.backtests.items():
        m, b = bt.metrics, bt.benchmark_metrics
        rows.append(
            [
                names.get(key, key),
                f"{bt.equity.index[0]:%Y-%m-%d}~{bt.equity.index[-1]:%Y-%m-%d}",
                _pct(m["total_return"], True),
                _pct(b["total_return"], True),
                _pct(m["cagr"], True),
                _num(m["sharpe"]),
                _pct(m["max_drawdown"]),
                _pct(m.get("win_rate", float("nan"))),
                str(m.get("trades", "")),
            ]
        )
    return rows


_BT_HEADER = ["策略", "区间", "策略收益", "买入持有", "年化", "夏普", "最大回撤", "胜率", "交易次数"]


def render_text(a: Analysis) -> str:
    nd = price_decimals(a.last_close, a.asset_type)
    asset_cn = "外汇" if a.asset_type == FOREX else "股票"
    val = a.ml_validation
    lines = [
        "=" * 64,
        f" {a.symbol}（{asset_cn}）  截至 {a.as_of:%Y-%m-%d}  收盘 {_num(a.last_close, nd)}  ({_pct(a.change_pct, True)})",
        "=" * 64,
        "",
        f"【综合结论】{a.combined_label}   综合分 {a.combined_score:+.1f}   置信度：{a.confidence}",
        f"【操作参考】{a.suggestion}",
        f"【未来{a.horizon}根K线约90%波动区间】{_num(a.expected_range[0], nd)} ~ {_num(a.expected_range[1], nd)}",
        "",
        f"一、技术面评分：{a.tech_score:+.1f}（{a.tech_label}）",
    ]
    for it in a.tech_items:
        lines.append(f"  - {ljust(it.name, 12)} {it.score:+.2f} ×{it.weight:.2f}  {it.detail}")

    lines += [
        "",
        f"二、机器学习预测（未来{a.horizon}根K线）",
        f"  上涨概率：{a.ml_proba_up:.1%}",
        f"  样本外验证：准确率 {val.accuracy:.1%} | AUC {val.auc:.3f} | 朴素基准 {val.baseline_accuracy:.1%} "
        f"| 测试样本 {val.n_test} | {'有一定预测力' if val.has_edge else '预测力不足'}",
        "  重要特征：" + "、".join(FEATURE_NAMES_CN.get(n, n) for n, _ in a.ml_top_features),
    ]

    lines += ["", "三、风控建议"]
    rp = a.risk_plan
    if rp is None:
        lines.append("  当前无明确开仓方向，不给出仓位建议。")
    else:
        unit = "单位" if a.asset_type == FOREX else "股"
        lines += [
            f"  方向：{_DIR_CN[rp.direction]}   参考入场：{_num(rp.entry, nd)}   ATR(14)：{_num(rp.atr, nd)}",
            f"  止损：{_num(rp.stop_loss, nd)}   止盈：{_num(rp.take_profit, nd)}",
            f"  建议数量：{rp.units:,.0f} {unit}   名义市值：{_num(rp.position_value)}   "
            f"杠杆：{rp.leverage:.2f}x   止损亏损约：{_num(rp.risk_amount)}",
        ]
        if rp.note:
            lines.append(f"  注意：{rp.note}")

    if a.backtests:
        lines += ["", "四、历史回测（含交易成本，不代表未来表现）"]
        lines += format_table([_BT_HEADER, *_bt_rows(a)], indent="  ")

    if a.warnings:
        lines += ["", "⚠ 提示"]
        lines += [f"  - {w}" for w in a.warnings]

    lines += ["", DISCLAIMER, ""]
    return "\n".join(lines)


def render_markdown(a: Analysis) -> str:
    nd = price_decimals(a.last_close, a.asset_type)
    val = a.ml_validation
    out = [
        f"# {a.symbol} 预测辅助报告",
        "",
        f"截至 **{a.as_of:%Y-%m-%d}**，收盘 **{_num(a.last_close, nd)}**（{_pct(a.change_pct, True)}）",
        "",
        "## 综合结论",
        "",
        f"- 结论：**{a.combined_label}**（综合分 {a.combined_score:+.1f}，置信度 {a.confidence}）",
        f"- 操作参考：{a.suggestion}",
        f"- 未来 {a.horizon} 根K线约 90% 波动区间：{_num(a.expected_range[0], nd)} ~ {_num(a.expected_range[1], nd)}",
        "",
        f"## 技术面评分：{a.tech_score:+.1f}（{a.tech_label}）",
        "",
        "| 指标 | 得分 | 权重 | 解读 |",
        "|---|---|---|---|",
    ]
    out += [f"| {it.name} | {it.score:+.2f} | {it.weight:.2f} | {it.detail} |" for it in a.tech_items]
    out += [
        "",
        "## 机器学习预测",
        "",
        f"- 未来 {a.horizon} 根K线上涨概率：**{a.ml_proba_up:.1%}**",
        f"- 样本外准确率 {val.accuracy:.1%}，AUC {val.auc:.3f}，朴素基准 {val.baseline_accuracy:.1%}，测试样本 {val.n_test}",
        "- 重要特征：" + "、".join(FEATURE_NAMES_CN.get(n, n) for n, _ in a.ml_top_features),
        "",
        "## 风控建议",
        "",
    ]
    rp = a.risk_plan
    if rp is None:
        out.append("当前无明确开仓方向，不给出仓位建议。")
    else:
        out += [
            f"- 方向：{_DIR_CN[rp.direction]}，参考入场 {_num(rp.entry, nd)}，ATR(14) {_num(rp.atr, nd)}",
            f"- 止损 {_num(rp.stop_loss, nd)}，止盈 {_num(rp.take_profit, nd)}",
            f"- 建议数量 {rp.units:,.0f}，名义市值 {_num(rp.position_value)}，杠杆 {rp.leverage:.2f}x，止损亏损约 {_num(rp.risk_amount)}",
        ]
        if rp.note:
            out.append(f"- 注意：{rp.note}")
    if a.backtests:
        out += ["", "## 历史回测", "", "| " + " | ".join(_BT_HEADER) + " |", "|" + "---|" * len(_BT_HEADER)]
        out += ["| " + " | ".join(r) + " |" for r in _bt_rows(a)]
    if a.warnings:
        out += ["", "## 提示", ""] + [f"- {w}" for w in a.warnings]
    out += ["", f"> {DISCLAIMER}", ""]
    return "\n".join(out)


def _clean(x: Any) -> Any:
    if isinstance(x, float) and (math.isnan(x) or math.isinf(x)):
        return None
    return x


def to_dict(a: Analysis) -> Dict[str, Any]:
    val = a.ml_validation
    rp = a.risk_plan
    return {
        "symbol": a.symbol,
        "asset_type": a.asset_type,
        "as_of": f"{a.as_of:%Y-%m-%d}",
        "last_close": a.last_close,
        "change_pct": a.change_pct,
        "horizon": a.horizon,
        "combined": {
            "score": a.combined_score,
            "label": a.combined_label,
            "confidence": a.confidence,
            "suggestion": a.suggestion,
            "expected_range": list(a.expected_range),
        },
        "technical": {
            "score": _clean(a.tech_score),
            "label": a.tech_label,
            "items": [
                {"key": i.key, "name": i.name, "score": i.score, "weight": i.weight, "detail": i.detail}
                for i in a.tech_items
            ],
        },
        "ml": {
            "proba_up": a.ml_proba_up,
            "accuracy": _clean(val.accuracy),
            "auc": _clean(val.auc),
            "baseline_accuracy": _clean(val.baseline_accuracy),
            "n_test": val.n_test,
            "has_edge": val.has_edge,
            "folds": [{k: _clean(v) for k, v in f.items()} for f in val.folds],
            "top_features": [{"name": n, "importance": v} for n, v in a.ml_top_features],
        },
        "risk_plan": None
        if rp is None
        else {k: _clean(v) for k, v in rp.__dict__.items()},
        "backtests": {
            k: {
                "start": f"{bt.equity.index[0]:%Y-%m-%d}",
                "end": f"{bt.equity.index[-1]:%Y-%m-%d}",
                "strategy": {m: _clean(v) for m, v in bt.metrics.items()},
                "buy_and_hold": {m: _clean(v) for m, v in bt.benchmark_metrics.items()},
            }
            for k, bt in a.backtests.items()
        },
        "warnings": a.warnings,
        "disclaimer": DISCLAIMER,
    }


def render_json(a: Analysis) -> str:
    return json.dumps(to_dict(a), ensure_ascii=False, indent=2)


RENDERERS = {"text": render_text, "markdown": render_markdown, "json": render_json}
