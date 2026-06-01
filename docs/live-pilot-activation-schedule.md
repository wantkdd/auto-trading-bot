# Live Pilot Activation Schedule

This schedule makes the system ready to move from no-order observation to a broker sandbox and then a tightly capped live pilot on the operator-requested 2026-07-01 target, if the evidence and approval gates allow it. It does **not** authorize immediate live trading, does not guarantee profit, and does not bypass human/legal/operator approval.

Safety boundary: no leverage, no margin, no shorting, no options, no inverse/leveraged ETFs, no automatic strategy self-modification, no live orders before the live pilot gate, and no broker credentials in source control.

## Current state as of 2026-06-02 KST

- Promotion level: `paper_dry_run_candidate`.
- Live trading authorized: `false`.
- Paper observation: `1 / 22` target sessions recorded, starting with the 2026-05-29 US session.
- Locked champion for observation: `AAPL_0.3_GLD_0.7`.
- Broker preflight: blocked by design; generated order tickets are deterministic previews only.
- No-order gate: passing in the latest persisted state branch.
- Intraday aggregation: active via the no-order monitor state branch; it records quote/judgement summaries only and does not create orders.

## Earliest activation calendar

The operator-selected live-pilot review target is 2026-07-01 KST. That uses the available no-order evidence through the 2026-06-30 US session rather than a 30-trading-day requirement. From the first observed 2026-05-29 US session through 2026-06-30, excluding the 2026-06-19 NYSE holiday, the target observation window is 22 US trading sessions.

| Date / window | Target | Required result |
| --- | --- | --- |
| 2026-06-02 KST | Schedule lock | Keep daily no-order paper workflow and intraday no-order monitor active. |
| 2026-06-02 to 2026-06-18 US sessions | Observation days 2-15 | Daily paper report stays green; no-order gate pass; no live credentials. |
| 2026-06-19 | NYSE closed | No missing-observation incident for the holiday. |
| 2026-06-22 to 2026-06-30 US sessions | Observation days 16-22 | Finish the operator-requested July 1 evidence window. |
| 2026-07-01 KST | Live-pilot readiness review | Latest report should show at least `22 / 22`, no-order gate pass, no halt, no unresolved data mismatch. |
| 2026-07-01 KST daytime | Broker sandbox final check | Run paper/sandbox adapter only; prove endpoint separation, idempotency, reconciliation, cancel/reject handling, and kill switch. |
| 2026-07-01 US session, earliest | Limited live pilot decision window | If all gates pass and human/legal approval exists, enable a very small capped live pilot; otherwise stay in sandbox/no-order mode. |

## Work that can start immediately

1. Keep GitHub Actions schedules active and verify the `paper-observation-state` and `intraday-no-order-state` branches daily.
2. Prepare a broker-neutral sandbox adapter behind an explicit paper-only gate.
3. Default the first broker candidate to Alpaca paper only unless the operator selects a different broker before implementation.
4. Add tests proving live endpoints cannot be used while `live_trading_authorized=false`.
5. Add order lifecycle tests for idempotency keys, duplicate prevention, partial fills, rejects, cancels, stale quotes, market hours, account-position reconciliation, and kill switch.
6. Prepare a live pilot runbook with fixed caps:
   - max symbols: champion symbols only unless separately approved;
   - max notional: tiny pilot amount only, configured outside source;
   - daily loss halt and drawdown halt required;
   - manual kill switch required;
   - no automatic strategy promotion from challenger to live.

## Non-negotiable live pilot gate

Live pilot can only start when every item below is true:

- `minimum_paper_observation_window_missing` is cleared for the 2026-07-01 target window.
- `live_pilot_target_date_not_reached` is cleared.
- No-order gate is `pass` and operational halt is `false`.
- Independent price replication is `pass`.
- Broker sandbox adapter has passed endpoint-separation and order-lifecycle tests.
- Paper/sandbox account reconciliation matches expected positions and cash.
- Tax/cost/liquidity review is recorded.
- Human approval is recorded for the exact pilot caps.
- Legal/adviser-status review is recorded for automated investment advice risk.
- Kill switch is armed and tested.
- `live_trading_authorized` is set only by an explicit approval artifact, never by code inference.

## If a gate fails

- Data mismatch, stale data, failed reconciliation, missing observation day, or kill-switch issue: stay no-order/sandbox and restart the affected evidence window if needed.
- Drawdown/loss halt: stop promotion review until manually reviewed.
- Broker endpoint ambiguity: delete/disable live endpoint config and continue paper-only.
- Missing human/legal approval: no live pilot.

## Operator checklist before 2026-07-01 KST

- Choose/confirm the broker for sandbox; default schedule assumes Alpaca paper because the existing comparison ranks it as the safest first paper-only candidate.
- Create paper/sandbox account access outside the repository.
- Do not add live credentials to GitHub or local `.env` until the live pilot gate explicitly allows it.
- Decide the maximum pilot notional and daily loss halt in writing.
- Prepare legal/tax/adviser-status notes for personal automated trading risk.

## References

- NYSE holiday calendar: https://www.nyse.com/markets/hours-calendars
- FINRA auto-trading risk notice: https://www.finra.org/investors/insights/auto-trading-unregistered-entities
- FINRA automated investment tools alert: https://www.finra.org/investors/alerts/automated-investment-tools
- SEC automated investment advice page: https://www.sec.gov/about/divisions-offices/office-strategic-hub-innovation-financial-technology-finhub/automated-investment-advice
