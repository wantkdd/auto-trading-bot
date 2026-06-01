"""Generate a broker API attachment preflight report.

The report converts accepted no-order preview intents into broker-neutral order
tickets and checks whether all required approvals exist. It never imports a
broker SDK, reads credentials, opens a network connection, or submits orders.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from auto_trading_bot.execution_contract import (
    ExecutionApproval,
    ExecutionPreflightPolicy,
    ExecutionVenue,
    build_tickets_from_no_order_plan,
    evaluate_execution_preflight,
)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Write broker execution preflight report.")
    parser.add_argument("--no-order-preview", default=".omx/reports/no-order-preview-latest.json")
    parser.add_argument(
        "--paper-summary", default=".omx/reports/paper-observation-summary-latest.json"
    )
    parser.add_argument("--output", default=".omx/reports/broker-execution-preflight-latest.json")
    parser.add_argument("--markdown", default=".omx/reports/broker-execution-preflight-latest.md")
    parser.add_argument("--environment", choices=["paper", "live"], default="paper")
    parser.add_argument("--max-order-notional", type=float, default=1_000.0)
    parser.add_argument("--max-total-notional", type=float, default=2_000.0)
    parser.add_argument("--min-paper-observation-days", type=int, default=12)
    parser.add_argument("--allowed-symbols", nargs="*", default=None)
    parser.add_argument("--blocked-symbols", nargs="*", default=[])
    parser.add_argument("--human-approved", action="store_true")
    parser.add_argument("--broker-api-connected", action="store_true")
    parser.add_argument("--account-reconciled", action="store_true")
    parser.add_argument("--market-data-fresh", action="store_true")
    parser.add_argument("--kill-switch-armed", action="store_true")
    parser.add_argument("--legal-tax-review-complete", action="store_true")
    parser.add_argument("--live-trading-authorized", action="store_true")
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
        "broker preflight status={status} tickets={tickets} blockers={blockers}".format(
            status=report["summary"]["status"],
            tickets=report["summary"]["ticket_count"],
            blockers=report["summary"]["blockers"],
        )
    )
    print(f"json={output}")
    print(f"markdown={markdown}")
    return 0


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    preview = read_json_if_exists(Path(args.no_order_preview)) or {}
    paper = read_json_if_exists(Path(args.paper_summary)) or {}
    plan = preview.get("plan", {})
    if not isinstance(plan, Mapping):
        plan = {}
    tickets = build_tickets_from_no_order_plan(plan)
    target_weights = preview.get("policy", {}).get("allowed_symbols", [])
    allowed_symbols = symbols_arg(args.allowed_symbols)
    if not allowed_symbols and isinstance(target_weights, list):
        allowed_symbols = frozenset(str(symbol).upper() for symbol in target_weights)
    blocked_symbols = symbols_arg(args.blocked_symbols)
    policy = ExecutionPreflightPolicy(
        max_order_notional=float(args.max_order_notional),
        max_total_notional=float(args.max_total_notional),
        min_paper_observation_days=int(args.min_paper_observation_days),
        allowed_symbols=allowed_symbols - blocked_symbols,
        blocked_symbols=blocked_symbols,
    )
    approval = ExecutionApproval(
        venue=ExecutionVenue(args.environment),
        human_approved=bool(args.human_approved),
        broker_api_connected=bool(args.broker_api_connected),
        account_reconciled=bool(args.account_reconciled),
        market_data_fresh=bool(args.market_data_fresh),
        kill_switch_armed=bool(args.kill_switch_armed),
        legal_tax_review_complete=bool(args.legal_tax_review_complete),
        live_trading_authorized=bool(args.live_trading_authorized),
        paper_observation_days=int(paper.get("observed_days", 0) or 0),
    )
    preflight = evaluate_execution_preflight(tickets, approval=approval, policy=policy)
    payload = preflight.to_dict()
    return {
        "status": "ok",
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "safety": payload["safety"],
        "live_trading_authorized": False,
        "paper_api_authorized": False,
        "summary": {
            "status": payload["status"],
            "ticket_count": payload["ticket_count"],
            "blockers": len(payload["blockers"]),
            "order_created": False,
            "submit_attempted": False,
            "api_attachable_after_approvals": payload["status"] != "blocked",
        },
        "preflight": payload,
        "source_reports": {
            "no_order_preview": str(args.no_order_preview),
            "paper_summary": str(args.paper_summary),
        },
        "required_before_api_attachment": [
            "Implement a broker-specific adapter that satisfies BrokerExecutionAdapter.",
            "Keep client_order_id idempotency and account reconciliation tests passing.",
            "Use broker sandbox/paper endpoint first; live endpoint remains blocked separately.",
            "Do not store broker API keys in source; use GitHub/host secrets only.",
        ],
    }


def symbols_arg(raw: Sequence[str] | None) -> frozenset[str]:
    if not raw:
        return frozenset()
    return frozenset(symbol.strip().upper() for symbol in raw if symbol.strip())


def read_json_if_exists(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else None


def write_markdown(path: Path, report: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    summary = report["summary"]
    preflight = report["preflight"]
    blockers = preflight.get("blockers", []) if isinstance(preflight, Mapping) else []
    tickets = preflight.get("tickets", []) if isinstance(preflight, Mapping) else []
    lines = [
        "# Broker execution preflight",
        "",
        "Safety: broker-neutral preflight only; no SDK, no credentials, no network, no orders.",
        "",
        "## Summary",
        "",
        f"- Status: `{summary['status']}`",
        f"- Tickets: `{summary['ticket_count']}`",
        f"- Blockers: `{summary['blockers']}`",
        f"- Order created: `{summary['order_created']}`",
        f"- Submit attempted: `{summary['submit_attempted']}`",
        "",
        "## Tickets",
        "",
        "| Client order id | Symbol | Side | Qty | Ref price | Notional |",
        "| --- | --- | --- | ---: | ---: | ---: |",
    ]
    if isinstance(tickets, list):
        for ticket in tickets:
            if isinstance(ticket, Mapping):
                row = (
                    "| {client_order_id} | {symbol} | {side} | {quantity} | "
                    "{reference_price} | {estimated_notional} |"
                )
                lines.append(row.format(**ticket))
    lines.extend(["", "## Blockers", ""])
    if isinstance(blockers, list):
        lines.extend(f"- {blocker}" for blocker in blockers or ["none"])
    path.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
