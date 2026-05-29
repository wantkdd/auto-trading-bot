"""Regression tests for committed examples and productization docs."""

from __future__ import annotations

import copy
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from conftest import PROJECT_ROOT

SAFETY_STATEMENT = "This MVP cannot place orders and is not approval for live trading."
SAMPLE_COMMAND_PARTS = (
    "uv run python -m auto_trading_bot.cli backtest",
    "--csv examples/data/sample_ohlcv.csv",
    "--output-dir examples/reports",
    "--strategy moving-average",
    "--symbol SAMPLE",
    "--market offline-fixture",
    "--short-window 3",
    "--long-window 8",
    "--train-fraction 0.65",
    "--min-trades 0",
)


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def _normalize_path_dependent_fields(payload: dict[str, Any]) -> dict[str, Any]:
    normalized = copy.deepcopy(payload)
    assumptions = normalized.get("assumptions")
    assert isinstance(assumptions, dict)
    assumptions["data_source"] = "<normalized-local-csv>"
    return normalized


def _normalize_markdown_paths(markdown: str, sample_csv: Path) -> str:
    return markdown.replace(str(sample_csv), "<normalized-local-csv>").replace(
        "examples/data/sample_ohlcv.csv", "<normalized-local-csv>"
    )


def test_committed_example_report_matches_regenerated_cli_output(tmp_path: Path) -> None:
    sample_csv = PROJECT_ROOT / "examples" / "data" / "sample_ohlcv.csv"
    committed_json_path = PROJECT_ROOT / "examples" / "reports" / "moving-average-report.json"
    committed_markdown_path = PROJECT_ROOT / "examples" / "reports" / "moving-average-report.md"
    output_dir = tmp_path / "reports"

    command = [
        sys.executable,
        "-m",
        "auto_trading_bot.cli",
        "backtest",
        "--csv",
        str(sample_csv),
        "--output-dir",
        str(output_dir),
        "--strategy",
        "moving-average",
        "--symbol",
        "SAMPLE",
        "--market",
        "offline-fixture",
        "--short-window",
        "3",
        "--long-window",
        "8",
        "--train-fraction",
        "0.65",
        "--min-trades",
        "0",
    ]

    completed = subprocess.run(command, check=False, capture_output=True, text=True)

    assert completed.returncode == 0, completed.stderr or completed.stdout
    regenerated_json_path = output_dir / "moving-average-report.json"
    regenerated_markdown_path = output_dir / "moving-average-report.md"
    assert regenerated_json_path.exists()
    assert regenerated_markdown_path.exists()
    assert committed_markdown_path.exists()

    committed_markdown = committed_markdown_path.read_text(encoding="utf-8")
    regenerated_markdown = regenerated_markdown_path.read_text(encoding="utf-8")
    assert _normalize_markdown_paths(committed_markdown, sample_csv) == _normalize_markdown_paths(
        regenerated_markdown, sample_csv
    )

    committed = _load_json(committed_json_path)
    regenerated = _load_json(regenerated_json_path)
    assert _normalize_path_dependent_fields(committed) == _normalize_path_dependent_fields(
        regenerated
    )

    assert committed["live_trading_authorized"] is False
    assert committed["metrics"]["metrics_label"] == "out_of_sample_test"
    assert committed["metrics"]["costs_included"] is True
    assert committed["validation"]["headline_metrics"] == "out_of_sample_test"
    assert "train_metrics" in committed["validation"]
    assert "test_metrics" in committed["validation"]
    assert SAFETY_STATEMENT in json.dumps(committed)
    assert SAFETY_STATEMENT in committed_markdown
    assert "Synthetic example fixtures are for report-shape demonstration only" in json.dumps(
        committed
    )
    assert "Synthetic example fixtures are for report-shape demonstration only" in (
        committed_markdown
    )


def test_docs_document_offline_boundary_and_example_command() -> None:
    readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
    live_gate = (PROJECT_ROOT / "docs" / "future-live-trading-gate.md").read_text(
        encoding="utf-8"
    )
    combined = f"{readme}\n{live_gate}"

    for command_part in SAMPLE_COMMAND_PARTS:
        assert command_part in readme
    assert "examples/reports/moving-average-report.md" in readme
    assert "examples/reports/moving-average-report.json" in readme
    assert "live_trading_authorized=false" in readme
    assert "synthetic and pedagogical" in readme
    assert "not market-performance evidence" in readme
    assert SAFETY_STATEMENT in combined

    required_boundary_phrases = (
        "local-simulator-only",
        "must not add broker SDKs",
        "network clients",
        "credential",
        "account reads",
        "order-routing paths",
        "Documentation alone does not authorize live trading.",
    )
    for phrase in required_boundary_phrases:
        assert phrase in combined
