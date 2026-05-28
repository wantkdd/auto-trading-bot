"""Offline market-data loading and validation."""

from __future__ import annotations

import csv
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path

from auto_trading_bot.domain import Bar, DomainValidationError


class DataValidationError(ValueError):
    """Raised when local market data is malformed or unsafe for backtests."""


_REQUIRED_COLUMNS = ("timestamp", "open", "high", "low", "close", "volume")


def load_csv_bars(path: str | Path) -> tuple[Bar, ...]:
    """Load strict OHLCV bars from a local CSV file.

    Required columns are: timestamp, open, high, low, close, volume.
    Timestamps must be ISO-8601 compatible, strictly increasing, and unique.
    """

    csv_path = Path(path)
    if not csv_path.exists():
        raise DataValidationError(f"CSV file does not exist: {csv_path}")

    try:
        with csv_path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames is None:
                raise DataValidationError("CSV file is missing a header row")
            missing = [column for column in _REQUIRED_COLUMNS if column not in reader.fieldnames]
            if missing:
                raise DataValidationError(f"CSV file is missing required columns: {missing}")
            bars = tuple(
                _parse_bar(row, line_number)
                for line_number, row in enumerate(reader, start=2)
            )
    except csv.Error as exc:
        raise DataValidationError(f"CSV parsing failed: {exc}") from exc

    validate_bars(bars)
    return bars


def validate_bars(bars: Iterable[Bar]) -> tuple[Bar, ...]:
    """Validate that bars are usable by the offline backtest engine."""

    validated = tuple(bars)
    if not validated:
        raise DataValidationError("at least one bar is required")

    previous: datetime | None = None
    seen: set[datetime] = set()
    for bar in validated:
        if bar.timestamp in seen:
            raise DataValidationError(f"duplicate timestamp: {bar.timestamp.isoformat()}")
        if previous is not None and bar.timestamp <= previous:
            raise DataValidationError("bars must be sorted by strictly increasing timestamp")
        seen.add(bar.timestamp)
        previous = bar.timestamp
    return validated


def _parse_bar(row: dict[str, str], line_number: int) -> Bar:
    try:
        timestamp = datetime.fromisoformat(row["timestamp"])
        values = {
            column: float(row[column])
            for column in _REQUIRED_COLUMNS
            if column != "timestamp"
        }
        return Bar(timestamp=timestamp, **values)
    except (KeyError, TypeError, ValueError, DomainValidationError) as exc:
        raise DataValidationError(f"invalid bar at line {line_number}: {exc}") from exc
