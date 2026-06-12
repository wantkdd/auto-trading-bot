# Independent price replication gate

Safety: independent price replication only; no orders, no broker, no credentials, no advice.

## Summary

- Status: `pass`
- Provider: `alpha_vantage`
- Symbols checked: `2`
- Max close diff bps: `100.0`
- Order created: `False`
- Live trading authorized: `False`

## Blockers

- none

## Required next evidence

- Provide STOOQ_API_KEY or ALPHA_VANTAGE_API_KEY to run independent replication.
- Keep independent close differences within the configured basis-point tolerance.
- Do not treat independent replication as live-trading approval.