"""Broker execution boundary for future API adapters.

This module defines the last local contract before a broker-specific API client.
It is intentionally side-effect free: it creates auditable order tickets and
preflight reports, but it does not import broker SDKs, read credentials, open
network connections, or submit orders.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Protocol, cast

from auto_trading_bot.domain import DomainValidationError


class ExecutionContractError(ValueError):
    """Raised when a future broker-execution request is unsafe or malformed."""


class BrokerOrderSide(StrEnum):
    """Broker-neutral order sides for a future long-only adapter."""

    BUY = "buy"
    SELL = "sell"


class BrokerOrderType(StrEnum):
    """Supported order types for the first API adapter contract."""

    MARKET = "market"


class BrokerTimeInForce(StrEnum):
    """Supported time-in-force values for the first API adapter contract."""

    DAY = "day"


class ExecutionVenue(StrEnum):
    """Future execution venue requested by an explicit approval bundle."""

    PAPER = "paper"
    LIVE = "live"


class ExecutionPreflightStatus(StrEnum):
    """Machine-readable preflight status before any adapter can submit."""

    BLOCKED = "blocked"
    READY_FOR_PAPER_API_ADAPTER = "ready_for_paper_api_adapter"
    READY_FOR_LIVE_API_ADAPTER = "ready_for_live_api_adapter"


@dataclass(frozen=True, slots=True)
class BrokerOrderTicket:
    """Adapter-ready local order ticket, not a submitted broker order."""

    client_order_id: str
    symbol: str
    side: BrokerOrderSide
    quantity: int
    reference_price: float
    created_at: datetime
    source_intent_created_at: datetime
    reason: str = ""
    order_type: BrokerOrderType = BrokerOrderType.MARKET
    time_in_force: BrokerTimeInForce = BrokerTimeInForce.DAY

    def __post_init__(self) -> None:
        normalized = self.symbol.upper().strip()
        object.__setattr__(self, "symbol", normalized)
        if not normalized:
            raise DomainValidationError("symbol is required")
        if self.quantity <= 0:
            raise DomainValidationError("quantity must be positive")
        if self.reference_price <= 0:
            raise DomainValidationError("reference_price must be positive")
        if not self.client_order_id.strip():
            raise DomainValidationError("client_order_id is required for idempotency")
        if self.created_at.tzinfo is None or self.source_intent_created_at.tzinfo is None:
            raise DomainValidationError("ticket timestamps must be timezone-aware")

    @property
    def estimated_notional(self) -> float:
        return self.quantity * self.reference_price

    def to_dict(self) -> dict[str, object]:
        return {
            "client_order_id": self.client_order_id,
            "symbol": self.symbol,
            "side": self.side.value,
            "quantity": self.quantity,
            "reference_price": self.reference_price,
            "estimated_notional": self.estimated_notional,
            "order_type": self.order_type.value,
            "time_in_force": self.time_in_force.value,
            "created_at": self.created_at.isoformat(),
            "source_intent_created_at": self.source_intent_created_at.isoformat(),
            "reason": self.reason,
            "order_created": False,
        }


@dataclass(frozen=True, slots=True)
class ExecutionApproval:
    """Explicit approvals required before a future broker adapter can be used."""

    venue: ExecutionVenue = ExecutionVenue.PAPER
    human_approved: bool = False
    broker_api_connected: bool = False
    account_reconciled: bool = False
    market_data_fresh: bool = False
    kill_switch_armed: bool = False
    legal_tax_review_complete: bool = False
    live_trading_authorized: bool = False
    paper_observation_days: int = 0

    def __post_init__(self) -> None:
        if self.paper_observation_days < 0:
            raise DomainValidationError("paper_observation_days must be nonnegative")
        if self.venue is ExecutionVenue.LIVE and not self.live_trading_authorized:
            # The object may still be constructed for a blocked report; the blocker is
            # emitted by evaluate_execution_preflight.
            return

    def to_dict(self) -> dict[str, object]:
        return {
            "venue": self.venue.value,
            "human_approved": self.human_approved,
            "broker_api_connected": self.broker_api_connected,
            "account_reconciled": self.account_reconciled,
            "market_data_fresh": self.market_data_fresh,
            "kill_switch_armed": self.kill_switch_armed,
            "legal_tax_review_complete": self.legal_tax_review_complete,
            "live_trading_authorized": self.live_trading_authorized,
            "paper_observation_days": self.paper_observation_days,
        }


@dataclass(frozen=True, slots=True)
class ExecutionPreflightPolicy:
    """Conservative order-routing gates shared by paper/live adapters."""

    max_order_notional: float = 1_000.0
    max_total_notional: float = 2_000.0
    min_paper_observation_days: int = 22
    allowed_symbols: frozenset[str] = field(default_factory=frozenset)
    blocked_symbols: frozenset[str] = field(default_factory=frozenset)

    def __post_init__(self) -> None:
        if self.max_order_notional <= 0 or self.max_total_notional <= 0:
            raise DomainValidationError("notional limits must be positive")
        if self.min_paper_observation_days < 0:
            raise DomainValidationError("min_paper_observation_days must be nonnegative")
        overlap = self.allowed_symbols & self.blocked_symbols
        if overlap:
            raise DomainValidationError(f"symbols cannot be both allowed and blocked: {overlap}")

    def to_dict(self) -> dict[str, object]:
        return {
            "max_order_notional": self.max_order_notional,
            "max_total_notional": self.max_total_notional,
            "min_paper_observation_days": self.min_paper_observation_days,
            "allowed_symbols": sorted(self.allowed_symbols),
            "blocked_symbols": sorted(self.blocked_symbols),
        }


@dataclass(frozen=True, slots=True)
class ExecutionPreflightReport:
    """Decision record immediately before a future broker adapter boundary."""

    status: ExecutionPreflightStatus
    tickets: tuple[BrokerOrderTicket, ...]
    blockers: tuple[str, ...]
    warnings: tuple[str, ...]
    approval: ExecutionApproval
    policy: ExecutionPreflightPolicy
    generated_at: datetime
    order_created: bool = False
    submit_attempted: bool = False

    def __post_init__(self) -> None:
        if self.order_created or self.submit_attempted:
            raise DomainValidationError("preflight reports cannot create or submit orders")
        if self.status is not ExecutionPreflightStatus.BLOCKED and self.blockers:
            raise DomainValidationError("ready preflight report cannot contain blockers")

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.status.value,
            "generated_at": self.generated_at.isoformat(),
            "safety": (
                "broker execution preflight only; no SDK; no credentials; "
                "no network; no submitted orders"
            ),
            "order_created": self.order_created,
            "submit_attempted": self.submit_attempted,
            "ticket_count": len(self.tickets),
            "total_estimated_notional": sum(ticket.estimated_notional for ticket in self.tickets),
            "tickets": [ticket.to_dict() for ticket in self.tickets],
            "blockers": list(self.blockers),
            "warnings": list(self.warnings),
            "approval": self.approval.to_dict(),
            "policy": self.policy.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class BrokerSubmissionResult:
    """Return type for future broker adapters; current null adapter always blocks."""

    client_order_id: str
    status: str
    order_created: bool = False
    broker_order_id: str | None = None

    def __post_init__(self) -> None:
        if self.order_created and not self.broker_order_id:
            raise DomainValidationError("created orders must include broker_order_id")


class BrokerExecutionAdapter(Protocol):
    """Protocol a future Alpaca/IBKR/etc. adapter must implement."""

    def route_ticket(self, ticket: BrokerOrderTicket) -> BrokerSubmissionResult:
        """Submit a single preflighted ticket to a broker API."""


@dataclass(frozen=True, slots=True)
class NullBrokerExecutionAdapter:
    """Safe placeholder adapter used until a real broker API is explicitly approved."""

    reason: str = "broker_api_adapter_not_configured"

    def route_ticket(self, ticket: BrokerOrderTicket) -> BrokerSubmissionResult:
        return BrokerSubmissionResult(
            client_order_id=ticket.client_order_id,
            status=self.reason,
            order_created=False,
        )


def build_tickets_from_no_order_plan(
    plan: Mapping[str, object], *, created_at: datetime | None = None
) -> tuple[BrokerOrderTicket, ...]:
    """Convert accepted no-order preview rows into adapter-shaped tickets."""

    accepted = plan.get("accepted", [])
    if not isinstance(accepted, list):
        raise ExecutionContractError("no-order plan accepted field must be a list")
    ticket_created_at = created_at or datetime.now(tz=UTC)
    tickets: list[BrokerOrderTicket] = []
    for row in accepted:
        if not isinstance(row, Mapping):
            raise ExecutionContractError("accepted no-order intent must be a mapping")
        tickets.append(ticket_from_intent_row(row, created_at=ticket_created_at))
    return tuple(tickets)


def ticket_from_intent_row(
    row: Mapping[str, object], *, created_at: datetime
) -> BrokerOrderTicket:
    side = side_from_no_order_side(str(row.get("side", "")))
    symbol = str(row.get("symbol", "")).upper().strip()
    raw_quantity = cast(str | int | float, row.get("quantity", 0) or 0)
    raw_reference_price = cast(str | int | float, row.get("reference_price", 0.0) or 0.0)
    quantity = int(raw_quantity)
    reference_price = float(raw_reference_price)
    source_created_at = parse_dt(str(row.get("created_at", "")))
    client_order_id = deterministic_client_order_id(
        symbol=symbol,
        side=side,
        quantity=quantity,
        reference_price=reference_price,
        source_created_at=source_created_at,
    )
    return BrokerOrderTicket(
        client_order_id=client_order_id,
        symbol=symbol,
        side=side,
        quantity=quantity,
        reference_price=reference_price,
        created_at=created_at,
        source_intent_created_at=source_created_at,
        reason=str(row.get("reason", "")),
    )


def side_from_no_order_side(value: str) -> BrokerOrderSide:
    if value == "would_buy":
        return BrokerOrderSide.BUY
    if value == "would_sell":
        return BrokerOrderSide.SELL
    raise ExecutionContractError(f"unsupported no-order side for broker ticket: {value}")


def deterministic_client_order_id(
    *,
    symbol: str,
    side: BrokerOrderSide,
    quantity: int,
    reference_price: float,
    source_created_at: datetime,
) -> str:
    raw = f"{symbol}|{side.value}|{quantity}|{reference_price:.8f}|{source_created_at.isoformat()}"
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]
    return f"atb-{digest}"


def parse_dt(value: str) -> datetime:
    if not value:
        return datetime.now(tz=UTC)
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


def evaluate_execution_preflight(
    tickets: Sequence[BrokerOrderTicket],
    *,
    approval: ExecutionApproval,
    policy: ExecutionPreflightPolicy | None = None,
    generated_at: datetime | None = None,
) -> ExecutionPreflightReport:
    """Return the adapter-readiness decision without submitting orders."""

    active_policy = policy or ExecutionPreflightPolicy()
    blockers = ticket_blockers(tickets, active_policy)
    blockers.extend(approval_blockers(approval, active_policy))
    status = ExecutionPreflightStatus.BLOCKED
    if not blockers:
        status = (
            ExecutionPreflightStatus.READY_FOR_LIVE_API_ADAPTER
            if approval.venue is ExecutionVenue.LIVE
            else ExecutionPreflightStatus.READY_FOR_PAPER_API_ADAPTER
        )
    warnings = (
        "preflight only; a separate broker-specific adapter must implement route_ticket",
        "do not route live capital until legal/tax/account reviews are complete",
    )
    return ExecutionPreflightReport(
        status=status,
        tickets=tuple(tickets),
        blockers=tuple(sorted(set(blockers))),
        warnings=warnings,
        approval=approval,
        policy=active_policy,
        generated_at=generated_at or datetime.now(tz=UTC),
    )


def ticket_blockers(
    tickets: Sequence[BrokerOrderTicket], policy: ExecutionPreflightPolicy
) -> list[str]:
    blockers: list[str] = []
    if not tickets:
        blockers.append("no_broker_order_tickets")
    total = 0.0
    for ticket in tickets:
        total += ticket.estimated_notional
        if policy.allowed_symbols and ticket.symbol not in policy.allowed_symbols:
            blockers.append("symbol_not_allowed")
        if ticket.symbol in policy.blocked_symbols:
            blockers.append("symbol_blocked")
        if ticket.estimated_notional > policy.max_order_notional:
            blockers.append("order_notional_limit_exceeded")
    if total > policy.max_total_notional:
        blockers.append("total_notional_limit_exceeded")
    return blockers


def approval_blockers(
    approval: ExecutionApproval, policy: ExecutionPreflightPolicy
) -> list[str]:
    blockers: list[str] = []
    if not approval.human_approved:
        blockers.append("human_approval_missing")
    if not approval.broker_api_connected:
        blockers.append("broker_api_adapter_not_connected")
    if not approval.account_reconciled:
        blockers.append("account_position_reconciliation_missing")
    if not approval.market_data_fresh:
        blockers.append("market_data_freshness_missing")
    if not approval.kill_switch_armed:
        blockers.append("kill_switch_not_armed")
    if approval.paper_observation_days < policy.min_paper_observation_days:
        blockers.append("minimum_paper_observation_days_missing")
    if approval.venue is ExecutionVenue.LIVE:
        if not approval.live_trading_authorized:
            blockers.append("live_trading_authorization_missing")
        if not approval.legal_tax_review_complete:
            blockers.append("legal_tax_review_missing_for_live")
    return blockers
