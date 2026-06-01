"""Tests for broker API comparison registry."""

from __future__ import annotations

import json

from scripts.broker_api_comparison import build_report, main

from conftest import PROJECT_ROOT


def test_broker_comparison_preserves_no_order_boundary() -> None:
    report = build_report()

    assert report["live_trading_authorized"] is False
    assert report["paper_api_authorized"] is False
    assert "no credentials" in report["safety"]
    assert "no orders" in report["safety"]
    assert "live order routing" in report["decision"]["rejected_now"]


def test_broker_comparison_covers_alpaca_ibkr_tradier() -> None:
    names = {candidate["name"] for candidate in build_report()["candidates"]}

    assert "Alpaca Trading API" in names
    assert "Interactive Brokers API" in names
    assert "Tradier API" in names


def test_broker_comparison_recommends_no_connection_yet() -> None:
    report = build_report()

    assert report["summary"]["recommendation"] == (
        "defer_broker_connection_start_with_no_order_adapter_contract"
    )
    assert "no-order adapter" in report["decision"]["next_safe_action"]


def test_broker_comparison_script_writes_json_and_markdown(tmp_path) -> None:
    output = tmp_path / "broker.json"
    markdown = tmp_path / "broker.md"

    assert main(["--output", str(output), "--markdown", str(markdown)]) == 0

    payload = json.loads(output.read_text(encoding="utf-8"))
    text = markdown.read_text(encoding="utf-8")
    assert payload["summary"]["candidates"] == 3
    assert "Universal preconditions" in text
    assert "no broker SDKs" in text


def test_broker_api_docs_capture_selected_broker_compare_path() -> None:
    text = (PROJECT_ROOT / "docs" / "broker-api-comparison.md").read_text(encoding="utf-8")

    assert "Broker compare" in text
    assert "Do not connect a broker yet" in text
    assert "Alpaca" in text
    assert "Interactive Brokers" in text
    assert "Tradier" in text
    assert "no order routing" in text
