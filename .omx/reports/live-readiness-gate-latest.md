# Live-readiness gate

Safety: readiness report only; no orders, no broker, no credentials, no advice.

## Summary

- Live trading authorized: False
- Promotion level: paper_dry_run_candidate
- Paper dry-run ready: True
- Paper observation days: 9 / 12
- Target live pilot date: 2026-06-16
- Top candidate: AAPL_0.3_GLD_0.7
- Passing candidates: 4
- Operational risk status: monitoring
- Independent price status: pass

## Passing candidates

| Candidate | Weights | Median excess | Worst MDD | Fundamentals | Recent |
| --- | --- | ---: | ---: | --- | --- |
| AAPL_0.3_GLD_0.7 | {'AAPL': 0.3, 'GLD': 0.7} | 12.09% | -18.29% | pass | pass |
| AAPL_0.36_GLD_0.64 | {'AAPL': 0.36, 'GLD': 0.64} | 10.35% | -17.63% | pass | pass |
| AAPL_0.4_GLD_0.6 | {'AAPL': 0.4, 'GLD': 0.6} | 9.34% | -17.79% | pass | pass |
| XLK_0.3_GLD_0.7 | {'XLK': 0.3, 'GLD': 0.7} | 7.56% | -19.74% | not_applicable | pass |

## Live blockers

- live_pilot_target_date_not_reached
- minimum_paper_observation_window_missing
- tax_cost_and_liquidity_review_missing
- human_approval_missing
- legal_or_registered_adviser_review_missing_for_automated_investment_advice
- broker_sandbox_and_order_reconciliation_intentionally_not_connected
- broker_api_latency_budget_not_defined
- slippage_and_spread_model_not_validated_against_live_quotes
- partial_fill_rejection_cancel_replace_handling_missing
- idempotency_keys_and_duplicate_order_prevention_missing
- rate_limit_backoff_and_outage_recovery_missing
- account_position_reconciliation_missing
- market_hours_holiday_and_corporate_action_handling_missing

## Required next evidence

- Collect no-order dry-run target logging through the 2026-06-16 live-pilot review target.
- Replicate price history with an independent licensed or official data source.
- Keep operational risk gate passing: drift monitor, loss limits, stale-data halt, and manual kill switch.
- Define broker API latency budget, stale-quote halt, idempotent order model, partial-fill handling, and reconciliation tests before any broker sandbox.
- Complete tax/cost/liquidity and legal/adviser-status review before any real capital.