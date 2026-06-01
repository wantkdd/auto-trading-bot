"""Tests for no-order operational risk gates."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from scripts.operational_risk_gate import (
    build_report,
    evaluate_drift_monitor,
    evaluate_market_data_staleness,
    evaluate_trade_intent_safety,
)


def test_market_data_staleness_passes_matching_recent_source_bars() -> None:
    signal = {
        "as_of_date": "2026-05-29",
        "source_bars": {
            "AAPL": {"timestamp": "2026-05-29T13:30:00"},
            "GLD": {"timestamp": "2026-05-29T13:30:00"},
        },
    }

    report = evaluate_market_data_staleness(
        signal,
        generated_date=__import__("datetime").date(2026, 6, 1),
        max_calendar_lag_days=5,
    )

    assert report["status"] == "pass"
    assert report["halt_required"] is False
    assert report["observed_lag_days"] == 3


def test_market_data_staleness_halts_on_old_or_mismatched_bars() -> None:
    signal = {
        "as_of_date": "2026-05-20",
        "source_bars": {"AAPL": {"timestamp": "2026-05-19T13:30:00"}},
    }

    report = evaluate_market_data_staleness(
        signal,
        generated_date=__import__("datetime").date(2026, 6, 1),
        max_calendar_lag_days=5,
    )

    assert report["halt_required"] is True
    assert "market_data_calendar_lag_above_limit" in report["blockers"]
    assert "source_bar_date_mismatch" in report["blockers"]


def test_market_data_staleness_blocks_malformed_as_of_date() -> None:
    signal = {
        "as_of_date": "not-a-date",
        "source_bars": {"AAPL": {"timestamp": "2026-05-29T13:30:00"}},
    }

    report = evaluate_market_data_staleness(
        signal,
        generated_date=__import__("datetime").date(2026, 6, 1),
        max_calendar_lag_days=5,
    )

    assert report["status"] == "blocked"
    assert report["halt_required"] is True
    assert report["blockers"] == ["paper_signal_as_of_date_invalid"]


def test_drift_monitor_halts_on_loss_limits() -> None:
    observations = [
        {"virtual_equity": 10000.0, "daily_return": 0.0},
        {"virtual_equity": 9100.0, "daily_return": -0.09},
    ]

    report = evaluate_drift_monitor(observations, daily_loss_halt=-0.03, drawdown_halt=-0.08)

    assert report["status"] == "halt"
    assert "daily_loss_halt_triggered" in report["blockers"]
    assert "drawdown_halt_triggered" in report["blockers"]


def test_trade_intent_safety_requires_order_created_false() -> None:
    report = evaluate_trade_intent_safety(
        [{"trade_intents": [{"symbol": "AAPL", "order_created": True}]}]
    )

    assert report["halt_required"] is True
    assert report["blockers"] == ["trade_intent_order_created_not_false"]


def test_trade_intent_safety_rejects_authorization_flags() -> None:
    report = evaluate_trade_intent_safety(
        [
            {
                "trade_intents": [
                    {
                        "symbol": "AAPL",
                        "order_created": False,
                        "paper_api_authorized": True,
                    },
                    {
                        "symbol": "GLD",
                        "order_created": False,
                        "live_trading_authorized": True,
                    },
                ]
            }
        ]
    )

    assert report["halt_required"] is True
    assert report["blockers"] == ["trade_intent_authorization_flag_present"]


def test_trade_intent_safety_fail_closes_when_signal_requires_intent_log() -> None:
    report = evaluate_trade_intent_safety([], require_trade_intents=True)

    assert report["status"] == "halt"
    assert report["halt_required"] is True
    assert report["blockers"] == ["paper_trade_intent_log_missing_for_trade_intent_safety"]


def test_build_report_fail_closes_missing_logs_when_paper_signal_exists(tmp_path: Path) -> None:
    signal = tmp_path / "signal.json"
    signal.write_text(
        json.dumps(
            {
                "as_of_date": "2026-05-29",
                "source_bars": {"AAPL": {"timestamp": "2026-05-29T13:30:00"}},
            }
        ),
        encoding="utf-8",
    )
    args = argparse.Namespace(
        paper_signal=str(signal),
        observation_log=str(tmp_path / "missing-observation.jsonl"),
        trade_intent_log=str(tmp_path / "missing-intents.jsonl"),
        manual_halt_file=str(tmp_path / "halt.flag"),
        output=str(tmp_path / "report.json"),
        markdown=str(tmp_path / "report.md"),
        max_calendar_lag_days=999,
        min_observation_days=1,
        daily_loss_halt=-0.03,
        drawdown_halt=-0.08,
    )

    report = build_report(args)

    assert report["summary"]["status"] == "halt"
    assert report["summary"]["halt_required"] is True
    assert report["summary"]["drift_monitor"] == "blocked"
    assert "paper_observation_log_missing_for_drift_monitor" in report["blockers"]
    assert "paper_trade_intent_log_missing_for_trade_intent_safety" in report["blockers"]


def test_build_report_blocks_malformed_json_inputs_without_traceback(tmp_path: Path) -> None:
    signal = tmp_path / "signal.json"
    observation = tmp_path / "observation.jsonl"
    intent = tmp_path / "intent.jsonl"
    signal.write_text("{not valid json", encoding="utf-8")
    observation.write_text("{not valid json\n", encoding="utf-8")
    intent.write_text("[]\n", encoding="utf-8")
    args = argparse.Namespace(
        paper_signal=str(signal),
        observation_log=str(observation),
        trade_intent_log=str(intent),
        manual_halt_file=str(tmp_path / "halt.flag"),
        output=str(tmp_path / "report.json"),
        markdown=str(tmp_path / "report.md"),
        max_calendar_lag_days=999,
        min_observation_days=1,
        daily_loss_halt=-0.03,
        drawdown_halt=-0.08,
    )

    report = build_report(args)

    assert report["summary"]["status"] == "halt"
    assert "paper_signal_json_invalid_for_operational_risk_gate" in report["blockers"]
    assert "paper_observation_log_json_invalid" in report["blockers"]
    assert "paper_trade_intent_log_json_invalid" in report["blockers"]


def test_build_report_writes_monitoring_summary_without_orders(tmp_path: Path) -> None:
    signal = tmp_path / "signal.json"
    observation = tmp_path / "observation.jsonl"
    intent = tmp_path / "intent.jsonl"
    signal.write_text(
        json.dumps(
            {
                "as_of_date": "2026-05-29",
                "source_bars": {"AAPL": {"timestamp": "2026-05-29T13:30:00"}},
            }
        ),
        encoding="utf-8",
    )
    observation.write_text(
        json.dumps({"virtual_equity": 10000.0, "daily_return": 0.0}) + "\n",
        encoding="utf-8",
    )
    intent.write_text(
        json.dumps({"trade_intents": [{"symbol": "AAPL", "order_created": False}]}) + "\n",
        encoding="utf-8",
    )
    args = argparse.Namespace(
        paper_signal=str(signal),
        observation_log=str(observation),
        trade_intent_log=str(intent),
        manual_halt_file=str(tmp_path / "halt.flag"),
        output=str(tmp_path / "report.json"),
        markdown=str(tmp_path / "report.md"),
        max_calendar_lag_days=999,
        min_observation_days=1,
        daily_loss_halt=-0.03,
        drawdown_halt=-0.08,
    )

    report = build_report(args)

    assert report["summary"]["status"] == "monitoring"
    assert report["summary"]["order_created"] is False
    assert report["live_trading_authorized"] is False
