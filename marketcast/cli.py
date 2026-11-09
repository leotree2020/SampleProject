"""命令行入口。

示例::

    python -m marketcast analyze AAPL
    python -m marketcast analyze EURUSD --horizon 3
    python -m marketcast analyze 600519 --start 2018-01-01 --format markdown -o report.md
    python -m marketcast analyze MYDATA --csv examples/sample_ohlcv.csv
    python -m marketcast analyze DEMO --demo
    python -m marketcast scan AAPL MSFT 600519 EURUSD USDJPY
    python -m marketcast simulate SPY --start 2022-01-03 --end 2022-10-12 --capital 5000
"""

from __future__ import annotations

import argparse
import re
import sys
import warnings
from pathlib import Path
from typing import List

from . import __version__
from .analysis import DISCLAIMER, AnalysisConfig, analyze
from .data import FOREX, DataError, fetch_yahoo, load_data
from .models import MODEL_CHOICES
from .report import RENDERERS, format_table
from .risk import RiskConfig, price_decimals

DEFAULT_CACHE = ".marketcast_cache"


def _add_common(p: argparse.ArgumentParser) -> None:
    p.add_argument("--type", dest="asset_type", choices=["auto", "stock", "forex"], default="auto", help="资产类型（默认自动识别）")
    p.add_argument("--start", help="开始日期，如 2018-01-01（默认取最近 --period）")
    p.add_argument("--end", help="结束日期")
    p.add_argument("--period", default="5y", help="未指定 --start 时的时间跨度，如 2y/5y/10y/max（默认 5y）")
    p.add_argument("--horizon", type=int, default=5, help="预测未来多少根K线（默认 5）")
    p.add_argument("--model", choices=MODEL_CHOICES, default="ensemble", help="机器学习模型（默认集成）")
    p.add_argument("--demo", action="store_true", help="使用合成数据（离线演示）")
    p.add_argument("--no-cache", action="store_true", help="不使用本地行情缓存")
    short = p.add_mutually_exclusive_group()
    short.add_argument("--allow-short", dest="allow_short", action="store_true", default=None, help="允许做空")
    short.add_argument("--long-only", dest="allow_short", action="store_false", help="只做多")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="marketcast", description="股票与外汇预测辅助系统")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    pa = sub.add_parser("analyze", help="分析单个品种并输出完整报告")
    pa.add_argument("symbol", help="代码，如 AAPL / 600519 / 0700 / EURUSD / USDJPY")
    pa.add_argument("--csv", help="改用本地 CSV 数据（需包含日期、开高低收、成交量列）")
    pa.add_argument("--capital", type=float, default=100_000, help="账户资金（默认 100000）")
    pa.add_argument("--risk-pct", type=float, default=0.01, help="单笔风险占资金比例（默认 0.01 即 1%%）")
    pa.add_argument("--atr-mult", type=float, default=2.0, help="止损距离 = N 倍 ATR（默认 2）")
    pa.add_argument("--rr", type=float, default=2.0, help="盈亏比（默认 2）")
    pa.add_argument("--lot-size", type=float, help="最小交易单位（默认：A股100、外汇1000、其他1）")
    pa.add_argument("--no-backtest", action="store_true", help="跳过回测")
    pa.add_argument("--format", choices=list(RENDERERS), default="text", help="输出格式")
    pa.add_argument("-o", "--output", help="把报告写入文件")
    _add_common(pa)

    ps = sub.add_parser("scan", help="批量扫描自选列表，输出汇总表")
    ps.add_argument("symbols", nargs="+", help="多个代码，空格分隔")
    _add_common(ps)

    pm = sub.add_parser("simulate", help="逐日历史模拟：如果当时就用本工具交易，结果会怎样")
    pm.add_argument("symbol", help="代码")
    pm.add_argument("--start", required=True, help="模拟开始日期，如 2022-01-03")
    pm.add_argument("--end", required=True, help="模拟结束日期，如 2022-10-12")
    pm.add_argument("--capital", type=float, default=5000, help="初始资金（账户货币，默认 5000）")
    pm.add_argument("--fx-rate", type=float, help="1 单位账户货币(USD)可换多少标的计价货币；默认自动获取模拟起始日汇率")
    pm.add_argument("--history-years", type=int, default=12, help="模拟开始前用于训练的历史年数（默认 12）")
    pm.add_argument("--refit-every", type=int, default=21, help="每隔多少根K线重训模型（默认 21）")
    pm.add_argument("--risk-pct", type=float, default=0.01, help="单笔风险占资金比例（默认 0.01）")
    pm.add_argument("--atr-mult", type=float, default=2.0, help="止损距离 = N 倍 ATR（默认 2）")
    pm.add_argument("--rr", type=float, default=2.0, help="盈亏比（默认 2）")
    pm.add_argument("--csv", help="改用本地 CSV 数据")
    pm.add_argument("--html", help="HTML 报告保存路径（默认 reports/<代码>_simulation.html）")
    pm.add_argument("--type", dest="asset_type", choices=["auto", "stock", "forex"], default="auto")
    pm.add_argument("--horizon", type=int, default=5, help="预测未来多少根K线（默认 5）")
    pm.add_argument("--model", choices=MODEL_CHOICES, default="ensemble")
    pm.add_argument("--demo", action="store_true", help="使用合成数据")
    pm.add_argument("--no-cache", action="store_true")
    short = pm.add_mutually_exclusive_group()
    short.add_argument("--allow-short", dest="allow_short", action="store_true", default=None)
    short.add_argument("--long-only", dest="allow_short", action="store_false")
    return parser


def _load(args: argparse.Namespace, symbol: str, csv: str | None = None):
    return load_data(
        symbol=symbol,
        asset_type=args.asset_type,
        csv=csv,
        demo=args.demo,
        start=args.start,
        end=args.end,
        period=args.period,
        cache_dir=None if args.no_cache else DEFAULT_CACHE,
    )


def cmd_analyze(args: argparse.Namespace) -> int:
    df, name, asset_type = _load(args, args.symbol, args.csv)
    cfg = AnalysisConfig(
        horizon=args.horizon,
        model=args.model,
        allow_short=args.allow_short,
        run_backtest=not args.no_backtest,
        risk=RiskConfig(
            capital=args.capital,
            risk_pct=args.risk_pct,
            atr_stop_mult=args.atr_mult,
            reward_risk=args.rr,
            lot_size=args.lot_size,
        ),
    )
    result = analyze(df, name, asset_type, cfg)
    text = RENDERERS[args.format](result)
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
        print(f"报告已保存到 {args.output}")
    else:
        print(text)
    return 0


def cmd_scan(args: argparse.Namespace) -> int:
    rows: List[List[str]] = []
    failed = []
    for sym in args.symbols:
        try:
            df, name, asset_type = _load(args, sym)
            cfg = AnalysisConfig(horizon=args.horizon, model=args.model, allow_short=args.allow_short, run_backtest=False)
            a = analyze(df, name, asset_type, cfg)
        except (DataError, ValueError) as exc:
            failed.append(f"{sym}: {exc}")
            continue
        nd = price_decimals(a.last_close, a.asset_type)
        rows.append(
            [
                a.symbol,
                f"{a.as_of:%Y-%m-%d}",
                f"{a.last_close:,.{nd}f}",
                f"{a.change_pct:+.2%}",
                f"{a.tech_score:+.0f}",
                f"{a.ml_proba_up:.0%}",
                "是" if a.ml_validation.has_edge else "否",
                f"{a.combined_score:+.0f}",
                a.combined_label,
                a.confidence,
            ]
        )
    rows.sort(key=lambda r: float(r[7]), reverse=True)
    header = ["代码", "日期", "收盘", "涨跌", "技术分", "上涨概率", "模型有效", "综合分", "结论", "置信度"]
    print("\n".join(format_table([header, *rows])))
    if failed:
        print("\n以下品种处理失败：", file=sys.stderr)
        for f in failed:
            print(f"  - {f}", file=sys.stderr)
    print(f"\n{DISCLAIMER}")
    return 0 if rows else 1


def _account_fx_rate(symbol: str, asset_type: str, df, start: str, cache_dir) -> float:
    """估算 1 美元可兑换多少标的计价货币（取模拟起始日汇率，期间视为不变）。"""
    quote = None
    if asset_type == FOREX:
        m = re.fullmatch(r"([A-Z]{3})([A-Z]{3})=X", symbol)
        if m and m.group(2) != "USD":
            if m.group(1) == "USD":
                return float(df["close"].loc[:start].iloc[-1])
            quote = m.group(2)
    elif symbol.endswith((".SS", ".SZ")):
        quote = "CNY"
    elif symbol.endswith(".HK"):
        quote = "HKD"
    if quote is None:
        return 1.0
    fx = fetch_yahoo(f"{quote}=X", period="max", cache_dir=cache_dir)
    return float(fx["close"].loc[:start].iloc[-1])


def cmd_simulate(args: argparse.Namespace) -> int:
    import pandas as pd

    from .sim_report import render_html, text_summary
    from .simulate import SimConfig, simulate

    start, end = pd.Timestamp(args.start), pd.Timestamp(args.end)
    cache_dir = None if args.no_cache else DEFAULT_CACHE
    df, name, asset_type = load_data(
        symbol=args.symbol, asset_type=args.asset_type, csv=args.csv, demo=args.demo,
        start=f"{start - pd.DateOffset(years=args.history_years):%Y-%m-%d}",
        end=f"{end + pd.Timedelta(days=20):%Y-%m-%d}",
        cache_dir=cache_dir,
    )
    fx = args.fx_rate
    if fx is None:
        fx = 1.0 if (args.csv or args.demo) else _account_fx_rate(name, asset_type, df, args.start, cache_dir)
    cfg = SimConfig(
        start=args.start, end=args.end, capital=args.capital, fx_rate=fx, horizon=args.horizon,
        model=args.model, refit_every=args.refit_every, allow_short=args.allow_short,
        risk=RiskConfig(risk_pct=args.risk_pct, atr_stop_mult=args.atr_mult, reward_risk=args.rr),
    )
    print(f"正在逐日模拟 {name}（{args.start} ~ {args.end}），每 {args.refit_every} 根K线重训一次模型…", file=sys.stderr)
    result = simulate(df, name, asset_type, cfg)
    print(text_summary(result))
    if fx != 1.0:
        print(f"  （按起始日汇率 1 USD = {fx:.4f} 换算，未计汇率波动）")

    out = Path(args.html or f"reports/{re.sub(r'[^A-Za-z0-9._-]', '_', name)}_simulation.html")
    try:
        page = render_html([result], title=f"{name} 历史模拟")
    except ImportError:
        print("未安装 plotly，跳过 HTML 报告（pip install plotly）", file=sys.stderr)
        return 0
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page, encoding="utf-8")
    print(f"\nHTML 报告：{out}")
    return 0


def main(argv: List[str] | None = None) -> int:
    warnings.filterwarnings("ignore", category=UserWarning)
    args = _build_parser().parse_args(argv)
    try:
        if args.command == "analyze":
            return cmd_analyze(args)
        if args.command == "simulate":
            return cmd_simulate(args)
        return cmd_scan(args)
    except DataError as exc:
        print(f"数据错误：{exc}", file=sys.stderr)
        return 2
    except ValueError as exc:
        print(f"参数错误：{exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
