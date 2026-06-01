"""Replicate latest paper-signal prices against an independent source.

The current independent free candidate is Stooq CSV downloads. Stooq requires a
captcha-issued free API key for CSV access, so this gate is fail-closed when the
key is absent and records the exact blocker. It never creates orders, connects to
a broker, reads trading credentials, or authorizes live trading.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import time
import urllib.parse
import urllib.request
from collections.abc import Mapping, Sequence
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

DEFAULT_PAPER_SIGNAL = "reports/paper-dry-run-signal-latest.json"
DEFAULT_OUTPUT = ".omx/reports/independent-price-replication-latest.json"
DEFAULT_MARKDOWN = ".omx/reports/independent-price-replication-latest.md"
STOOQ_CSV_URL = "https://stooq.com/q/d/l/"
STOOQ_API_KEY_HELP_URL = "https://stooq.com/q/d/?s=aapl.us&get_apikey"
ALPHA_VANTAGE_URL = "https://www.alphavantage.co/query"
ALPHA_VANTAGE_DOC_URL = "https://www.alphavantage.co/documentation/"


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Replicate latest prices with Stooq CSV data.")
    parser.add_argument("--paper-signal", default=DEFAULT_PAPER_SIGNAL)
    parser.add_argument("--output", default=DEFAULT_OUTPUT)
    parser.add_argument("--markdown", default=DEFAULT_MARKDOWN)
    parser.add_argument("--provider", choices=("auto", "stooq", "alpha_vantage"), default="auto")
    parser.add_argument("--stooq-api-key", default=os.environ.get("STOOQ_API_KEY", ""))
    parser.add_argument(
        "--alpha-vantage-api-key", default=os.environ.get("ALPHA_VANTAGE_API_KEY", "")
    )
    parser.add_argument("--max-close-diff-bps", type=float, default=100.0)
    parser.add_argument("--timeout-seconds", type=float, default=20.0)
    parser.add_argument("--request-delay-seconds", type=float, default=1.5)
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
            "independent price replication "
            "status={status} symbols={symbols} blockers={blockers}"
        ).format(
            status=report["summary"]["status"],
            symbols=report["summary"]["symbols_checked"],
            blockers=len(report["blockers"]),
        )
    )
    print(f"json={output}")
    print(f"markdown={markdown}")
    return 0


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    paper_signal = read_json_if_exists(Path(args.paper_signal))
    generated_at = datetime.now(tz=UTC)
    provider, provider_key, provider_blockers = resolve_provider(args)
    blockers: list[str] = []
    comparisons: list[dict[str, Any]] = []
    if paper_signal is None:
        blockers.append("paper_signal_missing_for_independent_price_replication")
    elif provider_blockers:
        blockers.extend(provider_blockers)
    else:
        comparisons, blockers = compare_provider_to_signal(
            paper_signal,
            provider=provider,
            api_key=provider_key,
            max_close_diff_bps=float(args.max_close_diff_bps),
            timeout_seconds=float(args.timeout_seconds),
            request_delay_seconds=float(args.request_delay_seconds),
        )
    status = "pass" if not blockers else "blocked"
    return {
        "status": "ok",
        "generated_at": generated_at.isoformat(),
        "safety": (
            "independent price replication only; no orders; no broker; "
            "no credentials; no advice"
        ),
        "live_trading_authorized": False,
        "summary": {
            "status": status,
            "provider": provider,
            "symbols_checked": len(comparisons),
            "max_close_diff_bps": float(args.max_close_diff_bps),
            "blockers": len(blockers),
            "order_created": False,
            "live_trading_authorized": False,
        },
        "sources": {
            "stooq_csv_url": STOOQ_CSV_URL,
            "stooq_api_key_help": STOOQ_API_KEY_HELP_URL,
            "alpha_vantage_docs": ALPHA_VANTAGE_DOC_URL,
            "source_report": str(args.paper_signal),
        },
        "comparisons": comparisons,
        "blockers": blockers,
        "required_next_evidence": [
            "Provide STOOQ_API_KEY or ALPHA_VANTAGE_API_KEY to run independent replication.",
            "Keep independent close differences within the configured basis-point tolerance.",
            "Do not treat independent replication as live-trading approval.",
        ],
    }


def read_json_if_exists(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else None


def resolve_provider(args: argparse.Namespace) -> tuple[str, str, list[str]]:
    requested = str(args.provider)
    stooq_key = str(args.stooq_api_key).strip()
    alpha_key = str(args.alpha_vantage_api_key).strip()
    if requested == "stooq":
        if not stooq_key:
            return "stooq_csv", "", ["stooq_api_key_missing_for_independent_price_replication"]
        return "stooq_csv", stooq_key, []
    if requested == "alpha_vantage":
        if not alpha_key:
            return "alpha_vantage", "", [
                "alpha_vantage_api_key_missing_for_independent_price_replication"
            ]
        return "alpha_vantage", alpha_key, []
    if alpha_key:
        return "alpha_vantage", alpha_key, []
    if stooq_key:
        return "stooq_csv", stooq_key, []
    return "missing", "", ["independent_price_api_key_missing"]


def compare_provider_to_signal(
    paper_signal: Mapping[str, Any],
    *,
    provider: str,
    api_key: str,
    max_close_diff_bps: float,
    timeout_seconds: float,
    request_delay_seconds: float = 0.0,
) -> tuple[list[dict[str, Any]], list[str]]:
    blockers: list[str] = []
    comparisons: list[dict[str, Any]] = []
    as_of = date.fromisoformat(str(paper_signal.get("as_of_date")))
    source_bars = paper_signal.get("source_bars", {})
    if not isinstance(source_bars, Mapping) or not source_bars:
        return [], ["paper_signal_source_bars_missing"]
    for index, (symbol, raw_bar) in enumerate(source_bars.items()):
        if index > 0 and request_delay_seconds > 0:
            time.sleep(request_delay_seconds)
        if not isinstance(raw_bar, Mapping):
            blockers.append(f"source_bar_invalid:{symbol}")
            continue
        yahoo_close = float(raw_bar.get("close", 0.0) or 0.0)
        try:
            provider_row = fetch_provider_daily_row(
                provider, str(symbol), as_of=as_of, api_key=api_key, timeout_seconds=timeout_seconds
            )
        except (OSError, ValueError) as exc:
            blockers.append(f"{provider}_fetch_failed:{symbol}:{exc}")
            continue
        provider_close = float(provider_row["close"])
        diff_bps = abs(provider_close / yahoo_close - 1.0) * 10_000 if yahoo_close > 0 else 0.0
        if diff_bps > max_close_diff_bps:
            blockers.append(f"independent_close_diff_above_limit:{symbol}")
        comparisons.append(
            {
                "symbol": str(symbol),
                "as_of_date": as_of.isoformat(),
                "yahoo_close": yahoo_close,
                "provider": provider,
                "provider_close": provider_close,
                "close_diff_bps": diff_bps,
                "status": "pass" if diff_bps <= max_close_diff_bps else "blocked",
            }
        )
    return comparisons, blockers


def fetch_provider_daily_row(
    provider: str,
    symbol: str,
    *,
    as_of: date,
    api_key: str,
    timeout_seconds: float,
) -> dict[str, float]:
    if provider == "stooq_csv":
        return fetch_stooq_daily_row(
            symbol, as_of=as_of, api_key=api_key, timeout_seconds=timeout_seconds
        )
    if provider == "alpha_vantage":
        return fetch_alpha_vantage_daily_row(
            symbol, as_of=as_of, api_key=api_key, timeout_seconds=timeout_seconds
        )
    raise ValueError(f"unsupported_provider:{provider}")


def fetch_stooq_daily_row(
    symbol: str,
    *,
    as_of: date,
    api_key: str,
    timeout_seconds: float,
) -> dict[str, float]:
    query = urllib.parse.urlencode(
        {
            "s": stooq_symbol(symbol),
            "i": "d",
            "d1": as_of.strftime("%Y%m%d"),
            "d2": as_of.strftime("%Y%m%d"),
            "apikey": api_key,
        }
    )
    url = f"{STOOQ_CSV_URL}?{query}"
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "auto-trading-bot-offline-research/0.1"},
    )
    with urllib.request.urlopen(  # noqa: S310 - public research CSV, no credentials
        request, timeout=timeout_seconds
    ) as response:
        text = response.read().decode("utf-8")
    if "Get your apikey" in text:
        raise ValueError("stooq_api_key_invalid_or_missing")
    rows = list(csv.DictReader(text.splitlines()))
    if not rows:
        raise ValueError("stooq_no_rows_returned")
    raw = rows[-1]
    return {
        "open": float(raw["Open"]),
        "high": float(raw["High"]),
        "low": float(raw["Low"]),
        "close": float(raw["Close"]),
        "volume": float(raw.get("Volume", 0) or 0),
    }


def fetch_alpha_vantage_daily_row(
    symbol: str,
    *,
    as_of: date,
    api_key: str,
    timeout_seconds: float,
) -> dict[str, float]:
    query = urllib.parse.urlencode(
        {
            "function": "TIME_SERIES_DAILY",
            "symbol": alpha_vantage_symbol(symbol),
            "outputsize": "compact",
            "apikey": api_key,
        }
    )
    request = urllib.request.Request(
        f"{ALPHA_VANTAGE_URL}?{query}",
        headers={"User-Agent": "auto-trading-bot-offline-research/0.1"},
    )
    with urllib.request.urlopen(  # noqa: S310 - public research API, no broker access
        request, timeout=timeout_seconds
    ) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if "Error Message" in payload:
        raise ValueError(str(payload["Error Message"]))
    if "Note" in payload or "Information" in payload:
        raise ValueError(str(payload.get("Note") or payload.get("Information")))
    series = payload.get("Time Series (Daily)")
    if not isinstance(series, Mapping):
        raise ValueError("alpha_vantage_daily_series_missing")
    key = as_of.isoformat()
    if key not in series:
        available = sorted(day for day in series if day <= key)
        if not available:
            raise ValueError("alpha_vantage_no_row_on_or_before_as_of")
        key = available[-1]
    raw = series[key]
    if not isinstance(raw, Mapping):
        raise ValueError("alpha_vantage_row_invalid")
    return {
        "open": float(raw["1. open"]),
        "high": float(raw["2. high"]),
        "low": float(raw["3. low"]),
        "close": float(raw["4. close"]),
        "volume": float(raw.get("5. volume", 0) or 0),
    }


def alpha_vantage_symbol(symbol: str) -> str:
    return symbol.strip().upper()


def stooq_symbol(symbol: str) -> str:
    normalized = symbol.strip().lower().replace("-", ".")
    if "." not in normalized:
        normalized = f"{normalized}.us"
    return normalized


def write_markdown(path: Path, report: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    summary = report["summary"]
    lines = [
        "# Independent price replication gate",
        "",
        (
            "Safety: independent price replication only; no orders, no broker, "
            "no credentials, no advice."
        ),
        "",
        "## Summary",
        "",
        f"- Status: `{summary['status']}`",
        f"- Provider: `{summary['provider']}`",
        f"- Symbols checked: `{summary['symbols_checked']}`",
        f"- Max close diff bps: `{summary['max_close_diff_bps']}`",
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
