"""Collect free BLS macro snapshots for no-order research.

This collector uses the BLS Public Data API without a registration key by
default. It records inflation/labor macro context only; it never creates orders,
connects to a broker, or reads credentials.
"""

from __future__ import annotations

import argparse
import json
import urllib.error
import urllib.request
from collections.abc import Mapping, Sequence
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

BLS_API_URL = "https://api.bls.gov/publicAPI/v2/timeseries/data/"
BLS_API_DOC_URL = "https://www.bls.gov/developers/api_signature_v2.htm"
DEFAULT_OUTPUT = ".omx/reports/bls-macro-snapshot-latest.json"
DEFAULT_MARKDOWN = ".omx/reports/bls-macro-snapshot-latest.md"
DEFAULT_SERIES = {
    "CUUR0000SA0": "cpi_all_urban_consumers",
    "LNS14000000": "unemployment_rate",
    "CES0000000001": "nonfarm_payrolls_all_employees",
}


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Collect BLS macro snapshot.")
    parser.add_argument("--series", nargs="+", default=list(DEFAULT_SERIES))
    parser.add_argument("--start-year", default=str(date.today().year - 1))
    parser.add_argument("--end-year", default=str(date.today().year))
    parser.add_argument("--output", default=DEFAULT_OUTPUT)
    parser.add_argument("--markdown", default=DEFAULT_MARKDOWN)
    parser.add_argument("--timeout", type=float, default=20.0)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    report = build_report(args)
    write_json(Path(args.output), report)
    write_markdown(Path(args.markdown), report)
    print(
        "bls macro status={status} series={series} latest_points={latest_points}".format(
            **report["summary"]
        )
    )
    print(f"json={args.output}")
    print(f"markdown={args.markdown}")
    return 0


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    series_ids = tuple(dict.fromkeys(str(series).upper() for series in args.series))
    try:
        payload = fetch_bls(
            series_ids=series_ids,
            start_year=str(args.start_year),
            end_year=str(args.end_year),
            timeout=float(args.timeout),
        )
        rows = parse_series_payload(payload)
        status = "ok" if rows else "empty"
        errors: list[str] = []
    except (OSError, urllib.error.URLError, ValueError, json.JSONDecodeError) as exc:
        rows = []
        status = "error"
        errors = [f"{type(exc).__name__}:{exc}"]
    latest_points = [latest_point(row) for row in rows]
    latest_points = [point for point in latest_points if point is not None]
    return {
        "status": status,
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "safety": "BLS macro snapshot only; no broker; no credentials; no orders; no advice",
        "summary": {
            "status": status,
            "series": len(series_ids),
            "returned_series": len(rows),
            "latest_points": len(latest_points),
            "order_created": False,
            "live_trading_authorized": False,
        },
        "source": {"endpoint": BLS_API_URL, "docs": BLS_API_DOC_URL},
        "series": rows,
        "latest_points": latest_points,
        "errors": errors,
        "point_in_time_rule": (
            "Use BLS period/year and release availability before joining features."
        ),
        "live_trading_authorized": False,
        "paper_api_authorized": False,
    }


def fetch_bls(
    *, series_ids: Sequence[str], start_year: str, end_year: str, timeout: float
) -> Mapping[str, Any]:
    payload = json.dumps(
        {"seriesid": list(series_ids), "startyear": start_year, "endyear": end_year}
    ).encode("utf-8")
    request = urllib.request.Request(
        BLS_API_URL,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "User-Agent": "auto-trading-bot-research/0.1",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 public API
        parsed = json.loads(response.read().decode("utf-8"))
    if not isinstance(parsed, Mapping):
        raise ValueError("BLS response was not a JSON object")
    if parsed.get("status") != "REQUEST_SUCCEEDED":
        raise ValueError(f"BLS request failed: {parsed.get('message')}")
    return parsed


def parse_series_payload(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    results = payload.get("Results", {})
    series = results.get("series", []) if isinstance(results, Mapping) else []
    if not isinstance(series, list):
        return []
    rows: list[dict[str, Any]] = []
    for item in series:
        if not isinstance(item, Mapping):
            continue
        series_id = str(item.get("seriesID") or "")
        data = item.get("data", [])
        if not isinstance(data, list):
            data = []
        points = [compact_point(point) for point in data if isinstance(point, Mapping)]
        rows.append(
            {
                "series_id": series_id,
                "name": DEFAULT_SERIES.get(series_id, series_id),
                "points": points,
                "latest": latest_point({"points": points}),
            }
        )
    return rows


def compact_point(point: Mapping[str, Any]) -> dict[str, Any]:
    value = point.get("value")
    numeric = None
    try:
        numeric = float(value) if value not in (None, "", "-") else None
    except ValueError:
        numeric = None
    return {
        "year": str(point.get("year") or ""),
        "period": str(point.get("period") or ""),
        "period_name": point.get("periodName"),
        "value": numeric,
        "latest": str(point.get("latest", "")).lower() == "true",
        "footnotes": point.get("footnotes", []),
    }


def latest_point(series_row: Mapping[str, Any]) -> dict[str, Any] | None:
    points = series_row.get("points", [])
    if not isinstance(points, list) or not points:
        return None
    return next(
        (point for point in points if isinstance(point, Mapping) and point.get("latest")),
        points[0],
    )


def write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def write_markdown(path: Path, report: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    summary = report["summary"]
    lines = [
        "# BLS macro snapshot",
        "",
        "Safety: macro context only; no broker, no credentials, no orders, no advice.",
        "",
        "## Summary",
        "",
        f"- Status: `{summary['status']}`",
        f"- Series requested: `{summary['series']}`",
        f"- Returned series: `{summary['returned_series']}`",
        f"- Latest points: `{summary['latest_points']}`",
        f"- Order created: `{summary['order_created']}`",
        f"- Live trading authorized: `{summary['live_trading_authorized']}`",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
