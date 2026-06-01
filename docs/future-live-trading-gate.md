# Future Live-Trading Approval Gate

This document defines the boundary for future paper or live trading proposals. It is not approval to build or operate live trading.

## Current MVP boundary

This MVP cannot place orders and is not approval for live trading. The current system is limited to:

- Loading user-provided OHLCV CSV files from local disk.
- Running deterministic local simulator backtests.
- Writing local Markdown and JSON reports.
- Preserving report caveats, including `live_trading_authorized=false`.

The current MVP must not include broker SDKs, exchange clients, network market-data clients, credential handling, account reads, paper/live adapters, or live-order paths.

## Activation schedule

The current calendar for moving from no-order observation to broker sandbox and a possible tightly capped live pilot is tracked in [`docs/live-pilot-activation-schedule.md`](live-pilot-activation-schedule.md). That schedule sets the operator-requested live-pilot review target at 2026-06-16 KST and keeps live trading blocked unless all approval, sandbox, reconciliation, kill-switch, tax/cost/liquidity, and legal/adviser-status gates pass.

## Current readiness automation

The repository may generate a local readiness-blocker report with:

```bash
uv run python scripts/live_readiness_gate.py
```

That report can mark a candidate as `paper_dry_run_candidate` when offline gates
and dry-run target logging line up, but it must keep `live_trading_authorized=false`.
It is a blocker checklist for future human/legal review, not permission to connect
a broker or place trades. Current mandatory live blockers include independent
data-source replication, the 2026-06-16 two-week paper-observation target window, drift
monitoring, tax/cost/liquidity review, human approval, and legal/adviser-status
review for automated investment advice.

## Required approval before expansion

Before any future paper or live trading work begins, maintainers must approve a separate design that covers:

1. Legal, compliance, and operator-risk review.
2. Credential and secret-management architecture.
3. Broker/API dependency selection, maintenance, and license review.
4. Network, retry, idempotency, rate-limit, and outage behavior.
5. Account permission boundaries and audit logging.
6. Order lifecycle modeling, reconciliation, and kill-switch behavior.
7. Independent sandbox/paper validation that is explicitly separate from live trading.
8. User-facing warnings that reports are not investment advice and do not guarantee profit.

Approval of this gate must happen before code is added. Documentation alone does not authorize live trading.

## Rejected for this MVP

The following remain out of scope for this MVP:

- Broker, exchange, or paper-trading integrations.
- Remote market-data downloads.
- Credential files, credential environment reads, or account identifiers.
- Any function or CLI path that places, submits, routes, modifies, or cancels real orders.
- Profit claims, trading recommendations, or production-readiness claims.

## Maintainer checklist for future proposals

A future proposal is not ready until it can answer all of these questions in writing:

- What new external systems are introduced, and why are they necessary?
- How are credentials protected and audited?
- How is live order placement prevented by default?
- What tests prove paper/sandbox behavior cannot accidentally target live accounts?
- What user confirmation and kill-switch controls exist?
- What incident response and rollback plan exists?

If any answer is missing, the proposal stays outside the repository's implementation scope.
