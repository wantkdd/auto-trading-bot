"""Validation helpers for offline backtest evaluation.

This module is intentionally pure/local: it performs deterministic data-window
splits and report disqualification checks without broker, network, or credential
integration.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any


class ValidationError(ValueError):
    """Raised when a validation request cannot produce a safe evaluation."""


@dataclass(frozen=True)
class ValidationWindow:
    """A non-overlapping train/test slice expressed as half-open indices."""

    train_start: int
    train_end: int
    test_start: int
    test_end: int
    label: str = ""

    def __post_init__(self) -> None:
        if self.train_start < 0 or self.test_start < 0:
            raise ValidationError("window indices must be non-negative")
        if self.train_start >= self.train_end:
            raise ValidationError("train window must contain at least one row")
        if self.test_start >= self.test_end:
            raise ValidationError("test window must contain at least one row")
        if self.train_end > self.test_start:
            raise ValidationError("train and test windows must not overlap")

    @property
    def train_slice(self) -> slice:
        return slice(self.train_start, self.train_end)

    @property
    def test_slice(self) -> slice:
        return slice(self.test_start, self.test_end)

    def to_dict(self) -> dict[str, int | str]:
        return {
            "label": self.label,
            "train_start": self.train_start,
            "train_end": self.train_end,
            "test_start": self.test_start,
            "test_end": self.test_end,
        }


@dataclass(frozen=True)
class DisqualificationRules:
    """Conservative report gates used before any future capital decision."""

    max_drawdown_limit: float = -0.20
    min_trades: int = 5
    require_positive_total_return: bool = True
    require_benchmark_outperformance: bool = True


@dataclass(frozen=True)
class DisqualificationFlag:
    """A machine-readable reason that a run should not be promoted."""

    code: str
    message: str
    severity: str = "fail"

    def to_dict(self) -> dict[str, str]:
        return {"code": self.code, "message": self.message, "severity": self.severity}


def _length(data: Sequence[Any] | Iterable[Any]) -> int:
    try:
        return len(data)  # type: ignore[arg-type]
    except TypeError:
        return len(list(data))


def train_test_split_window(
    data: Sequence[Any] | Iterable[Any],
    train_fraction: float = 0.7,
    *,
    min_train_size: int = 1,
    min_test_size: int = 1,
    label: str = "holdout",
) -> ValidationWindow:
    """Return one chronological train/test split without overlap.

    The split preserves input order and never shuffles financial time series.
    """

    n = _length(data)
    if not 0 < train_fraction < 1:
        raise ValidationError("train_fraction must be between 0 and 1")
    if min_train_size < 1 or min_test_size < 1:
        raise ValidationError("minimum split sizes must be positive")
    if n < min_train_size + min_test_size:
        raise ValidationError("not enough rows for requested train/test split")

    train_end = int(n * train_fraction)
    train_end = max(min_train_size, min(train_end, n - min_test_size))
    return ValidationWindow(0, train_end, train_end, n, label=label)


def split_train_test(
    data: Sequence[Any],
    train_fraction: float = 0.7,
    *,
    min_train_size: int = 1,
    min_test_size: int = 1,
) -> tuple[Sequence[Any], Sequence[Any], ValidationWindow]:
    """Return chronological train rows, test rows, and the split metadata."""

    window = train_test_split_window(
        data,
        train_fraction,
        min_train_size=min_train_size,
        min_test_size=min_test_size,
    )
    return data[window.train_slice], data[window.test_slice], window


def walk_forward_windows(
    data: Sequence[Any] | Iterable[Any],
    *,
    train_size: int,
    test_size: int,
    step_size: int | None = None,
) -> list[ValidationWindow]:
    """Build ordered walk-forward train/test windows.

    Windows are half-open index ranges and each test slice begins at or after the
    corresponding train slice ends, preventing leakage from future rows.
    """

    n = _length(data)
    if train_size < 1 or test_size < 1:
        raise ValidationError("train_size and test_size must be positive")
    step = test_size if step_size is None else step_size
    if step < 1:
        raise ValidationError("step_size must be positive")
    if n < train_size + test_size:
        raise ValidationError("not enough rows for one walk-forward window")

    windows: list[ValidationWindow] = []
    start = 0
    index = 1
    while start + train_size + test_size <= n:
        train_end = start + train_size
        test_end = train_end + test_size
        windows.append(
            ValidationWindow(
                start,
                train_end,
                train_end,
                test_end,
                label=f"walk_forward_{index}",
            )
        )
        start += step
        index += 1
    return windows


def evaluate_disqualification(
    metrics: Mapping[str, Any],
    *,
    benchmark_metrics: Mapping[str, Any] | None = None,
    rules: DisqualificationRules | None = None,
) -> list[DisqualificationFlag]:
    """Return conservative fail/warn flags for a completed backtest."""

    active_rules = rules or DisqualificationRules()
    flags: list[DisqualificationFlag] = []

    max_drawdown = _as_float(metrics.get("max_drawdown"))
    if max_drawdown is not None and max_drawdown < active_rules.max_drawdown_limit:
        flags.append(
            DisqualificationFlag(
                "max_drawdown_exceeded",
                "Max drawdown "
                f"{max_drawdown:.2%} is worse than limit "
                f"{active_rules.max_drawdown_limit:.2%}.",
            )
        )

    trade_count = _as_int(metrics.get("trade_count"))
    if trade_count is not None and trade_count < active_rules.min_trades:
        flags.append(
            DisqualificationFlag(
                "insufficient_trades",
                f"Trade count {trade_count} is below minimum "
                f"{active_rules.min_trades}; result may be statistically weak.",
                severity="warn",
            )
        )

    total_return = _as_float(metrics.get("total_return"))
    if (
        active_rules.require_positive_total_return
        and total_return is not None
        and total_return <= 0
    ):
        flags.append(
            DisqualificationFlag(
                "non_positive_total_return",
                f"Total return {total_return:.2%} is not positive after costs.",
            )
        )

    if active_rules.require_benchmark_outperformance and benchmark_metrics:
        benchmark_return = _as_float(benchmark_metrics.get("total_return"))
        if (
            total_return is not None
            and benchmark_return is not None
            and total_return <= benchmark_return
        ):
            flags.append(
                DisqualificationFlag(
                    "underperformed_benchmark",
                    "Strategy return "
                    f"{total_return:.2%} did not beat benchmark "
                    f"{benchmark_return:.2%} after costs.",
                )
            )

    if not metrics.get("costs_included", True):
        flags.append(
            DisqualificationFlag(
                "missing_costs",
                "Commission/slippage costs were not included in the result.",
            )
        )

    return flags


def flags_to_dicts(
    flags: Iterable[DisqualificationFlag | Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Normalize flag dataclasses or mappings for JSON reports."""

    normalized: list[dict[str, Any]] = []
    for flag in flags:
        if isinstance(flag, DisqualificationFlag):
            normalized.append(flag.to_dict())
        else:
            normalized.append(dict(flag))
    return normalized


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
