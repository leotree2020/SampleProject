import json

import numpy as np

from marketcast.analysis import AnalysisConfig, analyze
from marketcast.cli import main
from marketcast.report import render_json, render_markdown, render_text
from marketcast.signals import WEIGHTS, technical_view


def test_technical_view(stock_df):
    tv = technical_view(stock_df)
    assert -100 <= tv.score <= 100
    assert {i.key for i in tv.items} <= set(WEIGHTS)
    assert all(-1 <= i.score <= 1 for i in tv.items)
    s = tv.series.dropna()
    assert ((s >= -100) & (s <= 100)).all()


def test_analyze_stock(stock_df):
    a = analyze(stock_df, "TEST", "stock", AnalysisConfig(horizon=5, model="logistic"))
    assert 0 <= a.ml_proba_up <= 1
    assert a.expected_range[0] < a.last_close < a.expected_range[1]
    assert set(a.backtests) == {"technical", "ml"}
    if a.risk_plan is not None:
        assert a.risk_plan.direction == "long"  # 股票默认不做空
    for render in (render_text, render_markdown, render_json):
        assert "TEST" in render(a)
    data = json.loads(render_json(a))
    assert data["symbol"] == "TEST"


def test_analyze_forex(fx_df):
    a = analyze(fx_df, "EURUSD=X", "forex", AnalysisConfig(horizon=3, model="logistic", run_backtest=False))
    assert a.backtests == {}
    assert any("外汇" in w for w in a.warnings)
    assert np.isfinite(a.combined_score)


def test_cli_demo_text(capsys):
    assert main(["analyze", "DEMO", "--demo", "--model", "logistic", "--no-backtest"]) == 0
    out = capsys.readouterr().out
    assert "综合结论" in out and "不构成任何投资建议" in out


def test_cli_csv_json(tmp_path, stock_df, capsys):
    path = tmp_path / "data.csv"
    stock_df.to_csv(path)
    out_file = tmp_path / "r.json"
    assert main(["analyze", "MINE", "--csv", str(path), "--format", "json", "-o", str(out_file), "--model", "logistic"]) == 0
    assert json.loads(out_file.read_text(encoding="utf-8"))["symbol"] == "MINE"


def test_cli_scan_demo(capsys):
    assert main(["scan", "A", "B", "--demo", "--model", "logistic"]) == 0
    out = capsys.readouterr().out
    assert "综合分" in out


def test_cli_bad_csv(capsys, tmp_path):
    assert main(["analyze", "X", "--csv", str(tmp_path / "missing.csv")]) == 2
