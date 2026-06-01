"""Build broad US market feature gates for no-order research.

The gate deliberately separates "collect a lot of market data" from "use it".
It aggregates broad price, breadth, sector, and cross-asset features, then marks
features as usable only when coverage/freshness/conflict checks pass. It never
connects to brokers, reads broker credentials, or creates orders.
"""

from __future__ import annotations

import argparse
import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from statistics import fmean, median, pstdev
from typing import Any

try:
    from scripts.non_leveraged_universe_analysis import looks_leveraged, percent
    from scripts.strategy_optimization import fetch_or_load_bars
except ModuleNotFoundError:  # pragma: no cover - direct script execution path
    from non_leveraged_universe_analysis import looks_leveraged, percent  # type: ignore[no-redef]
    from strategy_optimization import fetch_or_load_bars  # type: ignore[no-redef]

from auto_trading_bot.domain import Bar

DEFAULT_SYMBOLS_FILE = "data/universe/us_dynamic_liquid_watchlist.txt"
FALLBACK_SYMBOLS_FILE = "data/universe/us_large_liquid_watchlist.txt"
DEFAULT_OUTPUT = ".omx/reports/market-data-feature-gate-latest.json"
DEFAULT_MARKDOWN = ".omx/reports/market-data-feature-gate-latest.md"
CORE_CROSS_ASSETS = ("SPY", "QQQ", "DIA", "IWM", "GLD", "TLT", "IEF", "SHY", "VNQ")
SECTOR_ETFS = ("XLK", "XLV", "XLP", "XLU", "XLF", "XLE", "XLI", "XLY", "XLC", "XLRE", "XLB")
TRADING_DAYS_PER_YEAR = 252


@dataclass(frozen=True)
class AssetFeature:
    symbol: str
    status: str
    latest_date: str | None
    rows: int
    close: float | None
    avg_dollar_volume_20d: float | None
    return_5d: float | None
    return_20d: float | None
    return_63d: float | None
    return_126d: float | None
    realized_vol_20d: float | None
    max_drawdown_63d: float | None
    above_sma50: bool | None
    above_sma200: bool | None
    failure_reasons: tuple[str, ...]


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build broad no-order market feature gate.")
    parser.add_argument("--symbols", nargs="+", default=None)
    parser.add_argument("--symbols-file", default=DEFAULT_SYMBOLS_FILE)
    parser.add_argument("--start", default="2015-01-01")
    parser.add_argument("--end", default=date.today().isoformat())
    parser.add_argument("--data-dir", default="data/external")
    parser.add_argument("--max-symbols", type=int, default=250)
    parser.add_argument("--min-usable-assets", type=int, default=50)
    parser.add_argument("--min-breadth-coverage", type=float, default=0.70)
    parser.add_argument("--max-freshness-lag-days", type=int, default=7)
    parser.add_argument("--force-refresh", action="store_true")
    parser.add_argument("--output", default=DEFAULT_OUTPUT)
    parser.add_argument("--markdown", default=DEFAULT_MARKDOWN)
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
        "market feature gate status={status} usable={usable} "
        "breadth={breadth:.1%} regime={regime}"
    )
    print(
        status_line.format(
            status=report["summary"]["status"],
            usable=report["summary"]["usable_assets"],
            breadth=report["breadth"]["coverage_ratio"],
            regime=report["regime"]["label"],
        )
    )
    print(f"json={output}")
    print(f"markdown={markdown}")
    return 0


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    requested = resolve_symbols(args.symbols, Path(args.symbols_file))
    core = tuple(symbol for symbol in (*CORE_CROSS_ASSETS, *SECTOR_ETFS) if symbol not in requested)
    symbols = tuple(dict.fromkeys((*requested[: int(args.max_symbols)], *core)))
    blocked = tuple(symbol for symbol in symbols if looks_leveraged(symbol))
    allowed = tuple(symbol for symbol in symbols if symbol not in blocked)
    start = date.fromisoformat(args.start)
    end = date.fromisoformat(args.end)
    features, metadata = load_feature_rows(
        allowed,
        start=start,
        end=end,
        data_dir=Path(args.data_dir),
        force_refresh=bool(args.force_refresh),
    )
    usable = [feature for feature in features if feature.status == "ok"]
    breadth = breadth_summary(features, usable, min_coverage=float(args.min_breadth_coverage))
    sector = sector_summary(features)
    cross_asset = cross_asset_summary(features)
    quality_blockers = quality_gate_blockers(
        features,
        usable,
        min_usable_assets=int(args.min_usable_assets),
        min_breadth_coverage=float(args.min_breadth_coverage),
        max_freshness_lag_days=int(args.max_freshness_lag_days),
    )
    regime = regime_summary(breadth, sector, cross_asset, quality_blockers)
    useful = not quality_blockers and regime["label"] != "conflicted"
    status = "pass" if useful else "review"
    return {
        "status": "ok",
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "safety": "market data feature gate only; no orders; no broker; no credentials; no advice",
        "live_trading_authorized": False,
        "summary": {
            "status": status,
            "use_for_strategy_promotion": useful,
            "requested_symbols": len(requested),
            "loaded_symbols": len(features),
            "usable_assets": len(usable),
            "blocked_leveraged_or_inverse": len(blocked),
            "quality_blockers": len(quality_blockers),
            "regime": regime["label"],
            "recommendation": recommendation(status, regime, quality_blockers),
            "order_created": False,
        },
        "quality_gate": {
            "blockers": quality_blockers,
            "min_usable_assets": int(args.min_usable_assets),
            "min_breadth_coverage": float(args.min_breadth_coverage),
            "max_freshness_lag_days": int(args.max_freshness_lag_days),
        },
        "breadth": breadth,
        "sector": sector,
        "cross_asset": cross_asset,
        "regime": regime,
        "top_assets": top_assets(usable),
        "weak_assets": weak_assets(usable),
        "features": [asdict(row) for row in features],
        "data_metadata": metadata,
        "blocked_symbols": blocked,
        "required_next_evidence": [
            "Use this feature pack only as a gate/diagnostic until walk-forward tests prove value.",
            "Do not promote or live-trade a strategy when quality_blockers is non-empty.",
            "Do not let broad-market features rewrite code automatically; "
            "review and test changes first.",
        ],
    }


def resolve_symbols(cli_symbols: Sequence[str] | None, symbols_file: Path) -> tuple[str, ...]:
    raw = list(cli_symbols) if cli_symbols else read_symbols_file(symbols_file)
    if not raw and symbols_file != Path(FALLBACK_SYMBOLS_FILE):
        raw = read_symbols_file(Path(FALLBACK_SYMBOLS_FILE))
    normalized: list[str] = []
    for symbol in raw:
        clean = symbol.strip().upper()
        if clean and clean not in normalized:
            normalized.append(clean)
    return tuple(normalized)


def read_symbols_file(path: Path) -> list[str]:
    if not path.exists():
        return []
    return [
        clean
        for line in path.read_text(encoding="utf-8").splitlines()
        if (clean := line.split("#", 1)[0].strip())
    ]


def load_feature_rows(
    symbols: Sequence[str], *, start: date, end: date, data_dir: Path, force_refresh: bool
) -> tuple[list[AssetFeature], list[dict[str, Any]]]:
    features: list[AssetFeature] = []
    metadata: list[dict[str, Any]] = []
    for symbol in symbols:
        bars, meta = fetch_or_load_bars(
            user_symbol=symbol,
            start=start,
            end=end,
            data_dir=data_dir,
            force_refresh=force_refresh,
        )
        metadata.append(meta)
        features.append(asset_feature(symbol, bars, meta))
    return features, metadata


def asset_feature(
    symbol: str, bars: Sequence[Bar] | None, metadata: Mapping[str, Any]
) -> AssetFeature:
    if not bars:
        return AssetFeature(
            symbol,
            "blocked",
            None,
            0,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            ("price_data_missing",),
        )
    ordered = tuple(sorted(bars, key=lambda bar: bar.timestamp))
    failures: list[str] = []
    if metadata.get("status") != "ok":
        failures.append("price_metadata_not_ok")
    if len(ordered) < 220:
        failures.append("insufficient_history_for_200d_features")
    latest = ordered[-1]
    closes = [bar.close for bar in ordered]
    returns = daily_returns(closes)
    status = "ok" if not failures else "review"
    return AssetFeature(
        symbol=symbol,
        status=status,
        latest_date=latest.timestamp.date().isoformat(),
        rows=len(ordered),
        close=latest.close,
        avg_dollar_volume_20d=average_dollar_volume(ordered, 20),
        return_5d=period_return(closes, 5),
        return_20d=period_return(closes, 20),
        return_63d=period_return(closes, 63),
        return_126d=period_return(closes, 126),
        realized_vol_20d=annualized_vol(returns[-20:]),
        max_drawdown_63d=drawdown(closes[-63:]),
        above_sma50=above_sma(closes, 50),
        above_sma200=above_sma(closes, 200),
        failure_reasons=tuple(failures),
    )


def period_return(closes: Sequence[float], lookback: int) -> float | None:
    if len(closes) <= lookback or closes[-lookback - 1] <= 0:
        return None
    return closes[-1] / closes[-lookback - 1] - 1.0


def daily_returns(closes: Sequence[float]) -> list[float]:
    return [
        closes[index] / closes[index - 1] - 1.0
        for index in range(1, len(closes))
        if closes[index - 1] > 0
    ]


def annualized_vol(returns: Sequence[float]) -> float | None:
    if len(returns) < 2:
        return None
    return pstdev(returns) * math.sqrt(TRADING_DAYS_PER_YEAR)


def average_dollar_volume(bars: Sequence[Bar], lookback: int) -> float | None:
    if len(bars) < lookback:
        return None
    rows = bars[-lookback:]
    return fmean(bar.close * bar.volume for bar in rows)


def above_sma(closes: Sequence[float], window: int) -> bool | None:
    if len(closes) < window:
        return None
    return closes[-1] > fmean(closes[-window:])


def drawdown(closes: Sequence[float]) -> float | None:
    if len(closes) < 2:
        return None
    peak = closes[0]
    worst = 0.0
    for close in closes:
        peak = max(peak, close)
        if peak > 0:
            worst = min(worst, close / peak - 1.0)
    return worst


def breadth_summary(
    features: Sequence[AssetFeature], usable: Sequence[AssetFeature], *, min_coverage: float
) -> dict[str, Any]:
    loaded = len(features)
    coverage = len(usable) / loaded if loaded else 0.0
    ret20 = values(feature.return_20d for feature in usable)
    ret63 = values(feature.return_63d for feature in usable)
    vol20 = values(feature.realized_vol_20d for feature in usable)
    above50 = ratio(feature.above_sma50 is True for feature in usable)
    above200 = ratio(feature.above_sma200 is True for feature in usable)
    positive20 = ratio(
        (feature.return_20d or 0.0) > 0
        for feature in usable
        if feature.return_20d is not None
    )
    return {
        "status": "pass" if coverage >= min_coverage and usable else "review",
        "coverage_ratio": coverage,
        "usable_assets": len(usable),
        "loaded_assets": loaded,
        "above_sma50_ratio": above50,
        "above_sma200_ratio": above200,
        "positive_20d_return_ratio": positive20,
        "median_return_20d": median(ret20) if ret20 else None,
        "median_return_63d": median(ret63) if ret63 else None,
        "median_realized_vol_20d": median(vol20) if vol20 else None,
    }


def sector_summary(features: Sequence[AssetFeature]) -> dict[str, Any]:
    by_symbol = {feature.symbol: feature for feature in features}
    sectors = [
        by_symbol[symbol]
        for symbol in SECTOR_ETFS
        if symbol in by_symbol and by_symbol[symbol].return_20d is not None
    ]
    ranked = sorted(sectors, key=lambda feature: feature.return_20d or -999.0, reverse=True)
    returns = values(feature.return_20d for feature in sectors)
    dispersion = (max(returns) - min(returns)) if returns else None
    defensive = {"XLP", "XLU", "XLV"}
    cyclical = {"XLK", "XLY", "XLF", "XLI", "XLE"}
    defensive_values = values(by_symbol[s].return_20d for s in defensive if s in by_symbol)
    cyclical_values = values(by_symbol[s].return_20d for s in cyclical if s in by_symbol)
    defensive_return = median(defensive_values) if defensive_values else None
    cyclical_return = median(cyclical_values) if cyclical_values else None
    return {
        "status": "pass" if len(sectors) >= 8 else "review",
        "sector_count": len(sectors),
        "best_20d": ranked[0].symbol if ranked else None,
        "worst_20d": ranked[-1].symbol if ranked else None,
        "return_dispersion_20d": dispersion,
        "defensive_median_return_20d": defensive_return,
        "cyclical_median_return_20d": cyclical_return,
        "leadership": [
            {
                "symbol": feature.symbol,
                "return_20d": feature.return_20d,
                "above_sma50": feature.above_sma50,
            }
            for feature in ranked[:5]
        ],
    }


def cross_asset_summary(features: Sequence[AssetFeature]) -> dict[str, Any]:
    by_symbol = {feature.symbol: feature for feature in features}

    def ret(symbol: str, attr: str = "return_20d") -> float | None:
        feature = by_symbol.get(symbol)
        return getattr(feature, attr) if feature else None

    spy20 = ret("SPY")
    qqq20 = ret("QQQ")
    iwm20 = ret("IWM")
    gld20 = ret("GLD")
    tlt20 = ret("TLT")
    shy20 = ret("SHY")
    risk_on_score = sum(
        1
        for condition in (
            spy20 is not None and spy20 > 0,
            qqq20 is not None and spy20 is not None and qqq20 >= spy20,
            iwm20 is not None and spy20 is not None and iwm20 >= spy20,
            gld20 is not None and spy20 is not None and spy20 >= gld20,
            tlt20 is not None and spy20 is not None and spy20 >= tlt20,
        )
        if condition
    )
    curve_proxy = None if tlt20 is None or shy20 is None else tlt20 - shy20
    return {
        "status": "pass" if spy20 is not None else "review",
        "risk_on_score_0_5": risk_on_score,
        "spy_return_20d": spy20,
        "qqq_minus_spy_20d": None if qqq20 is None or spy20 is None else qqq20 - spy20,
        "iwm_minus_spy_20d": None if iwm20 is None or spy20 is None else iwm20 - spy20,
        "gld_minus_spy_20d": None if gld20 is None or spy20 is None else gld20 - spy20,
        "tlt_minus_shy_20d": curve_proxy,
    }


def quality_gate_blockers(
    features: Sequence[AssetFeature],
    usable: Sequence[AssetFeature],
    *,
    min_usable_assets: int,
    min_breadth_coverage: float,
    max_freshness_lag_days: int,
) -> list[str]:
    blockers: list[str] = []
    if len(usable) < min_usable_assets:
        blockers.append("too_few_usable_market_features")
    coverage = len(usable) / len(features) if features else 0.0
    if coverage < min_breadth_coverage:
        blockers.append("market_feature_coverage_below_threshold")
    latest_dates = [
        date.fromisoformat(feature.latest_date)
        for feature in usable
        if feature.latest_date
    ]
    if latest_dates:
        lag = (max(latest_dates) - min(latest_dates)).days
        if lag > max_freshness_lag_days:
            blockers.append("market_feature_freshness_dispersion_too_wide")
    else:
        blockers.append("market_feature_latest_dates_missing")
    return blockers


def regime_summary(
    breadth: Mapping[str, Any],
    sector: Mapping[str, Any],
    cross_asset: Mapping[str, Any],
    quality_blockers: Sequence[str],
) -> dict[str, Any]:
    if quality_blockers:
        return {
            "label": "insufficient_data",
            "confidence": "low",
            "reasons": list(quality_blockers),
        }
    risk_on_score = int(cross_asset.get("risk_on_score_0_5", 0) or 0)
    above200 = float(breadth.get("above_sma200_ratio") or 0.0)
    positive20 = float(breadth.get("positive_20d_return_ratio") or 0.0)
    reasons = [
        f"risk_on_score={risk_on_score}/5",
        f"above_sma200={above200:.1%}",
        f"positive_20d={positive20:.1%}",
    ]
    if risk_on_score >= 4 and above200 >= 0.55 and positive20 >= 0.55:
        return {"label": "risk_on", "confidence": "medium", "reasons": reasons}
    if risk_on_score <= 2 and above200 <= 0.45 and positive20 <= 0.45:
        return {"label": "risk_off", "confidence": "medium", "reasons": reasons}
    return {"label": "conflicted", "confidence": "low", "reasons": reasons}


def recommendation(status: str, regime: Mapping[str, Any], blockers: Sequence[str]) -> str:
    if blockers:
        return "do_not_use_for_strategy_changes_until_data_quality_improves"
    if regime.get("label") == "risk_off":
        return "use_as_risk_warning_only_do_not_increase_exposure"
    if regime.get("label") == "risk_on" and status == "pass":
        return "usable_as_context_after_walk_forward_validation_not_as_standalone_signal"
    return "review_only_market_signals_are_conflicted"


def top_assets(usable: Sequence[AssetFeature]) -> list[dict[str, Any]]:
    ranked = sorted(
        [feature for feature in usable if feature.return_20d is not None],
        key=lambda feature: feature.return_20d or -999.0,
        reverse=True,
    )
    return [compact_asset(feature) for feature in ranked[:10]]


def weak_assets(usable: Sequence[AssetFeature]) -> list[dict[str, Any]]:
    ranked = sorted(
        [feature for feature in usable if feature.return_20d is not None],
        key=lambda feature: feature.return_20d or 999.0,
    )
    return [compact_asset(feature) for feature in ranked[:10]]


def compact_asset(feature: AssetFeature) -> dict[str, Any]:
    return {
        "symbol": feature.symbol,
        "return_20d": feature.return_20d,
        "return_63d": feature.return_63d,
        "realized_vol_20d": feature.realized_vol_20d,
        "above_sma50": feature.above_sma50,
        "above_sma200": feature.above_sma200,
    }


def values(raw: Sequence[float | None] | Any) -> list[float]:
    return [
        float(value)
        for value in raw
        if isinstance(value, int | float) and math.isfinite(value)
    ]


def ratio(raw: Any) -> float | None:
    rows = list(raw)
    if not rows:
        return None
    return sum(1 for value in rows if value) / len(rows)


def write_markdown(path: Path, report: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    summary = report["summary"]
    breadth = report["breadth"]
    sector = report["sector"]
    cross = report["cross_asset"]
    regime = report["regime"]
    lines = [
        "# Market data feature gate",
        "",
        "Safety: market feature diagnostics only; no orders, no broker, no advice.",
        "",
        "## Summary",
        "",
        f"- Status: `{summary['status']}`",
        f"- Use for strategy promotion: `{summary['use_for_strategy_promotion']}`",
        f"- Recommendation: `{summary['recommendation']}`",
        f"- Requested symbols: `{summary['requested_symbols']}`",
        f"- Loaded symbols: `{summary['loaded_symbols']}`",
        f"- Usable assets: `{summary['usable_assets']}`",
        f"- Quality blockers: `{summary['quality_blockers']}`",
        f"- Regime: `{regime['label']}` / confidence `{regime['confidence']}`",
        f"- Live trading authorized: `{report['live_trading_authorized']}`",
        "",
        "## Breadth",
        "",
        f"- Coverage: `{percent(breadth['coverage_ratio'])}`",
        f"- Above SMA50: `{percent(breadth['above_sma50_ratio'])}`",
        f"- Above SMA200: `{percent(breadth['above_sma200_ratio'])}`",
        f"- Positive 20d return: `{percent(breadth['positive_20d_return_ratio'])}`",
        f"- Median 20d return: `{percent(breadth['median_return_20d'])}`",
        f"- Median 63d return: `{percent(breadth['median_return_63d'])}`",
        "",
        "## Sector / cross-asset",
        "",
        f"- Sector count: `{sector['sector_count']}`",
        f"- Best sector 20d: `{sector['best_20d']}`",
        f"- Worst sector 20d: `{sector['worst_20d']}`",
        f"- Risk-on score: `{cross['risk_on_score_0_5']} / 5`",
        f"- QQQ minus SPY 20d: `{percent(cross['qqq_minus_spy_20d'])}`",
        f"- IWM minus SPY 20d: `{percent(cross['iwm_minus_spy_20d'])}`",
        f"- GLD minus SPY 20d: `{percent(cross['gld_minus_spy_20d'])}`",
        "",
        "## Quality blockers",
        "",
    ]
    blockers = report["quality_gate"]["blockers"]
    lines.extend(f"- {blocker}" for blocker in blockers or ["none"])
    lines.extend(
        [
            "",
            "## Top 20d assets",
            "",
            "| Symbol | 20d | 63d | Vol 20d |",
            "| --- | ---: | ---: | ---: |",
        ]
    )
    for row in report["top_assets"][:10]:
        lines.append(
            f"| {row['symbol']} | {percent(row['return_20d'])} | "
            f"{percent(row['return_63d'])} | {percent(row['realized_vol_20d'])} |"
        )
    lines.extend(
        [
            "",
            "## Weak 20d assets",
            "",
            "| Symbol | 20d | 63d | Vol 20d |",
            "| --- | ---: | ---: | ---: |",
        ]
    )
    for row in report["weak_assets"][:10]:
        lines.append(
            f"| {row['symbol']} | {percent(row['return_20d'])} | "
            f"{percent(row['return_63d'])} | {percent(row['realized_vol_20d'])} |"
        )
    path.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
