"""Evaluate no-order operational risk gates for paper observation.

This report is intentionally defensive: it can only halt or block promotion. It
never creates orders, connects to a broker, reads credentials, or authorizes live
trading.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping, Sequence
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

DEFAULT_PAPER_SIGNAL = "reports/paper-dry-run-signal-latest.json"
DEFAULT_OBSERVATION_LOG = "reports/paper-observation-log.jsonl"
DEFAULT_TRADE_INTENT_LOG = "reports/paper-trade-intent-log.jsonl"
DEFAULT_MANUAL_HALT_FILE = ".omx/state/manual-kill-switch.flag"
DEFAULT_OUTPUT = ".omx/reports/operational-risk-gate-latest.json"
DEFAULT_MARKDOWN = ".omx/reports/operational-risk-gate-latest.md"


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate no-order operational risk gates.")
    parser.add_argument("--paper-signal", default=DEFAULT_PAPER_SIGNAL)
    parser.add_argument("--observation-log", default=DEFAULT_OBSERVATION_LOG)
    parser.add_argument("--trade-intent-log", default=DEFAULT_TRADE_INTENT_LOG)
    parser.add_argument("--manual-halt-file", default=DEFAULT_MANUAL_HALT_FILE)
    parser.add_argument("--output", default=DEFAULT_OUTPUT)
    parser.add_argument("--markdown", default=DEFAULT_MARKDOWN)
    parser.add_argument("--max-calendar-lag-days", type=int, default=5)
    parser.add_argument("--min-observation-days", type=int, default=1)
    parser.add_argument("--daily-loss-halt", type=float, default=-0.03)
    parser.add_argument("--drawdown-halt", type=float, default=-0.08)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    report = build_report(args)
    output = Path(args.output)
    markdown = Path(args.markdown)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    write_markdown(markdown, report)
    print(
        "operational risk status={status} halt={halt} blockers={blockers}".format(
            status=report["summary"]["status"],
            halt=report["summary"]["halt_required"],
            blockers=len(report["blockers"]),
        )
    )
    print(f"json={output}")
    print(f"markdown={markdown}")
    return 0


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    paper_signal, paper_signal_load_blockers = read_paper_signal(Path(args.paper_signal))
    observations, observation_load_blockers = read_jsonl(
        Path(args.observation_log),
        invalid_blocker="paper_observation_log_json_invalid",
    )
    trade_intents, trade_intent_load_blockers = read_jsonl(
        Path(args.trade_intent_log),
        invalid_blocker="paper_trade_intent_log_json_invalid",
    )
    generated_at = datetime.now(tz=UTC)
    staleness = evaluate_market_data_staleness(
        paper_signal,
        generated_date=generated_at.date(),
        max_calendar_lag_days=int(args.max_calendar_lag_days),
    )
    paper_signal_present = paper_signal is not None
    drift = evaluate_drift_monitor(
        observations,
        daily_loss_halt=float(args.daily_loss_halt),
        drawdown_halt=float(args.drawdown_halt),
        required_observation_days=(
            int(getattr(args, "min_observation_days", 1)) if paper_signal_present else 0
        ),
    )
    kill_switch = evaluate_kill_switch(Path(args.manual_halt_file), drift, staleness)
    trade_intent_gate = evaluate_trade_intent_safety(
        trade_intents,
        require_trade_intents=paper_signal_present,
    )
    blockers = [
        *paper_signal_load_blockers,
        *observation_load_blockers,
        *trade_intent_load_blockers,
        *staleness["blockers"],
        *drift["blockers"],
        *kill_switch["blockers"],
        *trade_intent_gate["blockers"],
    ]
    halt_required = bool(
        staleness["halt_required"]
        or drift["halt_required"]
        or kill_switch["halt_required"]
        or trade_intent_gate["halt_required"]
    )
    return {
        "status": "ok",
        "generated_at": generated_at.isoformat(),
        "safety": "operational risk gate only; no orders; no broker; no credentials; no advice",
        "live_trading_authorized": False,
        "summary": {
            "status": "halt" if halt_required else "monitoring",
            "halt_required": halt_required,
            "blockers": len(blockers),
            "market_data_staleness_gate": staleness["status"],
            "drift_monitor": drift["status"],
            "kill_switch": kill_switch["status"],
            "trade_intent_safety": trade_intent_gate["status"],
            "order_created": False,
            "live_trading_authorized": False,
        },
        "market_data_staleness_gate": staleness,
        "drift_monitor": drift,
        "kill_switch": kill_switch,
        "trade_intent_safety": trade_intent_gate,
        "blockers": blockers,
        "required_next_evidence": [
            "Keep collecting no-order paper observations through the 2026-06-16 "
            "live-pilot review target.",
            "Review any halt_required=true report before changing thresholds.",
            "Before broker sandbox work, add latency, idempotency, partial-fill, and "
            "reconciliation tests.",
        ],
    }


def read_paper_signal(path: Path) -> tuple[dict[str, Any] | None, list[str]]:
    if not path.exists():
        return None, []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None, ["paper_signal_json_invalid_for_operational_risk_gate"]
    if not isinstance(payload, dict):
        return None, ["paper_signal_json_shape_invalid_for_operational_risk_gate"]
    return payload, []


def read_jsonl(path: Path, *, invalid_blocker: str) -> tuple[list[dict[str, Any]], list[str]]:
    if not path.exists():
        return [], []
    rows: list[dict[str, Any]] = []
    blockers: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped:
            try:
                payload = json.loads(stripped)
            except json.JSONDecodeError:
                blockers.append(invalid_blocker)
                continue
            if isinstance(payload, dict):
                rows.append(payload)
            else:
                blockers.append(invalid_blocker)
    return rows, sorted(set(blockers))


def evaluate_market_data_staleness(
    paper_signal: Mapping[str, Any] | None,
    *,
    generated_date: date,
    max_calendar_lag_days: int,
) -> dict[str, Any]:
    blockers: list[str] = []
    if paper_signal is None:
        return {
            "status": "blocked",
            "halt_required": True,
            "blockers": ["paper_signal_missing_for_staleness_gate"],
            "max_calendar_lag_days": max_calendar_lag_days,
            "observed_lag_days": None,
            "source_bar_dates": {},
        }
    raw_as_of = paper_signal.get("as_of_date")
    try:
        as_of = date.fromisoformat(str(raw_as_of))
    except ValueError:
        return {
            "status": "blocked",
            "halt_required": True,
            "blockers": ["paper_signal_as_of_date_invalid"],
            "max_calendar_lag_days": max_calendar_lag_days,
            "observed_lag_days": None,
            "as_of_date": raw_as_of,
            "source_bar_dates": {},
            "stale_symbols": [],
        }
    observed_lag_days = (generated_date - as_of).days
    if observed_lag_days < 0:
        blockers.append("paper_signal_as_of_date_in_future")
    if observed_lag_days > max_calendar_lag_days:
        blockers.append("market_data_calendar_lag_above_limit")
    source_bar_dates = extract_source_bar_dates(paper_signal)
    stale_symbols = [symbol for symbol, bar_date in source_bar_dates.items() if bar_date != as_of]
    if stale_symbols:
        blockers.append("source_bar_date_mismatch")
    if not source_bar_dates:
        blockers.append("source_bar_metadata_missing")
    return {
        "status": "pass" if not blockers else "blocked",
        "halt_required": bool(blockers),
        "blockers": blockers,
        "max_calendar_lag_days": max_calendar_lag_days,
        "observed_lag_days": observed_lag_days,
        "as_of_date": as_of.isoformat(),
        "source_bar_dates": {
            symbol: value.isoformat() for symbol, value in source_bar_dates.items()
        },
        "stale_symbols": stale_symbols,
    }


def extract_source_bar_dates(paper_signal: Mapping[str, Any]) -> dict[str, date]:
    source_bars = paper_signal.get("source_bars", {})
    if not isinstance(source_bars, Mapping):
        return {}
    dates: dict[str, date] = {}
    for symbol, raw_bar in source_bars.items():
        if not isinstance(raw_bar, Mapping):
            continue
        timestamp = raw_bar.get("timestamp")
        if timestamp is None:
            continue
        try:
            dates[str(symbol)] = datetime.fromisoformat(str(timestamp)).date()
        except ValueError:
            continue
    return dates


def evaluate_drift_monitor(
    observations: Sequence[Mapping[str, Any]],
    *,
    daily_loss_halt: float,
    drawdown_halt: float,
    required_observation_days: int = 0,
) -> dict[str, Any]:
    if not observations:
        blockers = ["paper_observation_log_missing_for_drift_monitor"]
        halt_required = required_observation_days > 0
        return {
            "status": "blocked" if halt_required else "collecting",
            "halt_required": halt_required,
            "blockers": blockers,
            "observation_days": 0,
            "required_observation_days": required_observation_days,
            "max_drawdown": 0.0,
            "worst_daily_return": 0.0,
            "daily_loss_halt": daily_loss_halt,
            "drawdown_halt": drawdown_halt,
        }
    equities = [float(row.get("virtual_equity", 0.0) or 0.0) for row in observations]
    daily_returns = [float(row.get("daily_return", 0.0) or 0.0) for row in observations]
    max_drawdown = compute_max_drawdown(equities)
    worst_daily_return = min(daily_returns) if daily_returns else 0.0
    blockers: list[str] = []
    if len(observations) < required_observation_days:
        blockers.append("paper_observation_days_below_required")
    if worst_daily_return <= daily_loss_halt:
        blockers.append("daily_loss_halt_triggered")
    if max_drawdown <= drawdown_halt:
        blockers.append("drawdown_halt_triggered")
    status = "pass"
    if "paper_observation_days_below_required" in blockers:
        status = "blocked"
    elif blockers:
        status = "halt"
    return {
        "status": status,
        "halt_required": bool(blockers),
        "blockers": blockers,
        "observation_days": len(observations),
        "required_observation_days": required_observation_days,
        "max_drawdown": max_drawdown,
        "worst_daily_return": worst_daily_return,
        "daily_loss_halt": daily_loss_halt,
        "drawdown_halt": drawdown_halt,
    }


def compute_max_drawdown(equities: Sequence[float]) -> float:
    peak = 0.0
    worst = 0.0
    for equity in equities:
        peak = max(peak, equity)
        if peak > 0:
            worst = min(worst, equity / peak - 1.0)
    return worst


def evaluate_kill_switch(
    manual_halt_file: Path,
    drift: Mapping[str, Any],
    staleness: Mapping[str, Any],
) -> dict[str, Any]:
    blockers: list[str] = []
    manual_halt = manual_halt_file.exists()
    if manual_halt:
        blockers.append("manual_kill_switch_file_present")
    triggered_by = []
    if drift.get("halt_required"):
        triggered_by.append("drift_monitor")
    if staleness.get("halt_required"):
        triggered_by.append("market_data_staleness_gate")
    return {
        "status": "halt" if manual_halt or triggered_by else "armed",
        "halt_required": bool(manual_halt or triggered_by),
        "blockers": blockers,
        "manual_halt_file": str(manual_halt_file),
        "manual_halt_file_present": manual_halt,
        "triggered_by": triggered_by,
    }


def evaluate_trade_intent_safety(
    trade_intents: Sequence[Mapping[str, Any]],
    *,
    require_trade_intents: bool = False,
) -> dict[str, Any]:
    blockers: list[str] = []
    if require_trade_intents and not trade_intents:
        blockers.append("paper_trade_intent_log_missing_for_trade_intent_safety")
    created_orders = []
    authorized_rows = []
    for index, row in enumerate(trade_intents):
        intents = row.get("trade_intents", [])
        if not isinstance(intents, list):
            blockers.append("trade_intents_shape_invalid")
            continue
        for intent in intents:
            if not isinstance(intent, Mapping):
                blockers.append("trade_intents_shape_invalid")
                continue
            if intent.get("order_created") is not False:
                created_orders.append(index)
            if (
                intent.get("live_trading_authorized") is True
                or intent.get("paper_api_authorized") is True
            ):
                authorized_rows.append(index)
    if created_orders:
        blockers.append("trade_intent_order_created_not_false")
    if authorized_rows:
        blockers.append("trade_intent_authorization_flag_present")
    return {
        "status": "pass" if not blockers else "halt",
        "halt_required": bool(blockers),
        "blockers": blockers,
        "trade_intent_rows": len(trade_intents),
        "created_order_rows": created_orders,
        "authorized_rows": authorized_rows,
    }


def write_markdown(path: Path, report: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    summary = report["summary"]
    lines = [
        "# Operational risk gate",
        "",
        "Safety: operational risk gate only; no orders, no broker, no credentials, no advice.",
        "",
        "## Summary",
        "",
        f"- Status: `{summary['status']}`",
        f"- Halt required: `{summary['halt_required']}`",
        f"- Market data staleness gate: `{summary['market_data_staleness_gate']}`",
        f"- Drift monitor: `{summary['drift_monitor']}`",
        f"- Kill switch: `{summary['kill_switch']}`",
        f"- Trade intent safety: `{summary['trade_intent_safety']}`",
        f"- Order created: `{summary['order_created']}`",
        f"- Live trading authorized: `{summary['live_trading_authorized']}`",
        "",
        "## Blockers",
        "",
    ]
    if report["blockers"]:
        lines.extend(f"- {blocker}" for blocker in report["blockers"])
    else:
        lines.append("- none")
    lines.extend(["", "## Required next evidence", ""])
    lines.extend(f"- {item}" for item in report["required_next_evidence"])
    path.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
