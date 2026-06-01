"""Tests for cached SEC fundamental feature snapshots."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import pytest
from scripts.sec_fundamental_feature_snapshot import build_snapshot, main


def fact(fiscal_year: int, filed: str, value: float) -> dict[str, object]:
    return {"form": "10-K", "fy": fiscal_year, "filed": filed, "val": value}


def value_fact(filed: str, value: float) -> dict[str, object]:
    return {"form": "10-K", "filed": filed, "val": value}


def write_sec_cache(cache: Path) -> None:
    cache.mkdir(parents=True, exist_ok=True)
    cache.joinpath("company_tickers.json").write_text(
        json.dumps({"0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."}}),
        encoding="utf-8",
    )
    cache.joinpath("CIK0000320193_companyfacts.json").write_text(
        json.dumps(
            {
                "facts": {
                    "us-gaap": {
                        "Revenues": {
                            "units": {
                                "USD": [
                                    fact(2022, "2023-01-01", 100.0),
                                    fact(2023, "2024-01-01", 110.0),
                                    fact(2024, "2027-01-01", 999.0),
                                ]
                            }
                        },
                        "NetIncomeLoss": {"units": {"USD": [value_fact("2024-01-01", 10.0)]}},
                        "NetCashProvidedByUsedInOperatingActivities": {
                            "units": {"USD": [value_fact("2024-01-01", 12.0)]}
                        },
                        "Liabilities": {"units": {"USD": [value_fact("2024-01-01", 50.0)]}},
                        "StockholdersEquity": {"units": {"USD": [value_fact("2024-01-01", 100.0)]}},
                        "AssetsCurrent": {"units": {"USD": [value_fact("2024-01-01", 40.0)]}},
                        "LiabilitiesCurrent": {"units": {"USD": [value_fact("2024-01-01", 20.0)]}},
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    cache.joinpath("CIK0000320193_submissions.json").write_text(
        json.dumps(
            {
                "filings": {
                    "recent": {
                        "form": ["8-K", "10-K", "8-K"],
                        "filingDate": ["2024-03-01", "2024-01-01", "2027-01-01"],
                    }
                }
            }
        ),
        encoding="utf-8",
    )


def args(tmp_path: Path, **overrides) -> argparse.Namespace:
    values = {
        "symbols": ["AAPL", "MSFT"],
        "symbols_file": str(tmp_path / "symbols.txt"),
        "sec_cache_dir": str(tmp_path / "sec"),
        "as_of": "2024-03-15",
        "output": str(tmp_path / "features.csv"),
        "report": str(tmp_path / "report.json"),
        "markdown": str(tmp_path / "report.md"),
        "allow_network_refresh": False,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


def test_snapshot_uses_cached_filed_dates_and_reports_missing_symbols(tmp_path: Path) -> None:
    write_sec_cache(tmp_path / "sec")

    result = build_snapshot(args(tmp_path))
    rows = result["rows"]

    assert rows[0]["symbol"] == "AAPL"
    assert rows[0]["status"] == "pass"
    assert rows[0]["revenue_growth_yoy"] == pytest.approx(0.1)
    assert rows[0]["net_income_positive"] is True
    assert rows[0]["recent_8k_count_90d"] == 1
    assert rows[1]["symbol"] == "MSFT"
    assert "sec_cik_not_found" in rows[1]["failure_reasons"]
    assert result["report"]["summary"]["network_refresh_allowed"] is False
    assert result["report"]["live_trading_authorized"] is False


def test_script_writes_csv_json_and_markdown(tmp_path: Path) -> None:
    write_sec_cache(tmp_path / "sec")
    output = tmp_path / "features.csv"
    report = tmp_path / "report.json"
    markdown = tmp_path / "report.md"

    assert (
        main(
            [
                "--symbols",
                "AAPL",
                "--sec-cache-dir",
                str(tmp_path / "sec"),
                "--as-of",
                "2024-03-15",
                "--output",
                str(output),
                "--report",
                str(report),
                "--markdown",
                str(markdown),
            ]
        )
        == 0
    )

    with output.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    payload = json.loads(report.read_text(encoding="utf-8"))
    assert rows[0]["symbol"] == "AAPL"
    assert rows[0]["net_income_positive"] == "true"
    assert payload["summary"]["passed"] == 1
    assert "SEC fundamental feature snapshot" in markdown.read_text(encoding="utf-8")
