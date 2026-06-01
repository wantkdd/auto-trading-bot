"""Aggregate research evidence into a live-readiness blocker report.

This script never authorizes trading. Its purpose is to show how far an offline
candidate is from a human/legal live-trading review gate.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

try:
    from scripts.non_leveraged_universe_analysis import looks_leveraged, percent
except ModuleNotFoundError:  # pragma: no cover - direct script execution path
    from non_leveraged_universe_analysis import looks_leveraged, percent  # type: ignore[no-redef]

SEC_AUTOMATED_ADVICE_URL = "https://www.sec.gov/about/divisions-offices/office-strategic-hub-innovation-financial-technology-finhub/automated-investment-advice"
FINRA_DAY_TRADING_URL = (
    "https://www.finra.org/investors/investing/investment-products/stocks/day-trading"
)
INVESTOR_MARGIN_URL = "https://www.investor.gov/additional-resources/news-alerts/alerts-bulletins/investor-bulletin-understanding-margin-accounts"


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Summarize blockers to live trading review.")
    parser.add_argument(
        "--fundamental-report",
        default=".omx/reports/fundamental-macro-recent-gate-latest.json",
    )
    parser.add_argument("--paper-signal", default="reports/paper-dry-run-signal-latest.json")
    parser.add_argument(
        "--operational-risk-report",
        default=".omx/reports/operational-risk-gate-latest.json",
    )
    parser.add_argument(
        "--independent-price-report",
        default=".omx/reports/independent-price-replication-latest.json",
    )
    parser.add_argument("--output", default=".omx/reports/live-readiness-gate-latest.json")
    parser.add_argument("--markdown", default=".omx/reports/live-readiness-gate-latest.md")
    parser.add_argument("--min-passing-candidates", type=int, default=3)
    parser.add_argument("--max-single-asset-weight", type=float, default=0.75)
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
        "live readiness={status} paper_ready={paper_ready} blockers={blockers}".format(
            status=report["summary"]["live_readiness_status"],
            paper_ready=report["summary"]["paper_dry_run_ready"],
            blockers=len(report["live_blockers"]),
        )
    )
    print(f"json={output}")
    print(f"markdown={markdown}")
    return 0


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    fundamental_report = read_json_if_exists(Path(args.fundamental_report))
    paper_signal = read_json(Path(args.paper_signal)) if Path(args.paper_signal).exists() else None
    operational_risk_report = (
        read_json(Path(args.operational_risk_report))
        if Path(args.operational_risk_report).exists()
        else None
    )
    independent_price_report = (
        read_json(Path(args.independent_price_report))
        if Path(args.independent_price_report).exists()
        else None
    )
    candidates = tuple(fundamental_report.get("candidate_gates", ())) if fundamental_report else ()
    passed = tuple(row for row in candidates if row.get("status") == "pass")
    top = passed[0] if passed else None
    candidate_blockers = (
        ["fundamental_recent_gate_missing", "no_candidate_passed_fundamental_recent_gate"]
        if fundamental_report is None
        else candidate_readiness_blockers(
            passed,
            top,
            min_passing_candidates=args.min_passing_candidates,
            max_single_asset_weight=args.max_single_asset_weight,
        )
    )
    report_as_of = str(fundamental_report.get("as_of_date") or "") if fundamental_report else ""
    paper_blockers = paper_signal_blockers(top, paper_signal, expected_as_of=report_as_of)
    operational_blockers = operational_readiness_blockers(operational_risk_report)
    independent_price_blockers = independent_price_readiness_blockers(independent_price_report)
    live_blockers = [
        *candidate_blockers,
        *paper_blockers,
        *operational_blockers,
        *independent_price_blockers,
        "minimum_30_trading_day_paper_observation_missing",
        "tax_cost_and_liquidity_review_missing",
        "human_approval_missing",
        "legal_or_registered_adviser_review_missing_for_automated_investment_advice",
        "broker_sandbox_and_order_reconciliation_intentionally_not_connected",
        "broker_api_latency_budget_not_defined",
        "slippage_and_spread_model_not_validated_against_live_quotes",
        "partial_fill_rejection_cancel_replace_handling_missing",
        "idempotency_keys_and_duplicate_order_prevention_missing",
        "rate_limit_backoff_and_outage_recovery_missing",
        "account_position_reconciliation_missing",
        "market_hours_holiday_and_corporate_action_handling_missing",
    ]
    paper_ready = top is not None and not candidate_blockers and not paper_blockers
    return {
        "status": "ok",
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "safety": "readiness report only; no orders; no broker; no credentials; no advice",
        "live_trading_authorized": False,
        "promotion_level": "research_only" if not paper_ready else "paper_dry_run_candidate",
        "sources": {
            "sec_automated_investment_advice": SEC_AUTOMATED_ADVICE_URL,
            "finra_day_trading": FINRA_DAY_TRADING_URL,
            "sec_investor_margin_bulletin": INVESTOR_MARGIN_URL,
        },
        "summary": {
            "live_readiness_status": "blocked_before_human_review",
            "paper_dry_run_ready": paper_ready,
            "passing_candidates": len(passed),
            "top_candidate": top.get("name") if top else None,
            "top_candidate_symbols": top.get("symbols") if top else [],
            "top_candidate_weights": top.get("weights") if top else [],
            "operational_risk_status": (
                operational_risk_report.get("summary", {}).get("status")
                if operational_risk_report
                else "missing"
            ),
            "independent_price_status": (
                independent_price_report.get("summary", {}).get("status")
                if independent_price_report
                else "missing"
            ),
            "live_trading_authorized": False,
        },
        "candidate_gate": {
            "as_of_date": fundamental_report.get("as_of_date") if fundamental_report else None,
            "source_report": str(args.fundamental_report),
            "signal_present": fundamental_report is not None,
            "passing_candidates": [compact_candidate(row) for row in passed],
            "candidate_blockers": candidate_blockers,
        },
        "paper_signal_gate": {
            "source_report": str(args.paper_signal),
            "signal_present": paper_signal is not None,
            "paper_blockers": paper_blockers,
            "paper_signal": compact_paper_signal(paper_signal),
        },
        "operational_risk_gate": {
            "source_report": str(args.operational_risk_report),
            "signal_present": operational_risk_report is not None,
            "operational_blockers": operational_blockers,
            "summary": (
                operational_risk_report.get("summary") if operational_risk_report else None
            ),
        },
        "independent_price_gate": {
            "source_report": str(args.independent_price_report),
            "signal_present": independent_price_report is not None,
            "independent_price_blockers": independent_price_blockers,
            "summary": (
                independent_price_report.get("summary") if independent_price_report else None
            ),
        },
        "live_blockers": live_blockers,
        "required_next_evidence": [
            "Run at least 30 trading days of dry-run target logging with no broker connection.",
            "Replicate price history with an independent licensed or official data source.",
            "Keep operational risk gate passing: drift monitor, loss limits, stale-data halt, "
            "and manual kill switch.",
            "Define broker API latency budget, stale-quote halt, idempotent order model, "
            "partial-fill handling, and reconciliation tests before any broker sandbox.",
            "Complete tax/cost/liquidity and legal/adviser-status review before any real capital.",
        ],
    }


def operational_readiness_blockers(
    operational_risk_report: Mapping[str, Any] | None,
) -> list[str]:
    if operational_risk_report is None:
        return [
            "operational_risk_gate_missing",
            "drift_monitor_and_kill_switch_not_implemented",
            "market_data_latency_and_staleness_gate_missing",
        ]
    summary = operational_risk_report.get("summary", {})
    blockers: list[str] = []
    if summary.get("drift_monitor") not in {"pass", "collecting"}:
        blockers.append("drift_monitor_halt_or_invalid")
    if summary.get("kill_switch") not in {"armed", "halt"}:
        blockers.append("kill_switch_not_armed")
    if summary.get("market_data_staleness_gate") != "pass":
        blockers.append("market_data_staleness_gate_not_passing")
    if summary.get("halt_required") is True:
        blockers.append("operational_halt_required")
    return blockers


def independent_price_readiness_blockers(
    independent_price_report: Mapping[str, Any] | None,
) -> list[str]:
    if independent_price_report is None:
        return ["independent_non_yahoo_data_replication_missing"]
    summary = independent_price_report.get("summary", {})
    if summary.get("status") != "pass":
        return ["independent_non_yahoo_data_replication_missing"]
    if int(summary.get("symbols_checked", 0) or 0) <= 0:
        return ["independent_non_yahoo_data_replication_missing"]
    return []


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def read_json_if_exists(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return read_json(path)


def candidate_readiness_blockers(
    passed: Sequence[Mapping[str, Any]],
    top: Mapping[str, Any] | None,
    *,
    min_passing_candidates: int,
    max_single_asset_weight: float,
) -> list[str]:
    blockers: list[str] = []
    if len(passed) < min_passing_candidates:
        blockers.append("too_few_passing_candidates_for_redundancy")
    if top is None:
        blockers.append("no_candidate_passed_fundamental_recent_gate")
        return blockers
    symbols = [str(symbol) for symbol in top.get("symbols", [])]
    if any(looks_leveraged(symbol) for symbol in symbols):
        blockers.append("leveraged_or_inverse_symbol_present")
    weights = [float(weight) for weight in top.get("weights", [])]
    if weights and max(weights) > max_single_asset_weight:
        blockers.append("single_asset_concentration_above_limit")
    if float(top.get("base_worst_mdd", -1.0)) < -0.20:
        blockers.append("base_drawdown_worse_than_minus_20pct")
    if top.get("recent_regime_status") != "pass":
        blockers.append("recent_regime_gate_not_passed")
    return blockers


def paper_signal_blockers(
    top: Mapping[str, Any] | None,
    paper_signal: Mapping[str, Any] | None,
    *,
    expected_as_of: str | None = None,
) -> list[str]:
    if top is None:
        return ["paper_signal_has_no_passing_candidate_to_track"]
    if paper_signal is None:
        return ["paper_dry_run_signal_missing"]
    blockers: list[str] = []
    top_weights = dict(zip(top.get("symbols", []), top.get("weights", []), strict=False))
    signal_weights = paper_signal.get("target_weights", {})
    if not isinstance(signal_weights, Mapping) or not weights_match(top_weights, signal_weights):
        blockers.append("paper_signal_does_not_match_top_candidate")
    warnings = paper_signal.get("warnings", [])
    if not isinstance(warnings, list) or not any(
        "do not place orders" in item for item in warnings
    ):
        blockers.append("paper_signal_missing_no_order_warning")
    if expected_as_of and paper_signal.get("as_of_date") != expected_as_of:
        blockers.append("paper_signal_as_of_date_mismatch")
    safety = str(paper_signal.get("safety", "")).lower()
    if "no orders" not in safety or "no broker" not in safety:
        blockers.append("paper_signal_safety_boundary_missing")
    return blockers


def weights_match(expected: Mapping[str, Any], actual: Mapping[str, Any]) -> bool:
    if set(expected) != set(actual):
        return False
    return all(abs(float(expected[symbol]) - float(actual[symbol])) <= 1e-9 for symbol in expected)


def compact_candidate(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "name": row.get("name"),
        "symbols": row.get("symbols"),
        "weights": row.get("weights"),
        "base_median_excess": row.get("base_median_excess"),
        "base_worst_mdd": row.get("base_worst_mdd"),
        "recent_regime_status": row.get("recent_regime_status"),
        "fundamental_status": row.get("fundamental_status"),
    }


def compact_paper_signal(signal: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if signal is None:
        return None
    return {
        "as_of_date": signal.get("as_of_date"),
        "strategy": signal.get("strategy"),
        "target_weights": signal.get("target_weights"),
        "safety": signal.get("safety"),
        "warnings": signal.get("warnings"),
    }


def write_markdown(path: Path, report: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Live-readiness gate",
        "",
        "Safety: readiness report only; no orders, no broker, no credentials, no advice.",
        "",
        "## Summary",
        "",
        f"- Live trading authorized: {report['live_trading_authorized']}",
        f"- Promotion level: {report['promotion_level']}",
        f"- Paper dry-run ready: {report['summary']['paper_dry_run_ready']}",
        f"- Top candidate: {report['summary']['top_candidate']}",
        f"- Passing candidates: {report['summary']['passing_candidates']}",
        f"- Operational risk status: {report['summary']['operational_risk_status']}",
        f"- Independent price status: {report['summary']['independent_price_status']}",
        "",
        "## Passing candidates",
        "",
        "| Candidate | Weights | Median excess | Worst MDD | Fundamentals | Recent |",
        "| --- | --- | ---: | ---: | --- | --- |",
    ]
    for row in report["candidate_gate"]["passing_candidates"]:
        weights = dict(zip(row["symbols"], row["weights"], strict=False))
        lines.append(
            "| {name} | {weights} | {excess} | {mdd} | {fund} | {recent} |".format(
                name=row["name"],
                weights=weights,
                excess=percent(row["base_median_excess"]),
                mdd=percent(row["base_worst_mdd"]),
                fund=row["fundamental_status"],
                recent=row["recent_regime_status"],
            )
        )
    lines.extend(["", "## Live blockers", ""])
    for blocker in report["live_blockers"]:
        lines.append(f"- {blocker}")
    lines.extend(["", "## Required next evidence", ""])
    for item in report["required_next_evidence"]:
        lines.append(f"- {item}")
    path.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
