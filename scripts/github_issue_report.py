"""Create or update a GitHub issue with paper-observation status.

This helper is intended for GitHub Actions. It reports research status only; it
never places orders, reads broker credentials, or authorizes trading.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

ISSUE_TITLE = "Paper observation status / action needed"
LABELS = ("paper-observation", "automated-status")


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create/update paper observation status issue.")
    parser.add_argument("--summary", default=".omx/reports/paper-observation-summary-latest.json")
    parser.add_argument("--readiness", default=".omx/reports/live-readiness-gate-latest.json")
    parser.add_argument(
        "--dynamic-universe",
        default=".omx/reports/us-dynamic-liquid-universe-latest.json",
    )
    parser.add_argument("--market-scan", default=".omx/reports/market-universe-scan-latest.json")
    parser.add_argument("--bls-macro", default=".omx/reports/bls-macro-snapshot-latest.json")
    parser.add_argument("--no-order-preview", default=".omx/reports/no-order-preview-latest.json")
    parser.add_argument(
        "--challenger-selection",
        default=".omx/reports/paper-challenger-selection-latest.json",
    )
    parser.add_argument(
        "--challenger-summary",
        default=".omx/reports/paper-challenger-observation-summary-latest.json",
    )
    parser.add_argument(
        "--operational-risk",
        default=".omx/reports/operational-risk-gate-latest.json",
    )
    parser.add_argument(
        "--independent-price",
        default=".omx/reports/independent-price-replication-latest.json",
    )
    parser.add_argument("--run-url", default=os.environ.get("GITHUB_RUN_URL", ""))
    parser.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY", ""))
    parser.add_argument(
        "--mode",
        choices=("success", "failure", "action-needed"),
        default="success",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    if not args.repo:
        raise SystemExit("GITHUB_REPOSITORY or --repo is required")
    body = build_issue_body(args)
    ensure_labels(args.repo)
    existing = find_existing_issue(args.repo)
    if existing is None:
        create_issue(args.repo, body)
    else:
        update_issue(args.repo, existing, body)
    return 0


def build_issue_body(args: argparse.Namespace) -> str:
    summary = read_json_if_exists(Path(args.summary))
    readiness = read_json_if_exists(Path(args.readiness))
    dynamic_universe = read_json_if_exists(Path(args.dynamic_universe))
    market_scan = read_json_if_exists(Path(args.market_scan))
    bls_macro = read_json_if_exists(Path(args.bls_macro))
    no_order_preview = read_json_if_exists(Path(args.no_order_preview))
    challenger_selection = read_json_if_exists(Path(args.challenger_selection))
    challenger_observation = read_json_if_exists(Path(args.challenger_summary))
    operational_risk = read_json_if_exists(Path(args.operational_risk))
    independent_price = read_json_if_exists(Path(args.independent_price))
    observed_days = summary.get("observed_days", "unknown") if summary else "unknown"
    required_days = summary.get("required_days", "unknown") if summary else "unknown"
    status = summary.get("status", "missing_summary") if summary else "missing_summary"
    latest_date = summary.get("latest_as_of_date", "unknown") if summary else "unknown"
    latest_equity = summary.get("latest_virtual_equity", "unknown") if summary else "unknown"
    total_return = summary.get("total_return_since_first_observation") if summary else None
    drawdown = summary.get("max_drawdown_since_first_observation") if summary else None
    live_authorized = readiness.get("live_trading_authorized", False) if readiness else False
    live_blockers = (
        readiness.get("live_blockers", []) if readiness else ["readiness_report_missing"]
    )
    paper_ready = readiness.get("summary", {}).get("paper_dry_run_ready") if readiness else None
    dynamic_universe_summary = dynamic_universe.get("summary", {}) if dynamic_universe else {}
    dynamic_selected = dynamic_universe_summary.get("selected", "unknown")
    dynamic_ranked = dynamic_universe_summary.get("ranked", "unknown")
    dynamic_sources = dynamic_universe_summary.get("sources", "unknown")
    dynamic_blocked = dynamic_universe_summary.get("blocked_leveraged_or_inverse", "unknown")
    dynamic_first_symbols = (
        dynamic_universe.get("top_selected_symbols", []) if dynamic_universe else []
    )
    if not isinstance(dynamic_first_symbols, list):
        dynamic_first_symbols = []
    dynamic_first_10 = ", ".join(str(symbol) for symbol in dynamic_first_symbols[:10]) or "unknown"
    market_summary = market_scan.get("summary", {}) if market_scan else {}
    top_market_candidate = market_summary.get("top_candidate", "unknown")
    market_passed = market_summary.get("passed", "unknown")
    market_symbols = market_summary.get("symbols", "unknown")
    bls_summary = bls_macro.get("summary", {}) if bls_macro else {}
    bls_status = bls_summary.get("status", "missing")
    bls_latest_points = bls_summary.get("latest_points", "unknown")
    no_order_summary = no_order_preview.get("summary", {}) if no_order_preview else {}
    no_order_status = no_order_summary.get("status", "missing")
    no_order_accepted = no_order_summary.get("accepted", "unknown")
    no_order_rejected = no_order_summary.get("rejected", "unknown")
    no_order_total_notional = no_order_summary.get("total_notional", "unknown")
    no_order_created = no_order_summary.get("order_created", False)
    challenger_summary = challenger_selection.get("summary", {}) if challenger_selection else {}
    challenger_status = challenger_summary.get("status", "missing")
    challenger_strategy = challenger_summary.get("challenger_strategy", "unknown")
    primary_strategy_changed = challenger_summary.get("primary_strategy_changed", "unknown")
    challenger_observation_status = (
        challenger_observation.get("status", "missing")
        if challenger_observation
        else "missing"
    )
    challenger_observed_days = (
        challenger_observation.get("observed_days", "unknown")
        if challenger_observation
        else "unknown"
    )
    challenger_latest_equity = (
        challenger_observation.get("latest_virtual_equity", "unknown")
        if challenger_observation
        else "unknown"
    )
    challenger_total_return = (
        challenger_observation.get("total_return_since_first_observation")
        if challenger_observation
        else None
    )
    challenger_drawdown = (
        challenger_observation.get("max_drawdown_since_first_observation")
        if challenger_observation
        else None
    )
    operational_summary = operational_risk.get("summary", {}) if operational_risk else {}
    operational_status = operational_summary.get("status", "missing")
    operational_halt = operational_summary.get("halt_required", "unknown")
    staleness_status = operational_summary.get("market_data_staleness_gate", "unknown")
    drift_status = operational_summary.get("drift_monitor", "unknown")
    kill_switch_status = operational_summary.get("kill_switch", "unknown")
    independent_price_summary = independent_price.get("summary", {}) if independent_price else {}
    independent_price_status = independent_price_summary.get("status", "missing")
    independent_price_provider = independent_price_summary.get("provider", "unknown")
    independent_price_symbols = independent_price_summary.get("symbols_checked", "unknown")
    issue_state = {
        "failure": "실패/확인 필요",
        "action-needed": "게이트 확인 필요",
        "success": "정상 관찰 중",
    }[args.mode]
    return "\n".join(
        [
            "# Paper observation status",
            "",
            f"- 상태: **{issue_state}**",
            f"- 관찰 상태: `{status}`",
            f"- 관찰일: `{observed_days} / {required_days}`",
            f"- 최신 as-of: `{latest_date}`",
            f"- 가상자산: `{latest_equity}`",
            f"- 누적수익률: `{format_percent(total_return)}`",
            f"- 최대낙폭: `{format_percent(drawdown)}`",
            f"- paper ready: `{paper_ready}`",
            f"- live trading authorized: `{live_authorized}`",
            (
                "- 동적 universe 선정/검증/원천: "
                f"`{dynamic_selected} / {dynamic_ranked} / {dynamic_sources}`"
            ),
            f"- 동적 universe 레버리지/인버스 차단: `{dynamic_blocked}`",
            f"- 우선 관찰 10종목: `{dynamic_first_10}`",
            f"- 시장 후보군 스캔 종목수: `{market_symbols}`",
            f"- 시장 후보군 통과 후보: `{market_passed}`",
            f"- 시장 후보군 top candidate: `{top_market_candidate}`",
            f"- BLS macro status: `{bls_status}`",
            f"- BLS macro latest points: `{bls_latest_points}`",
            f"- no-order preview status: `{no_order_status}`",
            f"- no-order accepted/rejected: `{no_order_accepted} / {no_order_rejected}`",
            f"- no-order accepted notional: `{no_order_total_notional}`",
            f"- challenger status: `{challenger_status}`",
            f"- challenger strategy: `{challenger_strategy}`",
            f"- primary strategy changed: `{primary_strategy_changed}`",
            f"- challenger observation status: `{challenger_observation_status}`",
            f"- challenger observed days: `{challenger_observed_days}`",
            f"- challenger virtual equity: `{challenger_latest_equity}`",
            f"- challenger total return: `{format_percent(challenger_total_return)}`",
            f"- challenger max drawdown: `{format_percent(challenger_drawdown)}`",
            f"- operational risk status: `{operational_status}`",
            f"- operational halt required: `{operational_halt}`",
            f"- market-data staleness gate: `{staleness_status}`",
            f"- drift monitor: `{drift_status}`",
            f"- kill switch: `{kill_switch_status}`",
            f"- independent price status: `{independent_price_status}`",
            f"- independent price provider: `{independent_price_provider}`",
            f"- independent price symbols checked: `{independent_price_symbols}`",
            f"- order created: `{no_order_created}`",
            f"- GitHub run: {args.run_url or 'n/a'}",
            "",
            "## 남은 live blockers",
            "",
            *[f"- `{blocker}`" for blocker in live_blockers],
            "",
            "## 안전 경계",
            "",
            (
                "이 이슈는 paper 관찰 상태 보고용입니다. 실주문, 브로커 연결, "
                "계좌/비밀키, 투자조언을 승인하지 않습니다."
            ),
        ]
    )


def read_json_if_exists(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return None
    return payload


def format_percent(value: Any) -> str:
    if isinstance(value, int | float):
        return f"{value * 100:.2f}%"
    return "unknown"


def ensure_labels(repo: str) -> None:
    for label in LABELS:
        run_gh(
            [
                "label",
                "create",
                label,
                "--repo",
                repo,
                "--color",
                "5319e7",
                "--description",
                "Automated paper-observation status",
            ],
            check=False,
        )


def find_existing_issue(repo: str) -> str | None:
    result = run_gh(
        [
            "issue",
            "list",
            "--repo",
            repo,
            "--state",
            "open",
            "--label",
            LABELS[0],
            "--json",
            "number,title",
            "--limit",
            "50",
        ]
    )
    issues = json.loads(result.stdout or "[]")
    for issue in issues:
        if isinstance(issue, Mapping) and issue.get("title") == ISSUE_TITLE:
            return str(issue["number"])
    return None


def create_issue(repo: str, body: str) -> None:
    run_gh(
        [
            "issue",
            "create",
            "--repo",
            repo,
            "--title",
            ISSUE_TITLE,
            "--body",
            body,
            "--label",
            ",".join(LABELS),
        ]
    )


def update_issue(repo: str, number: str, body: str) -> None:
    run_gh(["issue", "edit", number, "--repo", repo, "--body", body])


def run_gh(args: Sequence[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["gh", *args],
        text=True,
        capture_output=True,
        check=check,
    )


if __name__ == "__main__":
    raise SystemExit(main())
