"""Intraday no-order monitor for broad US paper observation.

This script is reporting-only. It fetches quote snapshots, records hypothetical
state changes, and never connects to a trading venue or creates orders.
"""

from __future__ import annotations

import argparse
import json
import os
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, time
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

DEFAULT_SYMBOLS = ("SPY", "QQQ", "DIA", "AAPL", "GLD", "NVDA", "MSFT", "AMZN", "META", "TSLA")
DEFAULT_SYMBOLS_FILE = "data/universe/us_dynamic_liquid_watchlist.txt"
DEFAULT_LOG = "reports/intraday-no-order-log.jsonl"
DEFAULT_OUTPUT = ".omx/reports/intraday-no-order-latest.json"
DEFAULT_MARKDOWN = ".omx/reports/intraday-no-order-latest.md"
FINNHUB_QUOTE_URL = "https://finnhub.io/api/v1/quote"


@dataclass(frozen=True)
class QuoteSnapshot:
    symbol: str
    status: str
    current: float | None
    previous_close: float | None
    change_pct: float | None
    source_timestamp: int | None
    error: str = ""


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run intraday no-order quote monitor.")
    parser.add_argument("--symbols-file", default=DEFAULT_SYMBOLS_FILE)
    parser.add_argument("--symbols", nargs="*", default=None)
    parser.add_argument("--max-symbols", type=int, default=10)
    parser.add_argument("--log", default=DEFAULT_LOG)
    parser.add_argument("--output", default=DEFAULT_OUTPUT)
    parser.add_argument("--markdown", default=DEFAULT_MARKDOWN)
    parser.add_argument("--max-log-entries", type=int, default=200)
    parser.add_argument("--finnhub-api-key", default=os.environ.get("FINNHUB_API_KEY", ""))
    parser.add_argument("--discord-webhook-url", default=os.environ.get("DISCORD_WEBHOOK_URL", ""))
    parser.add_argument("--send-discord", action="store_true")
    parser.add_argument("--force-market-open", action="store_true")
    parser.add_argument("--now", default="")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    now = parse_now(args.now)
    report = build_report(
        args,
        now=now,
        quote_fetcher=lambda symbol, token: fetch_finnhub_quote(symbol, token),
    )
    write_outputs(report, Path(args.output), Path(args.markdown))
    if report["summary"]["status"] == "ok":
        append_log(Path(args.log), report, max_entries=int(args.max_log_entries))
    if args.send_discord and args.discord_webhook_url and should_send_discord(report):
        post_discord(args.discord_webhook_url, render_discord_message(report))
    print(
        "intraday monitor status={status} market_open={market_open} symbols={symbols} "
        "changes={changes} notable={notable}".format(**report["summary"])
    )
    print(f"json={args.output}")
    print(f"markdown={args.markdown}")
    return 0


def parse_now(value: str) -> datetime:
    if not value:
        return datetime.now(tz=UTC)
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def build_report(
    args: argparse.Namespace,
    *,
    now: datetime,
    quote_fetcher: Callable[[str, str], QuoteSnapshot],
) -> dict[str, Any]:
    symbols = resolve_symbols(
        args.symbols, Path(args.symbols_file), max_symbols=int(args.max_symbols)
    )
    market_open = bool(args.force_market_open) or is_us_market_open(now)
    previous = latest_jsonl(Path(args.log))
    if not market_open:
        return base_report(
            now=now,
            symbols=symbols,
            status="skipped_market_closed",
            market_open=False,
            previous=previous,
            quotes=[],
        )
    if not args.finnhub_api_key:
        return base_report(
            now=now,
            symbols=symbols,
            status="blocked_missing_finnhub_api_key",
            market_open=True,
            previous=previous,
            quotes=[],
            blockers=["missing_finnhub_api_key"],
        )
    quotes = [quote_fetcher(symbol, args.finnhub_api_key) for symbol in symbols]
    return base_report(
        now=now,
        symbols=symbols,
        status="ok",
        market_open=True,
        previous=previous,
        quotes=quotes,
    )


def base_report(
    *,
    now: datetime,
    symbols: Sequence[str],
    status: str,
    market_open: bool,
    previous: Mapping[str, Any] | None,
    quotes: Sequence[QuoteSnapshot],
    blockers: Sequence[str] = (),
) -> dict[str, Any]:
    rows = [quote_row(quote) for quote in quotes]
    previous_judgements = previous_symbol_judgements(previous)
    changes = [row for row in rows if previous_judgements.get(row["symbol"]) != row["judgement"]]
    notable = [row for row in rows if row["notable"]]
    ok_quotes = [row for row in rows if row["status"] == "ok"]
    return {
        "status": status,
        "generated_at": now.astimezone(UTC).isoformat(),
        "market_time": now.astimezone(ZoneInfo("America/New_York")).isoformat(),
        "safety": "intraday paper monitor only; no orders; no trading venue; no advice",
        "live_trading_authorized": False,
        "order_created": False,
        "summary": {
            "status": status,
            "market_open": market_open,
            "symbols": len(symbols),
            "ok_quotes": len(ok_quotes),
            "changes": len(changes),
            "notable": len(notable),
            "max_symbols": len(symbols),
            "order_created": False,
        },
        "symbols": list(symbols),
        "quotes": rows,
        "judgement_changes": changes,
        "notable_quotes": notable,
        "blockers": list(blockers),
    }


def resolve_symbols(
    cli_symbols: Sequence[str] | None, symbols_file: Path, *, max_symbols: int
) -> tuple[str, ...]:
    raw = list(cli_symbols or []) or read_symbols_file(symbols_file) or list(DEFAULT_SYMBOLS)
    symbols: list[str] = []
    for item in raw:
        symbol = item.strip().upper()
        if symbol and symbol not in symbols:
            symbols.append(symbol)
        if len(symbols) >= max_symbols:
            break
    return tuple(symbols)


def read_symbols_file(path: Path) -> list[str]:
    if not path.exists():
        return []
    rows: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        clean = line.split("#", 1)[0].strip()
        if clean:
            rows.append(clean)
    return rows


def is_us_market_open(now: datetime) -> bool:
    local = now.astimezone(ZoneInfo("America/New_York"))
    if local.weekday() >= 5:
        return False
    current = local.time()
    return time(9, 30) <= current < time(16, 0)


def fetch_finnhub_quote(symbol: str, token: str) -> QuoteSnapshot:
    query = urllib.parse.urlencode({"symbol": symbol, "token": token})
    request = urllib.request.Request(
        f"{FINNHUB_QUOTE_URL}?{query}",
        headers={"User-Agent": "intraday-paper-observer/0.1"},
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:  # noqa: S310 - public API
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, ValueError, KeyError) as exc:
        return QuoteSnapshot(symbol, "fetch_failed", None, None, None, None, str(exc))
    current = numeric_or_none(payload.get("c"))
    previous_close = numeric_or_none(payload.get("pc"))
    source_ts = payload.get("t")
    source_timestamp = (
        int(source_ts) if isinstance(source_ts, int | float) and source_ts > 0 else None
    )
    if current is None or previous_close is None or current <= 0 or previous_close <= 0:
        return QuoteSnapshot(
            symbol, "missing_quote", current, previous_close, None, source_timestamp
        )
    return QuoteSnapshot(
        symbol=symbol,
        status="ok",
        current=current,
        previous_close=previous_close,
        change_pct=(current / previous_close) - 1.0,
        source_timestamp=source_timestamp,
    )


def numeric_or_none(value: Any) -> float | None:
    return float(value) if isinstance(value, int | float) else None


def quote_row(quote: QuoteSnapshot) -> dict[str, Any]:
    judgement = classify_judgement(quote)
    return {
        "symbol": quote.symbol,
        "status": quote.status,
        "current": quote.current,
        "previous_close": quote.previous_close,
        "change_pct": quote.change_pct,
        "source_timestamp": quote.source_timestamp,
        "judgement": judgement,
        "notable": judgement in {"would_review_buy_strength", "would_review_sell_risk"},
        "error": quote.error,
    }


def classify_judgement(quote: QuoteSnapshot) -> str:
    if quote.status != "ok" or quote.change_pct is None:
        return "unavailable"
    if quote.change_pct >= 0.02:
        return "would_review_buy_strength"
    if quote.change_pct <= -0.02:
        return "would_review_sell_risk"
    return "would_hold"


def latest_jsonl(path: Path) -> Mapping[str, Any] | None:
    rows = read_jsonl(path)
    return rows[-1] if rows else None


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            payload = json.loads(line)
            if isinstance(payload, dict):
                rows.append(payload)
    return rows


def previous_symbol_judgements(previous: Mapping[str, Any] | None) -> dict[str, str]:
    if not previous:
        return {}
    quotes = previous.get("quotes", [])
    if not isinstance(quotes, list):
        return {}
    return {
        str(row.get("symbol")): str(row.get("judgement"))
        for row in quotes
        if isinstance(row, Mapping) and row.get("symbol")
    }


def append_log(path: Path, report: Mapping[str, Any], *, max_entries: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = [*read_jsonl(path), dict(report)][-max_entries:]
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )


def write_outputs(report: Mapping[str, Any], output: Path, markdown: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    markdown.parent.mkdir(parents=True, exist_ok=True)
    markdown.write_text(render_markdown(report), encoding="utf-8")


def render_markdown(report: Mapping[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# Intraday no-order monitor",
        "",
        "Safety: intraday paper monitor only; no orders, no trading venue, no advice.",
        "",
        "## Summary",
        "",
        f"- Status: `{summary['status']}`",
        f"- Market open: `{summary['market_open']}`",
        f"- Symbols: `{summary['symbols']}`",
        f"- OK quotes: `{summary['ok_quotes']}`",
        f"- Judgement changes: `{summary['changes']}`",
        f"- Notable quotes: `{summary['notable']}`",
        f"- Order created: `{summary['order_created']}`",
        "",
        "## Quotes",
        "",
        "| Symbol | Change | Judgement |",
        "| --- | ---: | --- |",
    ]
    for row in report.get("quotes", []):
        if isinstance(row, Mapping):
            lines.append(
                f"| {row.get('symbol')} | {format_pct(row.get('change_pct'))} | "
                f"{row.get('judgement')} |"
            )
    return "\n".join(lines) + "\n"


def format_pct(value: Any) -> str:
    return f"{value * 100:.2f}%" if isinstance(value, int | float) else "unknown"


def should_send_discord(report: Mapping[str, Any]) -> bool:
    summary = report.get("summary", {})
    if not isinstance(summary, Mapping):
        return False
    return bool(summary.get("market_open")) and (
        int(summary.get("changes", 0) or 0) > 0 or int(summary.get("notable", 0) or 0) > 0
    )


def render_discord_message(report: Mapping[str, Any]) -> str:
    summary = report["summary"]
    notable = report.get("notable_quotes", [])
    lines = [
        "⏱️ 장중 NO-ORDER 모니터",
        "실주문 없음. 5분 단위 quote 기반 판단 변화만 기록합니다.",
        (
            f"- 상태: `{summary['status']}` / symbols `{summary['symbols']}` / "
            f"changes `{summary['changes']}`"
        ),
    ]
    if notable:
        lines.append(
            "- notable: "
            + ", ".join(
                str(row.get("symbol")) for row in notable[:5] if isinstance(row, Mapping)
            )
        )
    return "\n".join(lines)[:1900]


def post_discord(webhook_url: str, message: str) -> None:
    payload = json.dumps(
        {
            "username": "Auto Trading Bot Intraday Observer",
            "content": message,
            "allowed_mentions": {"parse": []},
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        webhook_url,
        data=payload,
        headers={"Content-Type": "application/json", "User-Agent": "intraday-paper-observer/0.1"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=10) as response:  # noqa: S310 - webhook URL secret
        if response.status >= 300:
            raise RuntimeError(f"Discord webhook failed with HTTP {response.status}")


if __name__ == "__main__":
    raise SystemExit(main())
