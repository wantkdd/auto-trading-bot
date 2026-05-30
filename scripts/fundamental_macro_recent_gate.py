"""Fundamental, macro-proxy, and recent-regime gates for research candidates.

This is an offline research script. It may fetch public SEC EDGAR data for local
analysis, but it never connects to brokers, reads credentials, or places orders.
"""

from __future__ import annotations

import argparse
import json
import urllib.error
import urllib.request
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from auto_trading_bot.domain import Bar

try:
    from scripts.non_leveraged_universe_analysis import (
        DEFAULT_SYMBOLS,
        align_by_date,
        evaluate_weights,
        load_symbols,
        looks_leveraged,
        percent,
    )
    from scripts.non_leveraged_universe_analysis import (
        build_report as build_universe_report,
    )
except ModuleNotFoundError:  # pragma: no cover - direct script execution path
    from non_leveraged_universe_analysis import (  # type: ignore[no-redef]
        DEFAULT_SYMBOLS,
        align_by_date,
        evaluate_weights,
        load_symbols,
        looks_leveraged,
        percent,
    )
    from non_leveraged_universe_analysis import (
        build_report as build_universe_report,
    )

SEC_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SEC_COMPANY_FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
SEC_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
SEC_API_DOC_URL = "https://www.sec.gov/edgar/sec-api-documentation"
SEC_FAIR_ACCESS_URL = "https://www.sec.gov/edgar/searchedgar/accessing-edgar-data.htm"
FRED_API_KEY_DOC_URL = "https://fred.stlouisfed.org/docs/api/fred/v2/api_key.html"
USER_AGENT = "auto-trading-bot-offline-research/0.1 contact: local-research@example.invalid"
STOCK_SYMBOLS = {"AAPL", "MSFT", "AMZN", "GOOGL", "META", "JPM", "JNJ", "PG", "XOM", "KO"}
BENCHMARK_SYMBOLS = ("SPY", "QQQ", "DIA")


@dataclass(frozen=True)
class FundamentalSnapshot:
    symbol: str
    cik: str | None
    company_name: str | None
    status: str
    revenue_growth_yoy: float | None
    net_income_positive: bool | None
    operating_cash_flow_positive: bool | None
    debt_to_equity: float | None
    current_ratio: float | None
    latest_filing_date: str | None
    recent_8k_count_90d: int | None
    failure_reasons: tuple[str, ...]
    data_warnings: tuple[str, ...]


@dataclass(frozen=True)
class RecentRegimeSummary:
    window: str
    start: str
    end: str
    candidate_return: float
    benchmark_return: float
    excess_return: float
    max_drawdown: float
    status: str
    failure_reasons: tuple[str, ...]


@dataclass(frozen=True)
class CandidateGate:
    name: str
    symbols: tuple[str, str]
    weights: tuple[float, float]
    base_median_excess: float
    base_holdout_excess: float
    base_worst_mdd: float
    fundamental_status: str
    recent_regime_status: str
    status: str
    failure_reasons: tuple[str, ...]
    recent_regimes: tuple[RecentRegimeSummary, ...]
    fundamentals: tuple[FundamentalSnapshot, ...]


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Gate non-leveraged candidates with SEC fundamentals and recent regimes."
    )
    parser.add_argument("--symbols", nargs="+", default=list(DEFAULT_SYMBOLS))
    parser.add_argument("--start", default="2015-01-01")
    parser.add_argument("--end", default=date.today().isoformat())
    parser.add_argument("--data-dir", default="data/external")
    parser.add_argument("--sec-cache-dir", default="data/external/sec")
    parser.add_argument(
        "--output", default=".omx/reports/fundamental-macro-recent-gate-latest.json"
    )
    parser.add_argument(
        "--markdown", default=".omx/reports/fundamental-macro-recent-gate-latest.md"
    )
    parser.add_argument("--top-candidates", type=int, default=12)
    parser.add_argument("--force-refresh", action="store_true")
    parser.add_argument("--skip-sec-refresh", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    report = build_report(args)
    output = Path(args.output)
    markdown = Path(args.markdown)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    write_markdown(markdown, report)
    status_line = (
        "fundamental gate status={status} candidates={candidates} pass={passed} review={review}"
    )
    print(status_line.format(**report["summary"]))
    print(f"json={output}")
    print(f"markdown={markdown}")
    return 0


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    symbols = tuple(dict.fromkeys(symbol.upper() for symbol in args.symbols))
    blocked = [symbol for symbol in symbols if looks_leveraged(symbol)]
    allowed = [symbol for symbol in symbols if symbol not in blocked]
    universe_args = argparse.Namespace(
        symbols=list(allowed),
        start=args.start,
        end=args.end,
        data_dir=args.data_dir,
        output=".omx/reports/non-leveraged-universe-latest.json",
        markdown=".omx/reports/non-leveraged-universe-latest.md",
        force_refresh=args.force_refresh,
    )
    universe = build_universe_report(universe_args)
    pass_pairs = [row for row in universe["pair_summaries"] if row["status"] == "pass"]
    selected_pairs = pass_pairs[: args.top_candidates]

    data_args = argparse.Namespace(
        start=args.start,
        end=args.end,
        data_dir=args.data_dir,
        force_refresh=args.force_refresh,
    )
    needed_symbols = sorted(
        set(BENCHMARK_SYMBOLS)
        | {symbol for row in selected_pairs for symbol in row["symbols"]}
        | {"TLT", "IEF", "SHY", "GLD"}
    )
    bars, price_metadata = load_symbols(data_args, needed_symbols)
    dates, aligned = align_by_date(bars)
    as_of = dates[-1]

    ticker_map = load_sec_ticker_map(Path(args.sec_cache_dir), force_refresh=args.force_refresh)
    fundamentals = {
        symbol: build_fundamental_snapshot(
            symbol=symbol,
            ticker_map=ticker_map,
            cache_dir=Path(args.sec_cache_dir),
            force_refresh=args.force_refresh and not args.skip_sec_refresh,
            skip_refresh=args.skip_sec_refresh,
            as_of=as_of,
        )
        for symbol in sorted({symbol for row in selected_pairs for symbol in row["symbols"]})
        if symbol in STOCK_SYMBOLS
    }
    candidate_gates = [
        gate_candidate(row, dates, aligned, fundamentals)
        for row in selected_pairs
        if row["status"] == "pass"
    ]
    passed = [row for row in candidate_gates if row.status == "pass"]
    review = [row for row in candidate_gates if row.status != "pass"]
    macro_proxy = build_macro_proxy_summary(dates, aligned)
    report = {
        "status": "ok",
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "as_of_date": as_of.isoformat(),
        "safety": "offline research only; non-leveraged; no orders, no broker, no advice",
        "sources": {
            "sec_api_documentation": SEC_API_DOC_URL,
            "sec_fair_access": SEC_FAIR_ACCESS_URL,
            "fred_api_key_documentation": FRED_API_KEY_DOC_URL,
            "price_data": "Yahoo Finance chart endpoint via existing local research cache",
        },
        "limitations": [
            "SEC fundamentals cover companies, not ETFs such as QQQ or GLD.",
            (
                "FRED macro series are documented but require an API key, so this run uses "
                "price-based macro proxies only."
            ),
            (
                "Public news sentiment is not treated as a reliable free data source; "
                "SEC 8-K counts are used only as event-risk flags, not sentiment or "
                "prediction."
            ),
            "Passing this research gate is still not approval for real-money trading.",
        ],
        "blocked_symbols": blocked,
        "price_data": price_metadata,
        "macro_proxy": macro_proxy,
        "live_trading_authorized": False,
        "promotion_level": "research_only",
        "summary": {
            "status": "ok",
            "candidates": len(candidate_gates),
            "passed": len(passed),
            "review": len(review),
            "top_status": candidate_gates[0].status if candidate_gates else "none",
            "top_candidate": candidate_gates[0].name if candidate_gates else None,
            "leverage_policy": "leveraged_and_inverse_products_blocked",
            "max_leverage_allowed": 1.0,
        },
        "candidate_gates": [asdict(row) for row in candidate_gates],
        "universe_summary": universe["summary"],
    }
    return report


def load_sec_ticker_map(cache_dir: Path, *, force_refresh: bool) -> dict[str, dict[str, Any]]:
    cache_path = cache_dir / "company_tickers.json"
    payload = fetch_json_cached(SEC_TICKERS_URL, cache_path, force_refresh=force_refresh)
    mapping: dict[str, dict[str, Any]] = {}
    if not isinstance(payload, Mapping):
        return mapping
    for value in payload.values():
        if not isinstance(value, Mapping):
            continue
        ticker = str(value.get("ticker", "")).upper()
        cik = value.get("cik_str")
        if ticker and cik is not None:
            mapping[ticker] = {
                "cik": f"{int(cik):010d}",
                "title": str(value.get("title", "")) or None,
            }
    return mapping


def build_fundamental_snapshot(
    *,
    symbol: str,
    ticker_map: Mapping[str, Mapping[str, Any]],
    cache_dir: Path,
    force_refresh: bool,
    skip_refresh: bool,
    as_of: date,
) -> FundamentalSnapshot:
    ticker = ticker_map.get(symbol)
    if ticker is None:
        return FundamentalSnapshot(
            symbol=symbol,
            cik=None,
            company_name=None,
            status="review",
            revenue_growth_yoy=None,
            net_income_positive=None,
            operating_cash_flow_positive=None,
            debt_to_equity=None,
            current_ratio=None,
            latest_filing_date=None,
            recent_8k_count_90d=None,
            failure_reasons=("sec_cik_not_found",),
            data_warnings=(),
        )
    cik = str(ticker["cik"])
    warnings: list[str] = []
    facts_payload: Mapping[str, Any] = {}
    submissions_payload: Mapping[str, Any] = {}
    if not skip_refresh:
        try:
            facts_payload = fetch_json_cached(
                SEC_COMPANY_FACTS_URL.format(cik=cik),
                cache_dir / f"CIK{cik}_companyfacts.json",
                force_refresh=force_refresh,
            )
            submissions_payload = fetch_json_cached(
                SEC_SUBMISSIONS_URL.format(cik=cik),
                cache_dir / f"CIK{cik}_submissions.json",
                force_refresh=force_refresh,
            )
        except (OSError, urllib.error.URLError, ValueError, json.JSONDecodeError) as exc:
            warnings.append(f"sec_fetch_failed:{type(exc).__name__}")
    else:
        facts_path = cache_dir / f"CIK{cik}_companyfacts.json"
        submissions_path = cache_dir / f"CIK{cik}_submissions.json"
        if facts_path.exists():
            facts_payload = json.loads(facts_path.read_text(encoding="utf-8"))
        else:
            warnings.append("companyfacts_cache_missing")
        if submissions_path.exists():
            submissions_payload = json.loads(submissions_path.read_text(encoding="utf-8"))
        else:
            warnings.append("submissions_cache_missing")

    metrics = extract_fundamental_metrics(facts_payload, as_of=as_of)
    recent_8k_count, latest_filing_date = extract_filing_risk(submissions_payload, as_of=as_of)
    reasons = fundamental_failure_reasons(metrics, warnings)
    return FundamentalSnapshot(
        symbol=symbol,
        cik=cik,
        company_name=str(ticker.get("title") or "") or None,
        status="pass" if not reasons else "review",
        revenue_growth_yoy=metrics.get("revenue_growth_yoy"),
        net_income_positive=positive_flag(metrics.get("net_income")),
        operating_cash_flow_positive=positive_flag(metrics.get("operating_cash_flow")),
        debt_to_equity=metrics.get("debt_to_equity"),
        current_ratio=metrics.get("current_ratio"),
        latest_filing_date=latest_filing_date,
        recent_8k_count_90d=recent_8k_count,
        failure_reasons=tuple(reasons),
        data_warnings=tuple(warnings),
    )


def fetch_json_cached(url: str, cache_path: Path, *, force_refresh: bool) -> Mapping[str, Any]:
    if cache_path.exists() and not force_refresh:
        return json.loads(cache_path.read_text(encoding="utf-8"))
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310 - research script only
        payload = json.loads(response.read().decode("utf-8"))
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    if not isinstance(payload, Mapping):
        raise ValueError(f"expected JSON object from {url}")
    return payload


def extract_fundamental_metrics(
    payload: Mapping[str, Any], *, as_of: date | None = None
) -> dict[str, float | None]:
    as_of = as_of or date.max
    us_gaap = payload.get("facts", {})
    if isinstance(us_gaap, Mapping):
        us_gaap = us_gaap.get("us-gaap", {})
    if not isinstance(us_gaap, Mapping):
        us_gaap = {}

    revenue_annual = annual_values(us_gaap, ("Revenues", "SalesRevenueNet"), as_of=as_of)
    revenue_growth = None
    if len(revenue_annual) >= 2 and revenue_annual[-2][1] not in (None, 0):
        revenue_growth = (revenue_annual[-1][1] / revenue_annual[-2][1]) - 1.0

    net_income = latest_value(us_gaap, ("NetIncomeLoss",), as_of=as_of)
    operating_cash_flow = latest_value(
        us_gaap,
        (
            "NetCashProvidedByUsedInOperatingActivities",
            "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations",
        ),
        as_of=as_of,
    )
    liabilities = latest_value(us_gaap, ("Liabilities", "LiabilitiesCurrent"), as_of=as_of)
    equity = latest_value(
        us_gaap,
        (
            "StockholdersEquity",
            "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
        ),
        as_of=as_of,
    )
    current_assets = latest_value(us_gaap, ("AssetsCurrent",), as_of=as_of)
    current_liabilities = latest_value(us_gaap, ("LiabilitiesCurrent",), as_of=as_of)
    debt_to_equity = None
    if liabilities is not None and equity is not None and equity > 0:
        debt_to_equity = liabilities / equity
    current_ratio = None
    if current_assets is not None and current_liabilities is not None and current_liabilities > 0:
        current_ratio = current_assets / current_liabilities
    return {
        "revenue_growth_yoy": revenue_growth,
        "net_income": net_income,
        "operating_cash_flow": operating_cash_flow,
        "debt_to_equity": debt_to_equity,
        "current_ratio": current_ratio,
    }


def annual_values(
    us_gaap: Mapping[str, Any], tags: Sequence[str], *, as_of: date
) -> list[tuple[int, float]]:
    by_year: dict[int, tuple[str, float]] = {}
    for fact in iter_facts(us_gaap, tags):
        if fact.get("form") != "10-K":
            continue
        fiscal_year = fact.get("fy")
        value = numeric_value(fact.get("val"))
        filed = str(fact.get("filed") or "")
        filed_on = parse_iso_date(filed)
        if not isinstance(fiscal_year, int) or value is None or filed_on is None:
            continue
        if filed_on > as_of:
            continue
        previous = by_year.get(fiscal_year)
        if previous is None or filed > previous[0]:
            by_year[fiscal_year] = (filed, value)
    return sorted((year, row[1]) for year, row in by_year.items())


def latest_value(us_gaap: Mapping[str, Any], tags: Sequence[str], *, as_of: date) -> float | None:
    for tag in tags:
        facts = sorted(
            (
                (str(fact.get("filed") or ""), numeric_value(fact.get("val")))
                for fact in iter_facts(us_gaap, (tag,))
                if fact.get("form") in {"10-K", "10-Q"} and filed_on_or_before(fact, as_of)
            ),
            key=lambda row: row[0],
        )
        for _filed, value in reversed(facts):
            if value is not None:
                return value
    return None


def iter_facts(us_gaap: Mapping[str, Any], tags: Sequence[str]) -> list[Mapping[str, Any]]:
    rows: list[Mapping[str, Any]] = []
    for tag in tags:
        container = us_gaap.get(tag)
        if not isinstance(container, Mapping):
            continue
        units = container.get("units")
        if not isinstance(units, Mapping):
            continue
        for unit_key in ("USD", "shares"):
            unit_rows = units.get(unit_key)
            if isinstance(unit_rows, list):
                rows.extend(row for row in unit_rows if isinstance(row, Mapping))
    return rows


def filed_on_or_before(fact: Mapping[str, Any], as_of: date) -> bool:
    filed_on = parse_iso_date(str(fact.get("filed") or ""))
    return filed_on is not None and filed_on <= as_of


def parse_iso_date(value: str) -> date | None:
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def numeric_value(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    return None


def extract_filing_risk(
    payload: Mapping[str, Any], *, as_of: date | None = None
) -> tuple[int | None, str | None]:
    as_of = as_of or date.today()
    recent = payload.get("filings", {})
    if isinstance(recent, Mapping):
        recent = recent.get("recent", {})
    if not isinstance(recent, Mapping):
        return None, None
    forms = recent.get("form")
    dates = recent.get("filingDate")
    if not isinstance(forms, list) or not isinstance(dates, list):
        return None, None
    cutoff = as_of - timedelta(days=90)
    count_8k = 0
    parsed_dates: list[str] = []
    for form, filing_date in zip(forms, dates, strict=False):
        if not isinstance(form, str) or not isinstance(filing_date, str):
            continue
        filed_on = parse_iso_date(filing_date)
        if filed_on is None or filed_on > as_of:
            continue
        parsed_dates.append(filing_date)
        if filed_on >= cutoff and form in {"8-K", "8-K/A"}:
            count_8k += 1
    return count_8k, max(parsed_dates) if parsed_dates else None


def fundamental_failure_reasons(
    metrics: Mapping[str, float | None], warnings: Sequence[str]
) -> list[str]:
    reasons: list[str] = []
    revenue_growth = metrics.get("revenue_growth_yoy")
    if revenue_growth is None:
        reasons.append("revenue_growth_missing")
    elif revenue_growth < -0.10:
        reasons.append("revenue_decline_worse_than_minus_10pct")
    net_income = metrics.get("net_income")
    if net_income is None:
        reasons.append("net_income_missing")
    elif net_income <= 0:
        reasons.append("net_income_not_positive")
    cash_flow = metrics.get("operating_cash_flow")
    if cash_flow is None:
        reasons.append("operating_cash_flow_missing")
    elif cash_flow <= 0:
        reasons.append("operating_cash_flow_not_positive")
    debt_to_equity = metrics.get("debt_to_equity")
    if debt_to_equity is not None and debt_to_equity > 5.0:
        reasons.append("debt_to_equity_above_5x")
    if any("failed" in warning or "missing" in warning for warning in warnings):
        reasons.append("sec_data_incomplete")
    return reasons


def positive_flag(value: float | None) -> bool | None:
    if value is None:
        return None
    return value > 0


def gate_candidate(
    row: Mapping[str, Any],
    dates: tuple[date, ...],
    data: Mapping[str, tuple[Bar, ...]],
    fundamentals: Mapping[str, FundamentalSnapshot],
) -> CandidateGate:
    symbols = tuple(str(symbol) for symbol in row["symbols"])
    weights_tuple = tuple(float(weight) for weight in row["weights"])
    weights = dict(zip(symbols, weights_tuple, strict=True))
    recent_regimes = tuple(evaluate_recent_regimes(dates, data, weights))
    relevant_fundamentals = tuple(
        fundamentals[symbol] for symbol in symbols if symbol in fundamentals
    )
    fundamental_reasons = [
        f"{snapshot.symbol}:{reason}"
        for snapshot in relevant_fundamentals
        if snapshot.status != "pass"
        for reason in snapshot.failure_reasons
    ]
    recent_reasons = [
        f"{regime.window}:{reason}"
        for regime in recent_regimes
        if regime.status != "pass"
        for reason in regime.failure_reasons
    ]
    reasons = [*fundamental_reasons, *recent_reasons]
    return CandidateGate(
        name=str(row["name"]),
        symbols=(symbols[0], symbols[1]),
        weights=(weights_tuple[0], weights_tuple[1]),
        base_median_excess=float(row["median_excess"]),
        base_holdout_excess=float(row["min_holdout_excess"]),
        base_worst_mdd=float(row["worst_max_drawdown"]),
        fundamental_status=(
            "not_applicable"
            if not relevant_fundamentals
            else "pass"
            if not fundamental_reasons
            else "review"
        ),
        recent_regime_status="pass" if not recent_reasons else "review",
        status="pass" if not reasons else "review",
        failure_reasons=tuple(reasons),
        recent_regimes=recent_regimes,
        fundamentals=relevant_fundamentals,
    )


def evaluate_recent_regimes(
    dates: tuple[date, ...], data: Mapping[str, tuple[Bar, ...]], weights: Mapping[str, float]
) -> list[RecentRegimeSummary]:
    windows = recent_windows(dates)
    rows: list[RecentRegimeSummary] = []
    for label, start, end in windows:
        candidate_return, benchmark_return, excess, drawdown = evaluate_weights(
            dates, dict(data), dict(weights), BENCHMARK_SYMBOLS, start, end
        )
        reasons: list[str] = []
        if excess < -0.05:
            reasons.append("recent_excess_below_minus_5pp")
        if drawdown < -0.20:
            reasons.append("recent_mdd_worse_than_minus_20pct")
        if candidate_return <= 0:
            reasons.append("recent_return_not_positive")
        rows.append(
            RecentRegimeSummary(
                window=label,
                start=dates[start].isoformat(),
                end=dates[end - 1].isoformat(),
                candidate_return=candidate_return,
                benchmark_return=benchmark_return,
                excess_return=excess,
                max_drawdown=drawdown,
                status="pass" if not reasons else "review",
                failure_reasons=tuple(reasons),
            )
        )
    return rows


def recent_windows(dates: tuple[date, ...]) -> tuple[tuple[str, int, int], ...]:
    labels = [
        ("post_2020", date(2020, 1, 1)),
        ("post_2022", date(2022, 1, 1)),
        ("ai_proxy_post_2023", date(2023, 1, 1)),
    ]
    windows: list[tuple[str, int, int]] = []
    for label, start_date in labels:
        start = next(
            (index for index, active_date in enumerate(dates) if active_date >= start_date), None
        )
        if start is not None and len(dates) - start >= 126:
            windows.append((label, start, len(dates)))
    for days in (504, 252):
        if len(dates) >= days:
            windows.append((f"trailing_{days}d", len(dates) - days, len(dates)))
    return tuple(windows)


def build_macro_proxy_summary(
    dates: tuple[date, ...], data: Mapping[str, tuple[Bar, ...]]
) -> dict[str, Any]:
    proxies: dict[str, Any] = {
        "method": "price-based proxy because FRED API requires a user API key",
        "fred_api_key_documentation": FRED_API_KEY_DOC_URL,
    }
    for symbol in ("TLT", "IEF", "SHY", "GLD", "SPY"):
        if symbol not in data:
            continue
        bars = data[symbol]
        trailing = min(252, len(bars) - 1)
        if trailing <= 0:
            continue
        ret = (bars[-1].close / bars[-trailing].close) - 1.0
        proxies[f"{symbol.lower()}_trailing_{trailing}d_return"] = ret
        proxies[f"{symbol.lower()}_last_date"] = dates[-1].isoformat()
    tlt = proxies.get("tlt_trailing_252d_return")
    spy = proxies.get("spy_trailing_252d_return")
    if isinstance(tlt, float) and isinstance(spy, float):
        proxies["rate_proxy_regime"] = (
            "bond_pressure" if tlt < 0 and spy > 0 else "mixed_or_defensive"
        )
    return proxies


def write_markdown(path: Path, report: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Fundamental, macro-proxy, and recent-regime gate",
        "",
        "Safety: offline research only; non-leveraged; no orders, no broker, no investment advice.",
        "",
        "## Summary",
        "",
        f"- Candidates checked: {report['summary']['candidates']}",
        f"- Passing full gate: {report['summary']['passed']}",
        f"- Review required: {report['summary']['review']}",
        (
            f"- Top candidate: {report['summary']['top_candidate']} "
            f"({report['summary']['top_status']})"
        ),
        "",
        "## Data-source limits",
        "",
    ]
    for item in report["limitations"]:
        lines.append(f"- {item}")
    lines.extend(
        [
            "",
            "## Candidate gates",
            "",
            (
                "| Candidate | Status | Base excess | Holdout excess | Worst MDD | "
                "Fundamentals | Recent regimes | Reasons |"
            ),
            "| --- | --- | ---: | ---: | ---: | --- | --- | --- |",
        ]
    )
    for row in report["candidate_gates"]:
        lines.append(
            (
                "| {name} | {status} | {base} | {holdout} | {mdd} | {fund} | {recent} | {reasons} |"
            ).format(
                name=row["name"],
                status=row["status"],
                base=percent(row["base_median_excess"]),
                holdout=percent(row["base_holdout_excess"]),
                mdd=percent(row["base_worst_mdd"]),
                fund=row["fundamental_status"],
                recent=row["recent_regime_status"],
                reasons=", ".join(row["failure_reasons"]) or "-",
            )
        )
    lines.extend(["", "## Top candidate recent-regime detail", ""])
    if report["candidate_gates"]:
        top = report["candidate_gates"][0]
        lines.extend(
            [
                f"Candidate: `{top['name']}`",
                "",
                "| Window | Status | Return | Benchmark | Excess | MDD | Reasons |",
                "| --- | --- | ---: | ---: | ---: | ---: | --- |",
            ]
        )
        for regime in top["recent_regimes"]:
            lines.append(
                "| {window} | {status} | {ret} | {bench} | {excess} | {mdd} | {reasons} |".format(
                    window=regime["window"],
                    status=regime["status"],
                    ret=percent(regime["candidate_return"]),
                    bench=percent(regime["benchmark_return"]),
                    excess=percent(regime["excess_return"]),
                    mdd=percent(regime["max_drawdown"]),
                    reasons=", ".join(regime["failure_reasons"]) or "-",
                )
            )
    path.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
