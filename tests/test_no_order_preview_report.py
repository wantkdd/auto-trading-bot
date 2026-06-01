"""Tests for daily no-order preview report generation."""

from __future__ import annotations

import argparse
import json

from scripts.no_order_preview_report import build_report, main


def write_log(path, rows) -> None:
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")


def args(tmp_path, **overrides):
    values = {
        "log": str(tmp_path / "paper-trade-intent-log.jsonl"),
        "output": str(tmp_path / "preview.json"),
        "markdown": str(tmp_path / "preview.md"),
        "max_order_notional": 10_000.0,
        "max_total_notional": 10_000.0,
        "allowed_symbols": None,
        "blocked_symbols": [],
    }
    values.update(overrides)
    return argparse.Namespace(**values)


def test_build_report_accepts_latest_paper_intents_without_orders(tmp_path) -> None:
    log = tmp_path / "paper-trade-intent-log.jsonl"
    write_log(
        log,
        [
            {
                "generated_at": "2026-06-01T03:26:25+00:00",
                "as_of_date": "2026-05-29",
                "strategy": "AAPL_0.3_GLD_0.7",
                "decision": "would_rebalance",
                "target_weights": {"AAPL": 0.3, "GLD": 0.7},
                "trade_intents": [
                    {
                        "symbol": "AAPL",
                        "side": "would_buy",
                        "quantity": 9,
                        "reference_price": 312.06,
                    },
                    {
                        "symbol": "GLD",
                        "side": "would_buy",
                        "quantity": 16,
                        "reference_price": 417.12,
                    },
                ],
            }
        ],
    )

    report = build_report(args(tmp_path, log=str(log)))

    assert report["summary"]["accepted"] == 2
    assert report["summary"]["rejected"] == 0
    assert report["summary"]["order_created"] is False
    assert report["paper_api_authorized"] is False
    assert report["live_trading_authorized"] is False
    assert "no broker" in report["safety"]


def test_build_report_rejects_blocked_symbol_and_total_notional(tmp_path) -> None:
    log = tmp_path / "paper-trade-intent-log.jsonl"
    write_log(
        log,
        [
            {
                "generated_at": "2026-06-01T03:26:25+00:00",
                "as_of_date": "2026-05-29",
                "strategy": "AAPL_0.3_GLD_0.7",
                "decision": "would_rebalance",
                "target_weights": {"AAPL": 0.3, "GLD": 0.7},
                "trade_intents": [
                    {
                        "symbol": "AAPL",
                        "side": "would_buy",
                        "quantity": 9,
                        "reference_price": 312.06,
                    },
                    {
                        "symbol": "GLD",
                        "side": "would_sell",
                        "quantity": 16,
                        "reference_price": 417.12,
                    },
                ],
            }
        ],
    )

    report = build_report(
        args(
            tmp_path,
            log=str(log),
            max_order_notional=5_000.0,
            max_total_notional=5_000.0,
            blocked_symbols=["GLD"],
        )
    )

    assert report["summary"]["accepted"] == 1
    assert report["summary"]["rejected"] == 1
    assert report["plan"]["rejection_reasons"]["GLD"] == [
        "symbol_not_allowed",
        "symbol_blocked",
        "order_notional_limit_exceeded",
        "total_notional_limit_exceeded",
    ]


def test_empty_log_generates_no_intents_report(tmp_path) -> None:
    report = build_report(args(tmp_path))

    assert report["status"] == "no_intents"
    assert report["summary"]["accepted"] == 0
    assert report["summary"]["order_created"] is False


def test_script_writes_json_and_markdown(tmp_path) -> None:
    log = tmp_path / "paper-trade-intent-log.jsonl"
    write_log(
        log,
        [
            {
                "generated_at": "2026-06-01T03:26:25+00:00",
                "as_of_date": "2026-05-29",
                "strategy": "AAPL_0.3_GLD_0.7",
                "decision": "would_hold",
                "target_weights": {"AAPL": 0.3, "GLD": 0.7},
                "trade_intents": [],
            }
        ],
    )
    output = tmp_path / "preview.json"
    markdown = tmp_path / "preview.md"

    assert main(["--log", str(log), "--output", str(output), "--markdown", str(markdown)]) == 0

    payload = json.loads(output.read_text(encoding="utf-8"))
    text = markdown.read_text(encoding="utf-8")
    assert payload["summary"]["decision"] == "would_hold"
    assert "No-order preview report" in text
    assert "no broker" in text
