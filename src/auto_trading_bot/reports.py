"""Markdown and JSON report generation for offline MVP backtests."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field, is_dataclass
from pathlib import Path
from typing import Any, cast

from .validation import DisqualificationFlag, flags_to_dicts

SAFETY_STATEMENT = "This MVP cannot place orders and is not approval for live trading."
DEFAULT_CAVEATS = [
    SAFETY_STATEMENT,
    "Backtests and paper trading are not live-trading proof.",
    "This report is not investment advice and does not guarantee profit.",
]


@dataclass(frozen=True)
class ReportInputs:
    """Serializable report payload shared by markdown and JSON writers."""

    strategy: str
    data_period: str
    assumptions: Mapping[str, Any]
    metrics: Mapping[str, Any]
    market: str = "unspecified"
    symbol: str = "unspecified"
    benchmark_metrics: Mapping[str, Any] = field(default_factory=dict)
    validation: Mapping[str, Any] = field(default_factory=dict)
    disqualification_flags: Sequence[DisqualificationFlag | Mapping[str, Any]] = field(
        default_factory=tuple
    )
    warnings: list[str] = field(default_factory=list)
    caveats: list[str] = field(default_factory=lambda: list(DEFAULT_CAVEATS))


def normalize_report(report: ReportInputs | Mapping[str, Any]) -> dict[str, Any]:
    """Convert a report dataclass/mapping into a stable JSON-ready schema."""

    payload = asdict(report) if isinstance(report, ReportInputs) else dict(report)

    caveats = list(payload.get("caveats") or [])
    if SAFETY_STATEMENT not in caveats:
        caveats.insert(0, SAFETY_STATEMENT)
    for caveat in DEFAULT_CAVEATS:
        if caveat not in caveats:
            caveats.append(caveat)

    payload["caveats"] = caveats
    payload["disqualification_flags"] = flags_to_dicts(payload.get("disqualification_flags") or [])
    payload.setdefault("warnings", [])
    payload.setdefault("benchmark_metrics", {})
    payload.setdefault("validation", {})
    payload.setdefault("schema_version", "1.0")
    payload["live_trading_authorized"] = False
    normalized = _json_safe(payload)
    return cast(dict[str, Any], normalized)


def write_json_report(report: ReportInputs | Mapping[str, Any], path: str | Path) -> Path:
    """Write a deterministic JSON report and return its path."""

    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(normalize_report(report), indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return output


def write_markdown_report(report: ReportInputs | Mapping[str, Any], path: str | Path) -> Path:
    """Write a human-readable markdown report and return its path."""

    payload = normalize_report(report)
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render_markdown_report(payload), encoding="utf-8")
    return output


def write_report_bundle(
    report: ReportInputs | Mapping[str, Any],
    output_dir: str | Path,
    *,
    stem: str = "backtest-report",
) -> dict[str, Path]:
    """Write both markdown and JSON reports under a local output directory."""

    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    return {
        "markdown": write_markdown_report(report, directory / f"{stem}.md"),
        "json": write_json_report(report, directory / f"{stem}.json"),
    }


def render_markdown_report(report: ReportInputs | Mapping[str, Any]) -> str:
    """Render markdown report text from a normalized report payload."""

    payload = normalize_report(report)
    lines = [
        "# Backtest Validation Report",
        "",
        "## Summary",
        f"- Strategy: {payload.get('strategy', 'unspecified')}",
        f"- Market: {payload.get('market', 'unspecified')}",
        f"- Symbol: {payload.get('symbol', 'unspecified')}",
        f"- Data period: {payload.get('data_period', 'unspecified')}",
        "- Live trading authorized: no",
        "",
        "## Safety Caveats",
    ]
    lines.extend(f"- {caveat}" for caveat in payload["caveats"])

    lines.extend(["", "## Assumptions"])
    lines.extend(_mapping_lines(payload.get("assumptions") or {}))

    lines.extend(["", "## Metrics"])
    lines.extend(_mapping_lines(payload.get("metrics") or {}))

    if payload.get("benchmark_metrics"):
        lines.extend(["", "## Benchmark Metrics"])
        lines.extend(_mapping_lines(payload["benchmark_metrics"]))

    if payload.get("validation"):
        lines.extend(["", "## Validation"])
        lines.extend(_mapping_lines(payload["validation"]))

    lines.extend(["", "## Disqualification Flags"])
    flags = payload.get("disqualification_flags") or []
    if flags:
        for flag in flags:
            lines.append(
                "- "
                f"[{flag.get('severity', 'fail')}] "
                f"{flag.get('code', 'unknown')}: "
                f"{flag.get('message', '')}"
            )
    else:
        lines.append(
            "- None triggered by configured gates; "
            "this still does not approve live trading."
        )

    if payload.get("warnings"):
        lines.extend(["", "## Warnings"])
        lines.extend(f"- {warning}" for warning in payload["warnings"])

    lines.append("")
    return "\n".join(lines)


def _mapping_lines(mapping: Mapping[str, Any]) -> list[str]:
    if not mapping:
        return ["- Not recorded"]
    return [f"- {key}: {_format_value(value)}" for key, value in sorted(mapping.items())]


def _format_value(value: Any) -> str:
    if isinstance(value, float):
        return f"{value:.6g}"
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(_json_safe(value), sort_keys=True, ensure_ascii=False)
    return str(value)


def _json_safe(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return _json_safe(asdict(cast(Any, value)))
    if isinstance(value, Mapping):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    if isinstance(value, Path):
        return str(value)
    return value
