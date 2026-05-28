"""Shared test helpers for deterministic local-only backtest tests."""

from __future__ import annotations

from datetime import datetime, timedelta

from auto_trading_bot.domain import Bar


def make_bars(closes: list[float], *, opens: list[float] | None = None) -> tuple[Bar, ...]:

    if opens is None:
        opens = closes
    if len(opens) != len(closes):
        raise ValueError("opens and closes must have the same length")

    start = datetime(2024, 1, 2, 9, 0)
    bars: list[Bar] = []
    for index, (open_price, close_price) in enumerate(zip(opens, closes, strict=True)):
        high = max(open_price, close_price) + 1.0
        low = min(open_price, close_price) - 1.0
        bars.append(
            Bar(
                timestamp=start + timedelta(days=index),
                open=float(open_price),
                high=float(high),
                low=float(low),
                close=float(close_price),
                volume=1_000 + index,
            )
        )
    return tuple(bars)
