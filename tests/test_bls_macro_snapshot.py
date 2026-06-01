"""Tests for BLS macro snapshot collector."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from scripts import bls_macro_snapshot as bls


def args(tmp_path: Path, **overrides) -> argparse.Namespace:
    values = {
        "series": ["CUUR0000SA0", "LNS14000000"],
        "start_year": "2025",
        "end_year": "2026",
        "output": str(tmp_path / "bls.json"),
        "markdown": str(tmp_path / "bls.md"),
        "timeout": 1.0,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


def sample_payload() -> dict[str, object]:
    return {
        "status": "REQUEST_SUCCEEDED",
        "Results": {
            "series": [
                {
                    "seriesID": "CUUR0000SA0",
                    "data": [
                        {
                            "year": "2026",
                            "period": "M04",
                            "periodName": "April",
                            "latest": "true",
                            "value": "333.020",
                        }
                    ],
                },
                {
                    "seriesID": "LNS14000000",
                    "data": [
                        {"year": "2026", "period": "M04", "value": "3.9"},
                    ],
                },
            ]
        },
    }


def test_build_report_collects_latest_points(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(bls, "fetch_bls", lambda **_kwargs: sample_payload())

    report = bls.build_report(args(tmp_path))

    assert report["summary"]["status"] == "ok"
    assert report["summary"]["returned_series"] == 2
    assert report["summary"]["latest_points"] == 2
    assert report["series"][0]["latest"]["value"] == 333.02
    assert report["live_trading_authorized"] is False


def test_failed_request_is_reported_without_orders(monkeypatch, tmp_path: Path) -> None:
    def fail_fetch(**_kwargs):
        raise OSError("network unavailable")

    monkeypatch.setattr(bls, "fetch_bls", fail_fetch)

    report = bls.build_report(args(tmp_path))

    assert report["status"] == "error"
    assert report["summary"]["order_created"] is False
    assert report["errors"]


def test_script_writes_json_and_markdown(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(bls, "fetch_bls", lambda **_kwargs: sample_payload())
    output = tmp_path / "bls.json"
    markdown = tmp_path / "bls.md"

    main_result = bls.main(
        [
            "--series",
            "CUUR0000SA0",
            "--output",
            str(output),
            "--markdown",
            str(markdown),
        ]
    )
    assert main_result == 0

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["summary"]["latest_points"] == 2
    assert "BLS macro snapshot" in markdown.read_text(encoding="utf-8")
