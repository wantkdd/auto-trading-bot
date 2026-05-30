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
    parser.add_argument("--run-url", default=os.environ.get("GITHUB_RUN_URL", ""))
    parser.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY", ""))
    parser.add_argument("--mode", choices=("success", "failure"), default="success")
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
    issue_state = "실패/확인 필요" if args.mode == "failure" else "정상 관찰 중"
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
