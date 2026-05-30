# API operational risk gate

This repository does not trade live. If a future human-approved proposal ever adds a broker sandbox, it must first close these operational risks in writing and in tests.

## Latency and stale data

- Define max acceptable market-data age before a signal is considered stale.
- Define max broker API round-trip latency before order placement is halted.
- Use exchange calendars and market-hours checks; never infer tradability from a cached quote alone.
- Halt on delayed quote feeds, missing bid/ask, crossed markets, zero volume, or large spread spikes.

## Execution risk

- Model bid/ask spread, slippage, commissions, and market impact before comparing to backtests.
- Treat market orders as unsafe by default; require explicit limit/order-type policy.
- Handle partial fills, rejects, cancels, cancel/replace races, and order status timeouts.
- Use idempotency keys or client order IDs so retries cannot duplicate orders.

## Broker/API reliability

- Respect rate limits with bounded backoff and circuit breakers.
- Halt on authentication failure, account permission mismatch, outage, or inconsistent API responses.
- Reconcile broker account cash, positions, open orders, and local state before and after every intended action.
- Persist every request/response/audit event; never rely on memory-only state.

## Portfolio and market events

- Block leverage, shorting, margin, options, and inverse/leveraged products unless a separate approved gate exists.
- Handle dividends, splits, corporate actions, symbol changes, halted securities, and holidays.
- Enforce max allocation, max daily loss, max drawdown, stale-data halt, and manual kill switch.

## Approval boundary

Passing backtests or paper observation does not close this gate. A future implementation must prove these behaviors in broker sandbox tests before any real capital is considered.
