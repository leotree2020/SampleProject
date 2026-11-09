"""命令行入口。

示例::

    python -m marketcast analyze AAPL
    python -m marketcast analyze EURUSD --horizon 3
    python -m marketcast analyze 600519 --start 2018-01-01 --format markdown -o report.md
    python -m marketcast analyze MYDATA --csv examples/sample_ohlcv.csv
    python -m marketcast analyze DEMO --demo
    python -m marketcast scan AAPL MSFT 600519 EURUSD USDJPY
"""

from __future__ import annotations

import argparse
import sys
import warnings
from pathlib import Path
from typing import List

from . import __version__
from .analysis import DISCLAIMER, AnalysisConfig, analyze
from .data import DataError, load_data
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


def main(argv: List[str] | None = None) -> int:
    warnings.filterwarnings("ignore", category=UserWarning)
    args = _build_parser().parse_args(argv)
    try:
        if args.command == "analyze":
            return cmd_analyze(args)
        return cmd_scan(args)
    except DataError as exc:
        print(f"数据错误：{exc}", file=sys.stderr)
        return 2
    except ValueError as exc:
        print(f"参数错误：{exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
