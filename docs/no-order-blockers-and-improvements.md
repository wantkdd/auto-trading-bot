# No-order blockers and improvement queue

This inspection records blockers and safe improvements for the US-only no-order
auto-trading research workflow. It is not approval to connect a broker, store
trading credentials, read accounts, or route orders.

## Current blocker map

1. **Live trading remains blocked before human/legal review.**
   `scripts/live_readiness_gate.py` intentionally keeps
   `live_trading_authorized=false` and lists unresolved items such as a minimum
   30-trading-day paper observation, independent price replication, tax/cost
   review, legal/adviser-status review, broker sandbox separation, latency
   budgets, slippage/spread validation, partial-fill handling, idempotency,
   rate-limit recovery, account reconciliation, market-hours handling, and
   corporate-action handling.
2. **The no-order adapter is still fixture-only.**
   `src/auto_trading_bot/broker_contract.py` can preview `would_buy` and
   `would_sell` intents, but every plan must keep `order_created=false`,
   `paper_api_authorized=false`, and `live_trading_authorized=false`.
3. **The paper-observation workflow is artifact-heavy and safety-critical.**
   `.github/workflows/paper-observation.yml` writes reports and a state branch;
   drift in that artifact contract could hide missing evidence even when the
   workflow still completes.
4. **Operational-risk requirements are broader than the current no-order code.**
   `docs/api-operational-risk-gate.md` documents latency, stale-data, partial
   fill, cancel/replace, duplicate-order, reconciliation, kill-switch, and audit
   blockers that must stay visible until a separate future design is approved.
5. **Static production safety is strong but intentionally narrow.**
   `tests/test_static_safety.py` protects production package code from network,
   broker SDK, credential, and remote-order patterns. Data-collection scripts may
   use public data-source API keys, so any future script-wide scanner needs an
   explicit allowlist for non-trading data providers and a denylist for broker or
   order-routing capabilities.
6. **Readiness naming can overstate evidence if operational evidence is missing.**
   `scripts/live_readiness_gate.py` separates live blockers from paper dry-run
   candidate status, but `paper_dry_run_ready` should remain clearly distinct
   from live readiness and should fail closed when operational-risk or
   independent-price reports are missing or blocked.
7. **No-order source rows must fail closed when tainted.**
   Paper intent logs are upstream inputs to preview reports, so malformed
   `as_of_date` values, `order_created=true`, live/paper authorization flags, or
   broker execution identifiers must be blocked before a clean-looking preview
   can be generated.
8. **Scheduled dry-run dates need market-session determinism.**
   `scripts/paper_signal_dry_run.py` should eventually use an explicit market
   date or a timezone-stable latest-session resolver instead of relying only on a
   local `date.today()` default around UTC/KST boundaries.

## Implemented no-order hardening from this inspection

- Pin README no-order sections in regression tests so the market-wide paper
  observation, no-order adapter, operational risk gate, and false authorization
  fields cannot disappear silently.
- Pin the cloud paper-observation artifact contract in regression tests so the
  state branch, no-order preview, operational risk gate, independent price
  replication, and feature snapshot evidence remain documented and uploaded.
- Pin the future API operational-risk gate blockers in regression tests so prose
  cannot regress into apparent live-trading approval.
- Persist `.omx/features` to the scheduled state branch along with reports so the
  SEC fundamental feature snapshot copied by the workflow is not dropped before
  the force-push.
- Fail closed on malformed paper-signal dates, live/paper authorization flags,
  broker execution identifiers, and any `order_created` value other than `false`
  in the no-order operational and preview paths.

## Next safe improvements

1. Add a dedicated script/workflow safety scanner that rejects broker SDK names,
   trading credential environment names, order-submission function names, and
   live endpoint literals while allowing documented public data-source API keys.
2. Add a generated no-order evidence index that links the latest paper signal,
   trade-intent log, no-order preview, operational risk gate, independent price
   replication, and live-readiness reports in one review artifact.
3. Add a fixture-based workflow smoke test that validates the paper-observation
   state branch file list without touching GitHub or any external service.
4. Keep all future broker-sandbox discussion behind `docs/future-live-trading-gate.md`
   and `docs/api-operational-risk-gate.md`; documentation alone must not
   authorize code that connects accounts or places orders.
5. Wire live-readiness reporting to explicit paper-observation day counts and
   keep paper-candidate labels separate from any live-readiness wording.
6. Add an explicit `--as-of`/market-session option for scheduled dry-run signal
   generation so timezone boundaries cannot silently change the observation
   window.

documentation alone must not authorize code that connects accounts or places orders.
