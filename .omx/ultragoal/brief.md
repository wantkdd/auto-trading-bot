# Ultragoal Execution Brief: Stock Trading Bot MVP

Use approved RALPLAN artifacts:
- PRD: `.omx/plans/prd-stock-trading-bot-mvp.md`
- Test spec: `.omx/plans/test-spec-stock-trading-bot-mvp.md`
- Consensus record: `.omx/plans/ralplan-consensus-stock-trading-bot-mvp.json`

Original constraints are binding:
- MVP must be offline/local-simulator-only.
- No live automatic orders.
- No remote broker paper API in MVP.
- No broker SDK imports, HTTP/WebSocket clients, broker endpoints, credentials, `.env`, or external network calls in production MVP code/tests.
- No leverage/margin/shorting/derivatives.
- Reports must state: “This MVP cannot place orders and is not approval for live trading.”

## Durable Stories

G001 — Skeleton, docs, and safety invariants
Objective: Create Python package skeleton, market-comparison documentation, and static safety tests blocking broker/network/credential/live-order pathways.
Evidence: files exist; static safety tests pass.

G002 — Data/domain/strategy core
Objective: Implement immutable domain models, strict CSV loader, moving-average crossover strategy, and momentum strategy with no look-ahead signal behavior.
Evidence: data/model/strategy tests pass.

G003 — Backtest engine and metrics
Objective: Implement long-only cash-only next-bar-open backtest engine with commission/slippage, trade ledger, equity curve, and metrics including max drawdown, returns, win rate, turnover, Sharpe-like risk measure, and benchmark comparison.
Evidence: accounting/metrics tests pass.

G004 — Validation, reports, and CLI
Objective: Implement train/test and walk-forward validation, markdown/JSON reporting with caveats/disqualification flags, and CLI fixture smoke path.
Evidence: CLI smoke generates reports; report tests pass.

G005 — Final verification, cleanup, and review
Objective: Run full pytest/static checks, run cleanup/no-op anti-slop pass, independent code/architecture review, and checkpoint completion evidence.
Evidence: tests pass; review artifacts approve or blockers are recorded.
