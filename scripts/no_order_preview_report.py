"""Preview paper trade intents through the no-order adapter contract.

This report is the daily bridge between hypothetical paper trade-intent logs and
future broker-readiness work. It never connects to a broker, reads credentials,
or creates orders.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from auto_trading_bot.broker_contract import (
    FixtureNoOrderBrokerAdapter,
    NoOrderSafetyPolicy,
    build_intents_from_trade_rows,
)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Write no-order preview report.")
    parser.add_argument("--log", default="reports/paper-trade-intent-log.jsonl")
    parser.add_argument("--output", default=".omx/reports/no-order-preview-latest.json")
    parser.add_argument("--markdown", default=".omx/reports/no-order-preview-latest.md")
    parser.add_argument("--max-order-notional", type=float, default=10_000.0)
    parser.add_argument("--max-total-notional", type=float, default=10_000.0)
    parser.add_argument("--allowed-symbols", nargs="*", default=None)
    parser.add_argument("--blocked-symbols", nargs="*", default=[])
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
        (
            "no-order preview status={status} decision={decision} "
            "accepted={accepted} rejected={rejected}"
        ).format(**report["summary"])
    )
    print(f"json={output}")
    print(f"markdown={markdown}")
    return 0


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    rows = read_jsonl(Path(args.log))
    latest = latest_intent(rows)
    if latest is None:
        return empty_report(args)
    created_at = parse_generated_at(str(latest.get("generated_at") or ""))
    trade_rows = latest.get("trade_intents", [])
    if not isinstance(trade_rows, list):
        raise SystemExit("latest trade_intents must be a list")
    target_weights = latest.get("target_weights", {})
    if not isinstance(target_weights, Mapping):
        raise SystemExit("latest target_weights must be a mapping")
    allowed_symbols = symbols_arg(args.allowed_symbols)
    if not allowed_symbols:
        allowed_symbols = frozenset(str(symbol).upper() for symbol in target_weights)
    blocked_symbols = symbols_arg(args.blocked_symbols)
    allowed_symbols = allowed_symbols - blocked_symbols
    policy = NoOrderSafetyPolicy(
        max_order_notional=args.max_order_notional,
        max_total_notional=args.max_total_notional,
        allowed_symbols=allowed_symbols,
        blocked_symbols=blocked_symbols,
    )
    intents = build_intents_from_trade_rows(trade_rows, created_at=created_at)
    plan = FixtureNoOrderBrokerAdapter(policy).preview(intents)
    plan_payload = plan.to_dict()
    return {
        "status": "ok",
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "as_of_date": latest.get("as_of_date"),
        "strategy": latest.get("strategy"),
        "paper_decision": latest.get("decision"),
        "safety": "no-order preview only; no broker; no credentials; no API calls; no orders",
        "policy": {
            "max_order_notional": args.max_order_notional,
            "max_total_notional": args.max_total_notional,
            "allowed_symbols": sorted(policy.allowed_symbols),
            "blocked_symbols": sorted(policy.blocked_symbols),
            "paper_api_authorized": False,
            "live_trading_authorized": False,
        },
        "summary": {
            "status": "ok",
            "decision": latest.get("decision"),
            "accepted": len(plan.accepted),
            "rejected": len(plan.rejected),
            "total_notional": plan.total_notional,
            "order_created": False,
            "paper_api_authorized": False,
            "live_trading_authorized": False,
        },
        "plan": plan_payload,
        "warnings": [
            "Accepted means accepted by local no-order safety checks only, not routed to a broker.",
            (
                "This report is not investment advice and does not authorize live "
                "or paper API trading."
            ),
        ],
        "live_trading_authorized": False,
        "paper_api_authorized": False,
    }


def empty_report(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "status": "no_intents",
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "safety": "no-order preview only; no broker; no credentials; no API calls; no orders",
        "policy": {
            "max_order_notional": args.max_order_notional,
            "max_total_notional": args.max_total_notional,
            "allowed_symbols": sorted(symbols_arg(args.allowed_symbols)),
            "blocked_symbols": sorted(symbols_arg(args.blocked_symbols)),
            "paper_api_authorized": False,
            "live_trading_authorized": False,
        },
        "summary": {
            "status": "no_intents",
            "decision": "none",
            "accepted": 0,
            "rejected": 0,
            "total_notional": 0.0,
            "order_created": False,
            "paper_api_authorized": False,
            "live_trading_authorized": False,
        },
        "plan": {},
        "warnings": ["No paper trade intents were available to preview."],
        "live_trading_authorized": False,
        "paper_api_authorized": False,
    }


def symbols_arg(raw: Sequence[str] | None) -> frozenset[str]:
    if not raw:
        return frozenset()
    return frozenset(symbol.strip().upper() for symbol in raw if symbol.strip())


def latest_intent(rows: Sequence[Mapping[str, Any]]) -> Mapping[str, Any] | None:
    if not rows:
        return None
    return sorted(
        rows,
        key=lambda row: (str(row.get("as_of_date", "")), str(row.get("generated_at", ""))),
    )[-1]


def parse_generated_at(value: str) -> datetime:
    if not value:
        return datetime.now(tz=UTC)
    normalized = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            payload = json.loads(line)
            if isinstance(payload, dict):
                rows.append(payload)
    return rows


def write_markdown(path: Path, report: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    summary = report["summary"]
    lines = [
        "# No-order preview report",
        "",
        "Safety: no broker, no credentials, no API calls, no orders.",
        "",
        "## Summary",
        "",
        f"- Status: `{summary['status']}`",
        f"- Paper decision: `{summary['decision']}`",
        f"- Accepted intents: `{summary['accepted']}`",
        f"- Rejected intents: `{summary['rejected']}`",
        f"- Total accepted notional: `{summary['total_notional']}`",
        f"- Order created: `{summary['order_created']}`",
        f"- Paper API authorized: `{summary['paper_api_authorized']}`",
        f"- Live trading authorized: `{summary['live_trading_authorized']}`",
        "",
        "## Accepted intents",
        "",
        "| Symbol | Side | Quantity | Reference price | Notional |",
        "| --- | --- | ---: | ---: | ---: |",
    ]
    plan = report.get("plan", {})
    accepted = plan.get("accepted", []) if isinstance(plan, Mapping) else []
    rejected = plan.get("rejected", []) if isinstance(plan, Mapping) else []
    rejection_reasons = plan.get("rejection_reasons", {}) if isinstance(plan, Mapping) else {}
    if isinstance(accepted, list):
        for row in accepted:
            if isinstance(row, Mapping):
                lines.append(intent_row(row))
    lines.extend(
        [
            "",
            "## Rejected intents",
            "",
            "| Symbol | Side | Quantity | Reference price | Notional | Reasons |",
            "| --- | --- | ---: | ---: | ---: | --- |",
        ]
    )
    if isinstance(rejected, list):
        for row in rejected:
            if isinstance(row, Mapping):
                symbol = str(row.get("symbol", ""))
                reasons = []
                if isinstance(rejection_reasons, Mapping):
                    raw_reasons = rejection_reasons.get(symbol, [])
                    if isinstance(raw_reasons, list):
                        reasons = [str(reason) for reason in raw_reasons]
                lines.append(intent_row(row, extra_columns=[", ".join(reasons) or "-"]))
    path.write_text("\n".join(lines), encoding="utf-8")


def intent_row(row: Mapping[str, Any], *, extra_columns: Sequence[str] = ()) -> str:
    cells = [
        row.get("symbol"),
        row.get("side"),
        row.get("quantity"),
        row.get("reference_price"),
        row.get("notional"),
        *extra_columns,
    ]
    return "| " + " | ".join(str(cell) for cell in cells) + " |"


if __name__ == "__main__":
    raise SystemExit(main())
