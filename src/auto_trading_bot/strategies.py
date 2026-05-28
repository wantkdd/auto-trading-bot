"""Explainable baseline strategies for local validation."""

from __future__ import annotations

from abc import ABC, abstractmethod
from statistics import fmean

from auto_trading_bot.domain import Bar, SignalAction, StrategySignal


class Strategy(ABC):
    """Strategy interface that emits signals after completed bars."""

    name: str

    @abstractmethod
    def generate_signals(self, bars: tuple[Bar, ...]) -> tuple[StrategySignal, ...]:
        """Generate one signal per bar using only information through that bar."""


class MovingAverageCrossoverStrategy(Strategy):
    """Long-only moving-average crossover baseline."""

    def __init__(self, short_window: int = 5, long_window: int = 20) -> None:
        if short_window <= 0 or long_window <= 0:
            raise ValueError("moving-average windows must be positive")
        if short_window >= long_window:
            raise ValueError("short_window must be less than long_window")
        self.short_window = short_window
        self.long_window = long_window
        self.name = f"moving_average_crossover_{short_window}_{long_window}"

    def generate_signals(self, bars: tuple[Bar, ...]) -> tuple[StrategySignal, ...]:
        signals: list[StrategySignal] = []
        closes = [bar.close for bar in bars]
        previous_relation: int | None = None

        for index, bar in enumerate(bars):
            if index + 1 < self.long_window:
                signals.append(StrategySignal(bar.timestamp, SignalAction.HOLD, "warming up"))
                continue

            short_average = fmean(closes[index + 1 - self.short_window : index + 1])
            long_average = fmean(closes[index + 1 - self.long_window : index + 1])
            if short_average > long_average:
                relation = 1
            elif short_average < long_average:
                relation = -1
            else:
                relation = 0

            if previous_relation is None:
                action = SignalAction.BUY if relation > 0 else SignalAction.HOLD
                reason = (
                    "initial short average above long average"
                    if relation > 0
                    else "no bullish crossover"
                )
            elif previous_relation <= 0 < relation:
                action = SignalAction.BUY
                reason = "short average crossed above long average"
            elif previous_relation >= 0 > relation:
                action = SignalAction.SELL
                reason = "short average crossed below long average"
            else:
                action = SignalAction.HOLD
                reason = "no crossover"

            previous_relation = relation
            signals.append(
                StrategySignal(
                    timestamp=bar.timestamp,
                    action=action,
                    reason=reason,
                    strength=short_average - long_average,
                )
            )
        return tuple(signals)


class MomentumStrategy(Strategy):
    """Long-only momentum baseline based on close-to-close lookback return."""

    def __init__(self, lookback: int = 10, threshold: float = 0.0) -> None:
        if lookback <= 0:
            raise ValueError("lookback must be positive")
        if threshold < 0:
            raise ValueError("threshold must be nonnegative")
        self.lookback = lookback
        self.threshold = threshold
        self.name = f"momentum_{lookback}_{threshold:g}"

    def generate_signals(self, bars: tuple[Bar, ...]) -> tuple[StrategySignal, ...]:
        signals: list[StrategySignal] = []
        for index, bar in enumerate(bars):
            if index < self.lookback:
                signals.append(StrategySignal(bar.timestamp, SignalAction.HOLD, "warming up"))
                continue

            past_close = bars[index - self.lookback].close
            momentum = (bar.close / past_close) - 1.0
            if momentum > self.threshold:
                action = SignalAction.BUY
                reason = "positive momentum above threshold"
            elif momentum < -self.threshold:
                action = SignalAction.SELL
                reason = "negative momentum below threshold"
            else:
                action = SignalAction.HOLD
                reason = "momentum inside threshold"
            signals.append(
                StrategySignal(
                    timestamp=bar.timestamp,
                    action=action,
                    reason=reason,
                    strength=momentum,
                )
            )
        return tuple(signals)
