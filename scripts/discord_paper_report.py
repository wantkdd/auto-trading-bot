"""Send concise no-order paper observation reports to Discord.

This notifier is reporting-only. It reads local research artifacts and posts a
summary to a user-provided Discord webhook. It never connects to a broker, reads
broker credentials, authorizes trading, or creates orders.
"""

from __future__ import annotations

import argparse
import json
import os
import urllib.request
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

DEFAULT_PAPER_SUMMARY = ".omx/reports/paper-observation-summary-latest.json"
DEFAULT_CHALLENGER_SUMMARY = ".omx/reports/paper-challenger-observation-summary-latest.json"
DEFAULT_PREVIEW = ".omx/reports/no-order-preview-latest.json"
DEFAULT_READINESS = ".omx/reports/live-readiness-gate-latest.json"
DEFAULT_GATE_STATUS = ".omx/reports/no-order-gate-status-latest.json"
DEFAULT_DYNAMIC_UNIVERSE = ".omx/reports/us-dynamic-liquid-universe-latest.json"
DEFAULT_MARKET_SCAN = ".omx/reports/market-universe-scan-latest.json"
DEFAULT_CHALLENGER_SELECTION = ".omx/reports/paper-challenger-selection-latest.json"
DEFAULT_OUTPUT = ".omx/reports/discord-paper-report-latest.json"
DEFAULT_MARKDOWN = ".omx/reports/discord-paper-report-latest.md"
DISCORD_LIMIT = 2000


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Send no-order paper report to Discord.")
    parser.add_argument("--webhook-url", default=os.environ.get("DISCORD_WEBHOOK_URL", ""))
    parser.add_argument("--paper-summary", default=DEFAULT_PAPER_SUMMARY)
    parser.add_argument("--challenger-summary", default=DEFAULT_CHALLENGER_SUMMARY)
    parser.add_argument("--no-order-preview", default=DEFAULT_PREVIEW)
    parser.add_argument("--readiness", default=DEFAULT_READINESS)
    parser.add_argument("--gate-status", default=DEFAULT_GATE_STATUS)
    parser.add_argument("--dynamic-universe", default=DEFAULT_DYNAMIC_UNIVERSE)
    parser.add_argument("--market-scan", default=DEFAULT_MARKET_SCAN)
    parser.add_argument("--challenger-selection", default=DEFAULT_CHALLENGER_SELECTION)
    parser.add_argument("--run-url", default=os.environ.get("GITHUB_RUN_URL", ""))
    parser.add_argument("--output", default=DEFAULT_OUTPUT)
    parser.add_argument("--markdown", default=DEFAULT_MARKDOWN)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--weekly-day", type=int, default=4, help="0=Monday ... 4=Friday")
    parser.add_argument("--final-observed-days", type=int, default=15)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    report = build_report(args)
    write_outputs(report, Path(args.output), Path(args.markdown))
    if not args.dry_run and args.webhook_url:
        post_discord(args.webhook_url, report["message"])
        sent = True
    else:
        sent = False
    print(
        "discord paper report sent={sent} sections={sections} length={length}".format(
            sent=sent,
            sections=",".join(report["sections"]),
            length=len(report["message"]),
        )
    )
    print(f"json={args.output}")
    print(f"markdown={args.markdown}")
    return 0


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    paper = read_json_if_exists(Path(args.paper_summary)) or {}
    challenger = read_json_if_exists(Path(args.challenger_summary)) or {}
    preview = read_json_if_exists(Path(args.no_order_preview)) or {}
    readiness = read_json_if_exists(Path(args.readiness)) or {}
    gate_status = read_json_if_exists(Path(args.gate_status)) or {}
    dynamic_universe = read_json_if_exists(Path(args.dynamic_universe)) or {}
    market_scan = read_json_if_exists(Path(args.market_scan)) or {}
    challenger_selection = read_json_if_exists(Path(args.challenger_selection)) or {}
    sections = report_sections(
        paper, weekly_day=args.weekly_day, final_days=args.final_observed_days
    )
    message = render_message(
        paper=paper,
        challenger=challenger,
        preview=preview,
        readiness=readiness,
        gate_status=gate_status,
        dynamic_universe=dynamic_universe,
        market_scan=market_scan,
        challenger_selection=challenger_selection,
        sections=sections,
        run_url=args.run_url,
        final_days=args.final_observed_days,
    )
    return {
        "status": "ok",
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "safety": "Discord report only; no orders; no broker; no credentials; no advice",
        "live_trading_authorized": False,
        "sections": sections,
        "message": trim_message(message),
        "inputs": {
            "paper_summary": str(args.paper_summary),
            "challenger_summary": str(args.challenger_summary),
            "no_order_preview": str(args.no_order_preview),
            "readiness": str(args.readiness),
            "gate_status": str(args.gate_status),
            "dynamic_universe": str(args.dynamic_universe),
            "market_scan": str(args.market_scan),
            "challenger_selection": str(args.challenger_selection),
        },
    }


def report_sections(
    paper: Mapping[str, Any], *, weekly_day: int, final_days: int
) -> list[str]:
    sections = ["daily"]
    latest = str(paper.get("latest_as_of_date") or "")
    try:
        if datetime.fromisoformat(latest).date().weekday() == weekly_day:
            sections.append("weekly")
    except ValueError:
        pass
    if int(paper.get("observed_days", 0) or 0) >= final_days:
        sections.append("final")
    return sections


def render_message(
    *,
    paper: Mapping[str, Any],
    challenger: Mapping[str, Any],
    preview: Mapping[str, Any],
    readiness: Mapping[str, Any],
    gate_status: Mapping[str, Any],
    dynamic_universe: Mapping[str, Any],
    market_scan: Mapping[str, Any],
    challenger_selection: Mapping[str, Any],
    sections: Sequence[str],
    run_url: str,
    final_days: int,
) -> str:
    preview_summary = mapping(preview.get("summary"))
    readiness_summary = mapping(readiness.get("summary"))
    gate_summary = mapping(gate_status.get("summary"))
    dynamic_summary = mapping(dynamic_universe.get("summary"))
    dynamic_first_symbols = dynamic_universe.get("top_selected_symbols", [])
    if not isinstance(dynamic_first_symbols, list):
        dynamic_first_symbols = []
    market_summary = mapping(market_scan.get("summary"))
    challenger_selection_summary = mapping(challenger_selection.get("summary"))
    title = "📊 자동매매 가정 일일 리포트 (NO-ORDER)"
    lines = [
        title,
        "실거래/브로커/API주문 없음. 오늘 종가 기준으로 '매매했다면' 로그만 기록합니다.",
        "",
        "**Champion 관찰**",
        f"- 전략: `{paper.get('latest_strategy', 'unknown')}`",
        "- 관찰일: `{observed} / {required}`".format(
            observed=paper.get("observed_days", "unknown"),
            required=paper.get("required_days", "unknown"),
        ),
        f"- 가상자산: `{money(paper.get('latest_virtual_equity'))}`",
        f"- 누적수익률: `{pct(paper.get('total_return_since_first_observation'))}`",
        f"- 최대낙폭: `{pct(paper.get('max_drawdown_since_first_observation'))}`",
        "",
        "**오늘 매매 가정**",
        f"- 판단: `{preview_summary.get('decision', 'unknown')}`",
        f"- would buy/sell 통과: `{preview_summary.get('accepted', 'unknown')}`건",
        f"- 거절: `{preview_summary.get('rejected', 'unknown')}`건",
        f"- 가정 거래금액: `{money(preview_summary.get('total_notional'))}`",
        "",
        "**시장 스캔 Challenger**",
        (
            "- 동적 universe: `{selected}`종목 선정 / "
            "`{ranked}`종목 가격검증 / `{sources}`개 원천심볼"
        ).format(
            selected=dynamic_summary.get("selected", "unknown"),
            ranked=dynamic_summary.get("ranked", "unknown"),
            sources=dynamic_summary.get("sources", "unknown"),
        ),
        "- 우선 관찰 10종목: `{symbols}`".format(
            symbols=", ".join(str(symbol) for symbol in dynamic_first_symbols[:10]) or "unknown"
        ),
        f"- 시장 top: `{market_summary.get('top_candidate', 'unknown')}`",
        "- 추적 challenger: `{strategy}`".format(
            strategy=challenger_selection_summary.get("challenger_strategy", "unknown")
        ),
        f"- challenger 관찰일: `{challenger.get('observed_days', 'unknown')}`",
        f"- challenger 가상자산: `{money(challenger.get('latest_virtual_equity'))}`",
        f"- challenger 수익률: `{pct(challenger.get('total_return_since_first_observation'))}`",
        f"- challenger MDD: `{pct(challenger.get('max_drawdown_since_first_observation'))}`",
        "",
        "**안전 게이트**",
        f"- no-order gate: `{gate_summary.get('status', 'missing')}`",
        f"- paper ready: `{readiness_summary.get('paper_dry_run_ready', 'unknown')}`",
        f"- live authorized: `{readiness.get('live_trading_authorized', False)}`",
        f"- 남은 live blockers: `{len(readiness.get('live_blockers', []))}`개",
    ]
    if "weekly" in sections:
        lines.extend(
            [
                "",
                "**주간 요약**",
                (
                    "- 주간 보고 조건 도달: 이번 주 champion/challenger 성과와 "
                    "게이트 상태를 함께 확인하세요."
                ),
                "- 자동 교체는 하지 않음: champion은 고정, challenger는 승격 후보로만 관찰합니다.",
            ]
        )
    if "final" in sections:
        lines.extend(
            [
                "",
                "**3주 최종 점검**",
                (
                    f"- `{final_days}` 관찰일 기준 도달. 실거래 직행이 아니라 "
                    "broker sandbox/법적·세무·인간승인 검토 필요."
                ),
                "- 실금액 자동매매는 아직 승인되지 않았습니다.",
            ]
        )
    if run_url:
        lines.extend(["", f"GitHub run: {run_url}"])
    return "\n".join(lines)


def mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def money(value: Any) -> str:
    if isinstance(value, int | float):
        return f"${value:,.2f}"
    return "unknown"


def pct(value: Any) -> str:
    if isinstance(value, int | float):
        return f"{value * 100:.2f}%"
    return "unknown"


def trim_message(message: str) -> str:
    if len(message) <= DISCORD_LIMIT:
        return message
    suffix = "\n…(Discord 길이 제한으로 일부 생략됨)"
    return message[: DISCORD_LIMIT - len(suffix)] + suffix


def read_json_if_exists(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else None


def write_outputs(report: Mapping[str, Any], output: Path, markdown: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    markdown.parent.mkdir(parents=True, exist_ok=True)
    markdown.write_text(str(report["message"]), encoding="utf-8")


def post_discord(webhook_url: str, message: str) -> None:
    payload = json.dumps(
        {
            "username": "Auto Trading Bot Paper Observer",
            "content": message,
            "allowed_mentions": {"parse": []},
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        webhook_url,
        data=payload,
        headers={"Content-Type": "application/json", "User-Agent": "paper-observer/0.1"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=20) as response:  # noqa: S310 - user webhook
        if response.status >= 300:
            raise RuntimeError(f"discord_webhook_failed:{response.status}")


if __name__ == "__main__":
    raise SystemExit(main())
