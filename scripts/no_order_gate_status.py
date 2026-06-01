"""Summarize no-order gate reports for GitHub status routing.

This helper never connects to brokers, reads broker credentials, or submits orders.
It only reads local JSON reports produced by no-order research gates.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

DEFAULT_OPERATIONAL = ".omx/reports/operational-risk-gate-latest.json"
DEFAULT_INDEPENDENT_PRICE = ".omx/reports/independent-price-replication-latest.json"
DEFAULT_READINESS = ".omx/reports/live-readiness-gate-latest.json"
DEFAULT_OUTPUT = ".omx/reports/no-order-gate-status-latest.json"
DEFAULT_MARKDOWN = ".omx/reports/no-order-gate-status-latest.md"


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Summarize no-order gate status.")
    parser.add_argument("--operational-risk", default=DEFAULT_OPERATIONAL)
    parser.add_argument("--independent-price", default=DEFAULT_INDEPENDENT_PRICE)
    parser.add_argument("--readiness", default=DEFAULT_READINESS)
    parser.add_argument("--output", default=DEFAULT_OUTPUT)
    parser.add_argument("--markdown", default=DEFAULT_MARKDOWN)
    parser.add_argument(
        "--github-output",
        default="",
        help="Optional GitHub Actions output file path for mode/action_required.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    report = build_report(args)
    output = Path(args.output)
    markdown = Path(args.markdown)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    write_markdown(markdown, report)
    if args.github_output:
        append_github_output(Path(args.github_output), report)
    print(
        (
            "no-order gate status={status} "
            "action_required={action_required} blockers={blockers}"
        ).format(
            status=report["summary"]["status"],
            action_required=report["summary"]["action_required"],
            blockers=len(report["blockers"]),
        )
    )
    print(f"json={output}")
    print(f"markdown={markdown}")
    return 0


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    operational = read_json_if_exists(Path(args.operational_risk))
    independent = read_json_if_exists(Path(args.independent_price))
    readiness = read_json_if_exists(Path(args.readiness))
    blockers = [
        *operational_blockers(operational),
        *independent_price_blockers(independent),
        *readiness_blockers(readiness),
    ]
    action_required = bool(blockers)
    return {
        "status": "ok",
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "safety": "status router only; no orders; no broker; no credentials; no advice",
        "live_trading_authorized": False,
        "summary": {
            "status": "action_needed" if action_required else "pass",
            "mode": "action-needed" if action_required else "success",
            "action_required": action_required,
            "operational_risk_status": summary_value(operational, "status"),
            "operational_halt_required": summary_value(operational, "halt_required"),
            "independent_price_status": summary_value(independent, "status"),
            "readiness_status": summary_value(readiness, "live_readiness_status"),
            "live_trading_authorized": False,
        },
        "inputs": {
            "operational_risk": str(args.operational_risk),
            "independent_price": str(args.independent_price),
            "readiness": str(args.readiness),
        },
        "blockers": blockers,
    }


def summary_value(report: Mapping[str, Any] | None, key: str) -> Any:
    if report is None:
        return "missing"
    summary = report.get("summary", {})
    if not isinstance(summary, Mapping):
        return "invalid_summary"
    return summary.get(key, "missing")


def operational_blockers(report: Mapping[str, Any] | None) -> list[str]:
    if report is None:
        return ["operational_risk_gate_report_missing"]
    summary = report.get("summary", {})
    if not isinstance(summary, Mapping):
        return ["operational_risk_gate_summary_invalid"]
    blockers: list[str] = []
    if summary.get("status") != "monitoring":
        blockers.append("operational_risk_gate_not_monitoring")
    if summary.get("halt_required") is not False:
        blockers.append("operational_risk_gate_halt_required")
    if summary.get("market_data_staleness_gate") != "pass":
        blockers.append("market_data_staleness_gate_not_passing")
    if summary.get("trade_intent_safety") != "pass":
        blockers.append("trade_intent_safety_not_passing")
    if summary.get("order_created") is not False:
        blockers.append("operational_gate_order_created_not_false")
    if summary.get("live_trading_authorized") is not False:
        blockers.append("operational_gate_live_trading_authorized_not_false")
    return blockers


def independent_price_blockers(report: Mapping[str, Any] | None) -> list[str]:
    if report is None:
        return ["independent_price_replication_report_missing"]
    summary = report.get("summary", {})
    if not isinstance(summary, Mapping):
        return ["independent_price_replication_summary_invalid"]
    if summary.get("status") != "pass" or int(summary.get("symbols_checked", 0) or 0) <= 0:
        return ["independent_price_replication_not_passing"]
    return []


def readiness_blockers(report: Mapping[str, Any] | None) -> list[str]:
    if report is None:
        return ["live_readiness_report_missing"]
    blockers: list[str] = []
    if report.get("live_trading_authorized") is not False:
        blockers.append("live_readiness_authorized_trading_unexpectedly")
    summary = report.get("summary", {})
    if not isinstance(summary, Mapping):
        blockers.append("live_readiness_summary_invalid")
    elif summary.get("live_trading_authorized") is not False:
        blockers.append("live_readiness_summary_authorized_trading_unexpectedly")
    return blockers


def read_json_if_exists(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else None


def append_github_output(path: Path, report: Mapping[str, Any]) -> None:
    summary = report["summary"]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(f"mode={summary['mode']}\n")
        handle.write(f"action_required={str(summary['action_required']).lower()}\n")


def write_markdown(path: Path, report: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    summary = report["summary"]
    lines = [
        "# No-order gate status",
        "",
        "Safety: status router only; no orders, no broker, no credentials, no advice.",
        "",
        "## Summary",
        "",
        f"- Status: `{summary['status']}`",
        f"- GitHub issue mode: `{summary['mode']}`",
        f"- Action required: `{summary['action_required']}`",
        f"- Operational risk status: `{summary['operational_risk_status']}`",
        f"- Operational halt required: `{summary['operational_halt_required']}`",
        f"- Independent price status: `{summary['independent_price_status']}`",
        f"- Live trading authorized: `{summary['live_trading_authorized']}`",
        "",
        "## Blockers",
        "",
    ]
    lines.extend(f"- {blocker}" for blocker in report["blockers"] or ["none"])
    path.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
