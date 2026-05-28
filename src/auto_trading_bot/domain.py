"""Core immutable domain models for the offline trading-research MVP.

The MVP models local backtests only. It intentionally contains no broker adapter,
credential access, network code, or remote execution path.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Mapping


class DomainValidationError(ValueError):
    """Raised when domain data violates an invariant."""


class SignalAction(str, Enum):
    """Long-only strategy intent generated after a bar is complete."""

    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"


class TradeSide(str, Enum):
    """Executed local-simulation trade side."""

    BUY = "buy"
    SELL = "sell"


@dataclass(frozen=True, slots=True)
class Bar:
    """Single OHLCV bar from a local/offline data source."""

    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float

    def __post_init__(self) -> None:
        if self.open <= 0 or self.high <= 0 or self.low <= 0 or self.close <= 0:
            raise DomainValidationError("OHLC prices must be positive")
        if self.volume < 0:
            raise DomainValidationError("volume must be nonnegative")
        if self.low > min(self.open, self.close, self.high):
            raise DomainValidationError("low must not exceed open/high/close")
        if self.high < max(self.open, self.close, self.low):
            raise DomainValidationError("high must not be below open/low/close")


@dataclass(frozen=True, slots=True)
class StrategySignal:
    """Signal emitted after observing a completed bar.

    Backtests must apply this signal no earlier than the next available bar open.
    """

    timestamp: datetime
    action: SignalAction
    reason: str = ""
    strength: float = 0.0


@dataclass(frozen=True, slots=True)
class LocalOrder:
    """Local-simulator order intent, never a remote instruction."""

    timestamp: datetime
    side: TradeSide
    quantity: int
    reference_price: float
    source_signal_at: datetime

    def __post_init__(self) -> None:
        if self.quantity <= 0:
            raise DomainValidationError("quantity must be positive")
        if self.reference_price <= 0:
            raise DomainValidationError("reference_price must be positive")


@dataclass(frozen=True, slots=True)
class Trade:
    """Executed local-simulation fill."""

    timestamp: datetime
    side: TradeSide
    quantity: int
    price: float
    commission: float
    slippage: float
    cash_after: float
    position_after: int
    source_signal_at: datetime

    def __post_init__(self) -> None:
        if self.quantity <= 0:
            raise DomainValidationError("quantity must be positive")
        if self.price <= 0:
            raise DomainValidationError("price must be positive")
        if self.commission < 0 or self.slippage < 0:
            raise DomainValidationError("costs must be nonnegative")
        if self.position_after < 0:
            raise DomainValidationError("short positions are not allowed in the MVP")

    @property
    def notional(self) -> float:
        return self.quantity * self.price


@dataclass(frozen=True, slots=True)
class EquityPoint:
    """Portfolio state marked at a bar close."""

    timestamp: datetime
    cash: float
    position: int
    close_price: float
    equity: float

    def __post_init__(self) -> None:
        if self.cash < -1e-9:
            raise DomainValidationError("cash must not be negative after local accounting")
        if self.position < 0:
            raise DomainValidationError("short positions are not allowed in the MVP")
        if self.close_price <= 0 or self.equity < 0:
            raise DomainValidationError("close_price and equity must be valid nonnegative values")


@dataclass(frozen=True, slots=True)
class BacktestConfig:
    """Configurable local backtest assumptions."""

    initial_cash: float = 10_000.0
    commission_rate: float = 0.001
    slippage_bps: float = 5.0
    min_trade_quantity: int = 1

    def __post_init__(self) -> None:
        if self.initial_cash <= 0:
            raise DomainValidationError("initial_cash must be positive")
        if self.commission_rate < 0:
            raise DomainValidationError("commission_rate must be nonnegative")
        if self.slippage_bps < 0:
            raise DomainValidationError("slippage_bps must be nonnegative")
        if self.min_trade_quantity <= 0:
            raise DomainValidationError("min_trade_quantity must be positive")


@dataclass(frozen=True, slots=True)
class BacktestResult:
    """Full deterministic local backtest output."""

    strategy_name: str
    config: BacktestConfig
    bars: tuple[Bar, ...]
    signals: tuple[StrategySignal, ...]
    trades: tuple[Trade, ...]
    equity_curve: tuple[EquityPoint, ...]
    metrics: Mapping[str, float | int | None]
    benchmark_metrics: Mapping[str, float | int | None]
    warnings: tuple[str, ...] = field(default_factory=tuple)

    @property
    def final_equity(self) -> float:
        if not self.equity_curve:
            return self.config.initial_cash
        return self.equity_curve[-1].equity
