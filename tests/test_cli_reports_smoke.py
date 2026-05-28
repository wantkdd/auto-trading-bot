"""CLI/reporting smoke gates for local fixture output."""

from __future__ import annotations

import json
import subprocess
import sys

import pytest

SAFETY_STATEMENT = "This MVP cannot place orders and is not approval for live trading."


def _fixture_csv(tmp_path):
    csv_path = tmp_path / "fixture.csv"
    csv_path.write_text(
        "timestamp,open,high,low,close,volume\n"
        "2024-01-01T09:00:00,10,11,9,10,1000\n"
        "2024-01-02T09:00:00,11,12,10,11,1100\n"
        "2024-01-03T09:00:00,12,13,11,12,1200\n"
        "2024-01-04T09:00:00,11,12,10,11,1300\n"
        "2024-01-05T09:00:00,13,14,12,13,1400\n",
        encoding="utf-8",
    )
    return csv_path


def test_reports_module_contains_required_safety_statement() -> None:
    try:
        import auto_trading_bot.reports as reports
    except ModuleNotFoundError as exc:  # pragma: no cover - failure message is the assertion value.
        pytest.fail(f"reports module is required for MVP report safety gates: {exc}")

    module_text = "\n".join(str(value) for value in vars(reports).values())
    assert SAFETY_STATEMENT in module_text


def test_cli_generates_local_markdown_and_json_reports(tmp_path) -> None:
    csv_path = _fixture_csv(tmp_path)
    output_dir = tmp_path / "out"
    command = [
        sys.executable,
        "-m",
        "auto_trading_bot.cli",
        "--csv",
        str(csv_path),
        "--output-dir",
        str(output_dir),
    ]

    completed = subprocess.run(command, check=False, capture_output=True, text=True)
    assert completed.returncode == 0, completed.stderr or completed.stdout

    report_files = sorted(output_dir.iterdir())
    assert {path.suffix for path in report_files} >= {".json", ".md"}
    assert all(path.resolve().is_relative_to(output_dir.resolve()) for path in report_files)

    markdown = "\n".join(path.read_text(encoding="utf-8") for path in report_files if path.suffix == ".md")
    assert SAFETY_STATEMENT in markdown

    json_reports = [json.loads(path.read_text(encoding="utf-8")) for path in report_files if path.suffix == ".json"]
    assert json_reports
    for report in json_reports:
        assert "metrics" in report
        assert "assumptions" in report
        assert "disqualification_flags" in report
        assert SAFETY_STATEMENT in json.dumps(report)
