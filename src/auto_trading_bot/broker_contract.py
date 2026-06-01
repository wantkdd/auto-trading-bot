"""Broker-neutral no-order adapter contract.

This module deliberately does not connect to any broker, network endpoint, or
credential source. It converts validated strategy intent into a local plan that
can be audited before any future paper API adapter is considered.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Protocol, cast

from auto_trading_bot.domain import DomainValidationError


class BrokerContractError(ValueError):
    """Raised when a no-order adapter request violates safety constraints."""


class OrderIntentSide(StrEnum):
    """Paper-order intent side names; these are not broker instructions."""

    WOULD_BUY = "would_buy"
    WOULD_SELL = "would_sell"


class OrderIntentStatus(StrEnum):
    """Execution status for the current no-order contract."""

    SIMULATED_ONLY = "simulated_only"
    REJECTED = "rejected"


@dataclass(frozen=True, slots=True)
class NoOrderSafetyPolicy:
    """Hard risk limits for a no-order broker adapter plan."""

    max_order_notional: float = 1_000.0
    max_total_notional: float = 2_000.0
    allowed_symbols: frozenset[str] = field(default_factory=frozenset)
    blocked_symbols: frozenset[str] = field(default_factory=frozenset)
    live_trading_authorized: bool = False
    paper_api_authorized: bool = False

    def __post_init__(self) -> None:
        if self.max_order_notional <= 0 or self.max_total_notional <= 0:
            raise DomainValidationError("notional limits must be positive")
        if self.live_trading_authorized or self.paper_api_authorized:
            raise DomainValidationError("broker API authorization is outside this contract")
        overlap = self.allowed_symbols & self.blocked_symbols
        if overlap:
            raise DomainValidationError(f"symbols cannot be both allowed and blocked: {overlap}")


@dataclass(frozen=True, slots=True)
class PaperOrderIntent:
    """Auditable paper intent that must never be routed to a broker."""

    symbol: str
    side: OrderIntentSide
    quantity: int
    reference_price: float
    created_at: datetime
    reason: str = ""

    def __post_init__(self) -> None:
        normalized = self.symbol.upper().strip()
        object.__setattr__(self, "symbol", normalized)
        if not normalized:
            raise DomainValidationError("symbol is required")
        if self.quantity <= 0:
            raise DomainValidationError("quantity must be positive")
        if self.reference_price <= 0:
            raise DomainValidationError("reference_price must be positive")

    @property
    def notional(self) -> float:
        return self.quantity * self.reference_price


@dataclass(frozen=True, slots=True)
class NoOrderPlan:
    """Result of evaluating paper intents under the no-order safety contract."""

    created_at: datetime
    accepted: tuple[PaperOrderIntent, ...]
    rejected: tuple[PaperOrderIntent, ...]
    rejection_reasons: Mapping[str, tuple[str, ...]]
    total_notional: float
    order_created: bool = False
    live_trading_authorized: bool = False
    paper_api_authorized: bool = False
    status: OrderIntentStatus = OrderIntentStatus.SIMULATED_ONLY

    def __post_init__(self) -> None:
        if self.order_created or self.live_trading_authorized or self.paper_api_authorized:
            raise DomainValidationError("no-order plans cannot authorize or create orders")
        if self.total_notional < 0:
            raise DomainValidationError("total_notional must be nonnegative")

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-safe audit payload."""

        return {
            "created_at": self.created_at.isoformat(),
            "status": self.status.value,
            "order_created": self.order_created,
            "live_trading_authorized": self.live_trading_authorized,
            "paper_api_authorized": self.paper_api_authorized,
            "total_notional": self.total_notional,
            "accepted": [intent_to_dict(intent) for intent in self.accepted],
            "rejected": [intent_to_dict(intent) for intent in self.rejected],
            "rejection_reasons": {
                symbol: list(reasons) for symbol, reasons in self.rejection_reasons.items()
            },
            "safety": "no-order broker contract only; no broker, no credentials, no API calls",
        }


class NoOrderBrokerAdapter(Protocol):
    """Protocol for future fixture/mock adapters that must remain no-order."""

    def preview(self, intents: Sequence[PaperOrderIntent]) -> NoOrderPlan:
        """Validate intents and return a no-order plan without side effects."""


@dataclass(frozen=True, slots=True)
class FixtureNoOrderBrokerAdapter:
    """Deterministic local adapter that validates but never submits intents."""

    policy: NoOrderSafetyPolicy = field(default_factory=NoOrderSafetyPolicy)

    def preview(self, intents: Sequence[PaperOrderIntent]) -> NoOrderPlan:
        accepted: list[PaperOrderIntent] = []
        rejected: list[PaperOrderIntent] = []
        reasons: dict[str, tuple[str, ...]] = {}
        running_total = 0.0

        for intent in intents:
            intent_reasons = tuple(self._rejection_reasons(intent, running_total))
            if intent_reasons:
                rejected.append(intent)
                reasons[intent.symbol] = intent_reasons
                continue
            accepted.append(intent)
            running_total += intent.notional

        return NoOrderPlan(
            created_at=max((intent.created_at for intent in intents), default=datetime.now(tz=UTC)),
            accepted=tuple(accepted),
            rejected=tuple(rejected),
            rejection_reasons=reasons,
            total_notional=running_total,
        )

    def _rejection_reasons(self, intent: PaperOrderIntent, running_total: float) -> list[str]:
        reasons: list[str] = []
        if self.policy.allowed_symbols and intent.symbol not in self.policy.allowed_symbols:
            reasons.append("symbol_not_allowed")
        if intent.symbol in self.policy.blocked_symbols:
            reasons.append("symbol_blocked")
        if intent.notional > self.policy.max_order_notional:
            reasons.append("order_notional_limit_exceeded")
        if running_total + intent.notional > self.policy.max_total_notional:
            reasons.append("total_notional_limit_exceeded")
        return reasons


def build_intents_from_trade_rows(
    rows: Sequence[Mapping[str, object]], *, created_at: datetime
) -> tuple[PaperOrderIntent, ...]:
    """Convert paper trade-intent JSON rows into validated no-order intents."""

    intents: list[PaperOrderIntent] = []
    for row in rows:
        _validate_no_order_source_row(row)
        side = str(row.get("side", ""))
        if side not in {OrderIntentSide.WOULD_BUY.value, OrderIntentSide.WOULD_SELL.value}:
            raise BrokerContractError(f"unsupported paper side: {side}")
        raw_quantity = cast(str | int | float, row.get("quantity", 0))
        raw_reference_price = cast(str | int | float, row.get("reference_price", 0.0))
        intents.append(
            PaperOrderIntent(
                symbol=str(row.get("symbol", "")),
                side=OrderIntentSide(side),
                quantity=int(raw_quantity),
                reference_price=float(raw_reference_price),
                created_at=created_at,
                reason=str(row.get("reason", "")),
            )
        )
    return tuple(intents)


def _validate_no_order_source_row(row: Mapping[str, object]) -> None:
    """Reject tainted source rows before building local no-order intents."""

    if row.get("order_created") not in (None, False):
        raise BrokerContractError("paper intent row must keep order_created=false")
    if row.get("live_trading_authorized") is True or row.get("paper_api_authorized") is True:
        raise BrokerContractError("paper intent row cannot authorize broker API trading")
    for metadata_field in (
        "broker_order_id",
        "broker_execution_id",
        "order_id",
        "execution_id",
    ):
        if row.get(metadata_field):
            raise BrokerContractError(f"paper intent row cannot include {metadata_field}")


def intent_to_dict(intent: PaperOrderIntent) -> dict[str, object]:
    return {
        "symbol": intent.symbol,
        "side": intent.side.value,
        "quantity": intent.quantity,
        "reference_price": intent.reference_price,
        "notional": intent.notional,
        "created_at": intent.created_at.isoformat(),
        "order_created": False,
        "reason": intent.reason,
    }
