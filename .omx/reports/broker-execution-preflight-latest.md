# Broker execution preflight

Safety: broker-neutral preflight only; no SDK, no credentials, no network, no orders.

## Summary

- Status: `blocked`
- Tickets: `0`
- Blockers: `7`
- Order created: `False`
- Submit attempted: `False`

## Tickets

| Client order id | Symbol | Side | Qty | Ref price | Notional |
| --- | --- | --- | ---: | ---: | ---: |

## Blockers

- account_position_reconciliation_missing
- broker_api_adapter_not_connected
- human_approval_missing
- kill_switch_not_armed
- market_data_freshness_missing
- minimum_paper_observation_days_missing
- no_broker_order_tickets