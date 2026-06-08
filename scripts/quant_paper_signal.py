"""Generate a no-order quant paper portfolio from broad market features.

This is a quantitative research signal only. It reads already-collected market
feature diagnostics, builds diversified paper-only candidate portfolios, and may
write a dry-run signal for observation. It never connects to brokers, reads
trading credentials, or creates orders.
"""

from __future__ import annotations

import argparse
import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

try:
    from scripts.non_leveraged_universe_analysis import looks_leveraged, percent
    from scripts.paper_signal_dry_run import build_signal
except ModuleNotFoundError:  # pragma: no cover - direct script execution path
    from non_leveraged_universe_analysis import looks_leveraged, percent  # type: ignore[no-redef]
    from paper_signal_dry_run import build_signal  # type: ignore[no-redef]

DEFAULT_MARKET_FEATURE_GATE = ".omx/reports/market-data-feature-gate-latest.json"
DEFAULT_OUTPUT = "reports/paper-quant-signal-latest.json"
DEFAULT_REPORT = ".omx/reports/quant-paper-selection-latest.json"
DEFAULT_MARKDOWN = ".omx/reports/quant-paper-selection-latest.md"
DEFENSIVE_SYMBOLS = ("SHY", "GLD", "IEF", "TLT")
SECTOR_SYMBOLS = ("XLK", "XLV", "XLP", "XLU", "XLF", "XLE", "XLI", "XLY", "XLC", "XLRE", "XLB")
CORE_RISK_SYMBOLS = ("SPY", "QQQ", "IWM", "DIA")
MAX_WEIGHT = 0.35


@dataclass(frozen=True)
class FeatureRow:
    symbol: str
    return_20d: float
    return_63d: float
    realized_vol_20d: float
    max_drawdown_63d: float
    above_sma50: bool
    above_sma200: bool
    avg_dollar_volume_20d: float


@dataclass(frozen=True)
class QuantCandidate:
    name: str
    family: str
    weights: dict[str, float]
    score: float
    status: str
    failure_reasons: tuple[str, ...]
    rationale: tuple[str, ...]


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Write no-order quant paper signal.")
    parser.add_argument("--market-feature-gate", default=DEFAULT_MARKET_FEATURE_GATE)
    parser.add_argument("--output", default=DEFAULT_OUTPUT)
    parser.add_argument("--report", default=DEFAULT_REPORT)
    parser.add_argument("--markdown", default=DEFAULT_MARKDOWN)
    parser.add_argument("--start", default="2015-01-01")
    parser.add_argument("--end", default=date.today().isoformat())
    parser.add_argument("--data-dir", default="data/external")
    parser.add_argument("--force-refresh", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    report = build_report(args)
    report_path = Path(args.report)
    markdown_path = Path(args.markdown)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    write_markdown(markdown_path, report)
    summary = report["summary"]
    print(
        (
            "quant paper status={status} strategy={strategy} "
            "candidates={candidates} blockers={blockers}"
        ).format(
            status=summary["status"],
            strategy=summary.get("selected_strategy"),
            candidates=summary["candidate_count"],
            blockers=len(report["blockers"]),
        )
    )
    print(f"json={report_path}")
    print(f"markdown={markdown_path}")
    return 0


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    generated_at = datetime.now(tz=UTC)
    market_feature_gate = read_json_if_exists(Path(args.market_feature_gate))
    blockers: list[str] = []
    if market_feature_gate is None:
        blockers.append("market_feature_gate_missing_for_quant_signal")

    candidates: list[QuantCandidate] = []
    regime = "unknown"
    feature_quality_status = "missing"
    if market_feature_gate is not None:
        regime = str(mapping(market_feature_gate.get("regime")).get("label") or "unknown")
        feature_quality_status = str(
            mapping(market_feature_gate.get("summary")).get("status") or "missing"
        )
        candidates = build_candidates(market_feature_gate)
        if not candidates:
            blockers.append("no_quant_candidate_from_market_features")

    selected = select_candidate(candidates)
    signal_payload: dict[str, Any] | None = None
    signal_blockers: list[str] = []
    if selected is not None:
        signal_payload, signal_blockers = write_signal(args, selected)
        blockers.extend(signal_blockers)

    status = quant_status(selected, blockers)
    selected_weights = selected.weights if selected else {}
    return {
        "status": "ok",
        "generated_at": generated_at.isoformat(),
        "safety": "quant paper signal only; no orders; no broker; no credentials; no advice",
        "live_trading_authorized": False,
        "paper_api_authorized": False,
        "summary": {
            "status": status,
            "feature_quality_status": feature_quality_status,
            "regime": regime,
            "candidate_count": len(candidates),
            "selected_strategy": selected.name if selected else None,
            "selected_family": selected.family if selected else None,
            "selected_symbols": sorted(selected_weights),
            "selected_weights": selected_weights,
            "selected_score": selected.score if selected else None,
            "max_weight": max(selected_weights.values()) if selected_weights else None,
            "use_for_strategy_promotion": False,
            "primary_strategy_changed": False,
            "output": str(args.output) if signal_payload else None,
            "order_created": False,
            "live_trading_authorized": False,
        },
        "selected_candidate": as_candidate_dict(selected),
        "candidates": [as_candidate_dict(candidate) for candidate in candidates],
        "signal": compact_signal(signal_payload),
        "blockers": blockers,
        "required_next_evidence": [
            "Track this quant candidate separately from the locked champion baseline.",
            "Do not promote quant weights to live trading without forward paper evidence.",
            "Do not let a conflicted regime or quality blocker increase real-money exposure.",
        ],
    }


def build_candidates(report: Mapping[str, Any]) -> list[QuantCandidate]:
    rows = usable_features(report)
    regime = str(mapping(report.get("regime")).get("label") or "unknown")
    quality_blockers = list(mapping(report.get("quality_gate")).get("blockers") or [])
    risk_budget = risk_budget_for_regime(regime)
    candidates = [
        momentum_candidate(rows, risk_budget, regime, quality_blockers),
        sector_rotation_candidate(rows, risk_budget, regime, quality_blockers),
        core_risk_parity_candidate(rows, regime, quality_blockers),
        defensive_min_vol_candidate(rows, regime, quality_blockers),
    ]
    return sorted(
        [candidate for candidate in candidates if candidate is not None],
        key=candidate_sort_key,
    )


def candidate_sort_key(candidate: QuantCandidate) -> tuple[int, int, float]:
    family_preference = {
        "momentum_plus_defensive": 0,
        "sector_rotation": 1,
        "inverse_volatility_core": 2,
        "defensive_min_volatility": 3,
    }
    return (
        0 if candidate.status == "pass" else 1,
        family_preference.get(candidate.family, 99),
        -candidate.score,
    )


def usable_features(report: Mapping[str, Any]) -> dict[str, FeatureRow]:
    rows: dict[str, FeatureRow] = {}
    raw_features = report.get("features", [])
    if not isinstance(raw_features, list):
        return rows
    for raw in raw_features:
        feature = parse_feature(raw)
        if feature is not None:
            rows[feature.symbol] = feature
    return rows


def parse_feature(raw: Any) -> FeatureRow | None:
    if not isinstance(raw, Mapping):
        return None
    symbol = str(raw.get("symbol") or "").upper()
    if not symbol or looks_leveraged(symbol) or raw.get("status") != "ok":
        return None
    ret20 = finite(raw.get("return_20d"))
    ret63 = finite(raw.get("return_63d"))
    vol20 = finite(raw.get("realized_vol_20d"))
    drawdown63 = finite(raw.get("max_drawdown_63d"))
    dollar_volume = finite(raw.get("avg_dollar_volume_20d"))
    if None in (ret20, ret63, vol20, drawdown63, dollar_volume):
        return None
    return FeatureRow(
        symbol=symbol,
        return_20d=float(ret20),
        return_63d=float(ret63),
        realized_vol_20d=max(float(vol20), 1e-6),
        max_drawdown_63d=float(drawdown63),
        above_sma50=raw.get("above_sma50") is True,
        above_sma200=raw.get("above_sma200") is True,
        avg_dollar_volume_20d=float(dollar_volume),
    )


def momentum_candidate(
    rows: Mapping[str, FeatureRow], risk_budget: float, regime: str, quality_blockers: Sequence[str]
) -> QuantCandidate | None:
    risk_rows = [
        row
        for row in rows.values()
        if row.symbol not in DEFENSIVE_SYMBOLS
        and row.return_20d > 0
        and row.return_63d > 0
        and row.above_sma50
        and row.above_sma200
    ]
    ranked = sorted(risk_rows, key=momentum_score, reverse=True)[:5]
    if len(ranked) < 3:
        return None
    weights = blend_with_defensive(
        {row.symbol: 1.0 for row in ranked},
        rows,
        risk_budget=risk_budget,
    )
    return candidate(
        name="quant_momentum_top5_defensive",
        family="momentum_plus_defensive",
        weights=weights,
        score=sum(momentum_score(row) for row in ranked) / len(ranked),
        regime=regime,
        quality_blockers=quality_blockers,
        rationale=(
            "Ranks assets by 20d/63d trend, SMA confirmation, volatility, and 63d drawdown.",
            (
                "Keeps a defensive sleeve so a broad scan does not become "
                "concentrated single-name chasing."
            ),
        ),
    )


def sector_rotation_candidate(
    rows: Mapping[str, FeatureRow], risk_budget: float, regime: str, quality_blockers: Sequence[str]
) -> QuantCandidate | None:
    sector_rows = [rows[symbol] for symbol in SECTOR_SYMBOLS if symbol in rows]
    ranked = sorted(sector_rows, key=momentum_score, reverse=True)[:3]
    if len(ranked) < 3:
        return None
    weights = blend_with_defensive(
        {row.symbol: 1.0 for row in ranked},
        rows,
        risk_budget=min(risk_budget, 0.60),
    )
    return candidate(
        name="quant_sector_rotation_top3_defensive",
        family="sector_rotation",
        weights=weights,
        score=sum(momentum_score(row) for row in ranked) / len(ranked),
        regime=regime,
        quality_blockers=quality_blockers,
        rationale=(
            "Rotates only among broad sector ETFs rather than individual stocks.",
            "Limits sector exposure and adds a defensive sleeve for regime uncertainty.",
        ),
    )


def core_risk_parity_candidate(
    rows: Mapping[str, FeatureRow], regime: str, quality_blockers: Sequence[str]
) -> QuantCandidate | None:
    symbols = [symbol for symbol in (*CORE_RISK_SYMBOLS, *DEFENSIVE_SYMBOLS) if symbol in rows]
    if len(symbols) < 4:
        return None
    raw = {symbol: 1.0 / rows[symbol].realized_vol_20d for symbol in symbols}
    weights = cap_and_normalize(raw, cap=0.30)
    score = sum(0.02 / rows[symbol].realized_vol_20d for symbol in symbols) / len(symbols)
    return candidate(
        name="quant_core_inverse_volatility",
        family="inverse_volatility_core",
        weights=weights,
        score=score,
        regime=regime,
        quality_blockers=quality_blockers,
        rationale=(
            "Uses core market ETFs with inverse-volatility sizing.",
            "Caps every symbol so the candidate remains diversified for paper observation.",
        ),
    )


def defensive_min_vol_candidate(
    rows: Mapping[str, FeatureRow], regime: str, quality_blockers: Sequence[str]
) -> QuantCandidate | None:
    defensive_pool = [
        row
        for row in rows.values()
        if row.symbol in (*DEFENSIVE_SYMBOLS, "XLP", "XLU", "XLV") and row.realized_vol_20d > 0
    ]
    ranked = sorted(defensive_pool, key=lambda row: (row.realized_vol_20d, -row.return_20d))[:4]
    if len(ranked) < 3:
        return None
    raw = {row.symbol: 1.0 / row.realized_vol_20d for row in ranked}
    weights = cap_and_normalize(raw, cap=0.35)
    score = sum(-row.realized_vol_20d + row.return_20d for row in ranked) / len(ranked)
    return candidate(
        name="quant_defensive_min_volatility",
        family="defensive_min_volatility",
        weights=weights,
        score=score,
        regime=regime,
        quality_blockers=quality_blockers,
        rationale=(
            "Tracks a low-volatility defensive paper alternative.",
            "Useful as a comparator when momentum candidates are unstable or regime is conflicted.",
        ),
    )


def candidate(
    *,
    name: str,
    family: str,
    weights: Mapping[str, float],
    score: float,
    regime: str,
    quality_blockers: Sequence[str],
    rationale: Sequence[str],
) -> QuantCandidate:
    normalized = normalize_weights(weights)
    failures: list[str] = []
    if quality_blockers:
        failures.append("market_feature_quality_blocked")
    if regime in {"conflicted", "insufficient_data", "unknown"}:
        failures.append(f"regime_{regime}_requires_review")
    if len(normalized) < 2:
        failures.append("portfolio_not_diversified")
    if max(normalized.values()) > MAX_WEIGHT:
        failures.append("max_weight_above_35pct")
    if any(looks_leveraged(symbol) for symbol in normalized):
        failures.append("leveraged_or_inverse_symbol_blocked")
    return QuantCandidate(
        name=name,
        family=family,
        weights=dict(sorted(normalized.items())),
        score=score,
        status="pass" if not failures else "review",
        failure_reasons=tuple(failures),
        rationale=tuple(rationale),
    )


def select_candidate(candidates: Sequence[QuantCandidate]) -> QuantCandidate | None:
    if not candidates:
        return None
    passing = [candidate for candidate in candidates if candidate.status == "pass"]
    return passing[0] if passing else candidates[0]


def write_signal(
    args: argparse.Namespace, selected: QuantCandidate
) -> tuple[dict[str, Any] | None, list[str]]:
    signal_args = argparse.Namespace(
        start=args.start,
        end=args.end,
        data_dir=args.data_dir,
        output=args.output,
        strategy=selected.name,
        weights=[f"{symbol}={weight}" for symbol, weight in selected.weights.items()],
        qqq_weight=0.36,
        gld_weight=0.64,
        force_refresh=args.force_refresh,
    )
    try:
        signal = build_signal(signal_args)
    except SystemExit as exc:
        return None, [f"quant_signal_build_failed:{exc}"]
    payload = asdict(signal)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return payload, []


def quant_status(selected: QuantCandidate | None, blockers: Sequence[str]) -> str:
    if selected is None:
        return "blocked"
    if blockers:
        return "blocked"
    return selected.status


def risk_budget_for_regime(regime: str) -> float:
    if regime == "risk_on":
        return 0.75
    if regime == "risk_off":
        return 0.30
    return 0.45


def blend_with_defensive(
    risk_raw: Mapping[str, float], rows: Mapping[str, FeatureRow], *, risk_budget: float
) -> dict[str, float]:
    defensive = [symbol for symbol in DEFENSIVE_SYMBOLS if symbol in rows]
    weights: dict[str, float] = {}
    if risk_raw:
        risk_weights = normalize_weights(risk_raw)
        weights.update({symbol: weight * risk_budget for symbol, weight in risk_weights.items()})
    defensive_budget = max(1.0 - risk_budget, 0.0)
    if defensive and defensive_budget > 0:
        defensive_raw = {
            symbol: max(1.0 / rows[symbol].realized_vol_20d, 0.0)
            for symbol in defensive
            if rows[symbol].realized_vol_20d > 0
        }
        defensive_weights = normalize_weights(defensive_raw)
        weights.update(
            {
                symbol: weights.get(symbol, 0.0) + weight * defensive_budget
                for symbol, weight in defensive_weights.items()
            }
        )
    return cap_and_normalize(weights, cap=MAX_WEIGHT)


def cap_and_normalize(raw: Mapping[str, float], *, cap: float) -> dict[str, float]:
    weights = normalize_weights(raw)
    capped: dict[str, float] = {}
    overflow = 0.0
    uncapped: set[str] = set(weights)
    for _ in range(10):
        changed = False
        for symbol in list(uncapped):
            value = weights[symbol]
            if value > cap:
                capped[symbol] = cap
                overflow += value - cap
                uncapped.remove(symbol)
                changed = True
        if not changed:
            break
        if uncapped and overflow > 0:
            total_uncapped = sum(weights[symbol] for symbol in uncapped)
            for symbol in uncapped:
                weights[symbol] += overflow * weights[symbol] / total_uncapped
            overflow = 0.0
    for symbol in uncapped:
        capped[symbol] = weights[symbol]
    return normalize_weights(capped)


def normalize_weights(raw: Mapping[str, float]) -> dict[str, float]:
    cleaned = {str(symbol).upper(): float(weight) for symbol, weight in raw.items() if weight > 0}
    total = sum(cleaned.values())
    if total <= 0:
        return {}
    return {symbol: weight / total for symbol, weight in sorted(cleaned.items())}


def momentum_score(row: FeatureRow) -> float:
    trend_bonus = 0.03 * int(row.above_sma50) + 0.04 * int(row.above_sma200)
    liquidity_bonus = min(math.log10(max(row.avg_dollar_volume_20d, 1.0)) / 1_000.0, 0.02)
    drawdown_penalty = abs(min(row.max_drawdown_63d, 0.0)) * 0.4
    volatility_penalty = row.realized_vol_20d * 0.25
    return (
        row.return_63d * 0.55
        + row.return_20d * 0.35
        + trend_bonus
        + liquidity_bonus
        - drawdown_penalty
        - volatility_penalty
    )


def finite(value: Any) -> float | None:
    if not isinstance(value, int | float):
        return None
    as_float = float(value)
    return as_float if math.isfinite(as_float) else None


def mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def read_json_if_exists(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else None


def as_candidate_dict(candidate: QuantCandidate | None) -> dict[str, Any] | None:
    if candidate is None:
        return None
    return {
        "name": candidate.name,
        "family": candidate.family,
        "weights": candidate.weights,
        "score": candidate.score,
        "status": candidate.status,
        "failure_reasons": candidate.failure_reasons,
        "rationale": candidate.rationale,
    }


def compact_signal(signal: Mapping[str, Any] | None) -> dict[str, Any] | None:
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
    summary = mapping(report["summary"])
    lines = [
        "# Quant paper signal",
        "",
        "Safety: quant paper signal only; no orders, no broker, no credentials, no advice.",
        "",
        "## Summary",
        "",
        f"- Status: `{summary.get('status')}`",
        f"- Feature quality: `{summary.get('feature_quality_status')}`",
        f"- Regime: `{summary.get('regime')}`",
        f"- Selected strategy: `{summary.get('selected_strategy')}`",
        f"- Selected family: `{summary.get('selected_family')}`",
        f"- Max weight: `{percent(summary.get('max_weight'))}`",
        f"- Use for strategy promotion: `{summary.get('use_for_strategy_promotion')}`",
        f"- Order created: `{summary.get('order_created')}`",
        f"- Live trading authorized: `{summary.get('live_trading_authorized')}`",
        "",
        "## Selected weights",
        "",
        "| Symbol | Weight |",
        "| --- | ---: |",
    ]
    selected_weights = mapping(summary.get("selected_weights"))
    for symbol, weight in sorted(
        selected_weights.items(), key=lambda item: float(item[1]), reverse=True
    ):
        lines.append(f"| {symbol} | {percent(float(weight))} |")
    lines.extend(
        [
            "",
            "## Candidate ranking",
            "",
            "| Strategy | Status | Score | Reasons |",
            "| --- | --- | ---: | --- |",
        ]
    )
    for candidate_row in report.get("candidates", []):
        candidate_map = mapping(candidate_row)
        reasons = candidate_map.get("failure_reasons") or []
        lines.append(
            "| {name} | {status} | {score:.4f} | {reasons} |".format(
                name=candidate_map.get("name"),
                status=candidate_map.get("status"),
                score=float(candidate_map.get("score") or 0.0),
                reasons=", ".join(str(reason) for reason in reasons) or "-",
            )
        )
    lines.extend(["", "## Blockers", ""])
    lines.extend(f"- {blocker}" for blocker in report.get("blockers", []) or ["none"])
    lines.extend(["", "## Required next evidence", ""])
    lines.extend(f"- {item}" for item in report.get("required_next_evidence", []))
    path.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
