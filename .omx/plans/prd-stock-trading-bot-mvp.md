# PRD: Stock Auto-Trading Bot MVP — Validation-First, No Live Orders

## 1. Requirements Summary

Build a greenfield stock-trading research and validation system that can later become an automated trading bot, but whose MVP **does not place real orders**. The MVP must help decide whether Korean or US equities are the better initial market, run explainable strategy backtests, validate them robustly, and produce reports that prevent overconfident live deployment.

Source of truth:
- Deep-interview spec: `.omx/specs/deep-interview-stock-trading-bot.md`
- Best-practice research: `.omx/research/stock-trading-bot-best-practice-20260528T081731Z.md`

## 2. User Intent

The user wants a “very smart” stock auto-trading bot that can start with small capital and receive more capital only if it performs well. The clarified requirement is: maximize correctness, validation rigor, and risk controls before any real-money trading.

## 3. Non-Goals / Hard Safety Boundaries

1. **No live automatic order execution in MVP.**
2. **No leverage, margin, short selling, futures/options, crypto, or derivatives in MVP.**
3. **No real broker credentials in source code or test fixtures.**
4. **No profit guarantee claims.** Reports must explicitly say backtests and paper trading are not live-trading proof.
5. **No paid API/data subscriptions without later explicit user approval.**
6. **No network calls, broker SDK imports, credential reads, or external production side effects** during tests; all tests must use local fixtures/fakes.

## 4. In Scope

### 4.1 Market/Data Feasibility
- Compare Korea vs US initial-market feasibility.
- Record official data/broker candidates:
  - Korea: KRX Open API/Data Marketplace, public data portal FSC/KRX stock-price information, KIS Open API / KIS GitHub samples.
  - US: Alpaca paper/data API, IBKR paper/TWS API as secondary candidate.
- Store market comparison as a repo document, not as hardcoded claims in strategy logic.

### 4.2 MVP Software
- Python package with modular architecture:
  - `data`: CSV/offline bar loading and future data-provider interfaces.
  - `strategy`: explainable strategies, starting with moving-average crossover and momentum.
  - `backtest`: event/order simulation with next-bar execution to avoid look-ahead.
  - `risk`: drawdown and future capital-gate rules.
  - `metrics`: total return, CAGR where possible, volatility, Sharpe/Sortino, max drawdown, win rate, turnover, trade count.
  - `validation`: train/test split and walk-forward evaluation.
  - `reports`: markdown/JSON summaries with caveats and disqualification flags.
  - `broker`: **local simulated broker only**; no remote broker paper API, no live broker implementation, no SDK endpoint, no credentials.
- CLI or script entrypoint for local fixture backtests.
- Unit tests for calculations and safety gates.

### 4.3 Validation Protocol
- Data integrity checks: sorted timestamps, no duplicate bars, nonnegative prices/volume, gap awareness.
- Transaction-cost assumptions: commission and slippage configurable and included in reports.
- Anti-overfitting checks: train/test split or walk-forward windows.
- Benchmark comparison: buy-and-hold baseline.
- Risk checks: max drawdown threshold, loss limit status, trade-count/turnover review.

## 5. RALPLAN-DR Summary

### Principles
1. **Safety before automation** — live order pathways must be impossible in MVP.
2. **Evidence before capital** — strategies graduate only through reproducible validation.
3. **Explainability before complexity** — baseline strategies first; ML/LLM decisions later only if justified.
4. **Broker/data portability** — market choice must not infect core strategy/backtest logic.
5. **Current official docs before external integration** — API claims must be re-verified near integration time.

### Decision Drivers
1. **Real-money risk**: accidental live trading or untested assumptions are unacceptable.
2. **Data quality and API feasibility**: Korea vs US feasibility affects architecture and testing.
3. **Reproducibility**: every performance claim must be backed by local data fixtures or saved reports.

### Viable Options

#### Option A — Pure-Python validation core first (Chosen)
- Pros: smallest safe surface, no accidental broker side effects, fast tests, easy audit, no dependency lock-in.
- Cons: less feature-rich than full trading frameworks; later paper/live adapters require extra work.

#### Option B — QuantConnect LEAN-first
- Pros: mature algorithmic engine, backtesting/live concepts already modeled, aligns with KIS GitHub backtester reference.
- Cons: heavier setup, data-format friction, overkill before market/API choice is settled.

#### Option C — Broker SDK first (Alpaca/KIS first)
- Pros: fastest route to paper trading with a real API.
- Cons: increases credential/API/side-effect risk too early; market choice may bias architecture.

## 6. ADR

### Decision
Start with **Option A: a pure-Python, broker-agnostic validation core** plus source-backed market-comparison documentation. Defer broker SDK integration until after the core proves backtest correctness and safety gates.

### Drivers
- MVP must not place live orders.
- Accuracy and testability outrank speed to live trading.
- Korea/US market choice is unresolved and should remain outside core backtest logic.

### Alternatives Considered
- LEAN-first: rejected for initial MVP due setup/data complexity and higher scope.
- Broker SDK first: rejected because it creates premature credential/API/live-path risk.

### Why Chosen
It creates a safe foundation: deterministic tests, fixture-based validation, explicit absence of live-order code, and future adapters behind stable interfaces.

### Consequences
- We will implement more basic infrastructure ourselves initially.
- Later broker/data adapters can be added only after official-doc recheck and explicit approval.
- Performance reports will be conservative and caveated.

### Follow-ups
1. Implement pure-Python MVP core and tests.
2. Add market-comparison document with official sources.
3. Run sample fixture backtests.
5. Separately approve any remote broker paper-trading adapter after fresh official-doc/regulatory review.
4. Only after MVP passes tests, consider a separate paper-trading adapter story.

## 7. Implementation Plan

### Phase 1 — Project Skeleton and Safety Invariants
- Add `pyproject.toml` for package/test configuration.
- Add `src/auto_trading_bot/` package.
- Add `tests/` with safety tests that assert no live broker/order side effects exist.
- Add structural safety tests that fail on broker SDK imports, HTTP/WebSocket client imports, broker endpoint literals, trading API key env names, `.env` dependency, or any order-submission method outside the local simulator.
- Add `docs/market-comparison.md` from research evidence.

### Phase 2 — Data and Domain Model
- Implement immutable bar/trade/order/result data types.
- Implement CSV loader with strict validation.
- Implement `DataValidationError` for bad fixtures.

### Phase 3 — Strategies
- Implement baseline strategies:
  - Moving-average crossover.
  - Momentum lookback.
- Enforce signal timing so today’s close cannot execute at today’s already-known price.

### Phase 4 — Backtest Engine
- Long-only, cash-only engine.
- Next-bar open execution.
- Configurable commission and slippage.
- Position/cash/equity accounting.
- Trade ledger and equity curve output.

### Phase 5 — Metrics and Validation
- Return, CAGR, volatility, Sharpe, max drawdown, win rate, turnover, exposure, benchmark return.
- Train/test split and walk-forward windows.
- Disqualification checks for max drawdown, insufficient trades, underperforming benchmark after costs.

### Phase 6 — Reports and CLI
- Generate markdown and JSON report.
- CLI runs backtest from CSV fixture and writes reports.
- Include explicit caveat: “not investment advice; not live-trading proof.”

### Phase 7 — Verification and Review
- Run unit tests.
- Run lint/static checks where available.
- Run code review and safety audit.

## 8. Testable Acceptance Criteria

1. `pytest` passes for all local unit tests.
2. Backtest engine cannot import or instantiate a live broker adapter because none exists in MVP; tests also block broker SDKs, HTTP/WebSocket clients, broker endpoints, credential/env reads, and `.env` dependencies.
3. A strategy signal generated from bar `t` executes no earlier than bar `t+1`.
4. Commission/slippage reduce realized returns in deterministic tests.
5. CSV loader rejects duplicate timestamps, unsorted rows, negative prices, and malformed rows.
6. Max drawdown metric is tested against a known equity curve.
7. Walk-forward validation returns separate train/test windows without overlap.
8. Sample CLI/report run creates markdown + JSON output from fixture data.
9. Report includes risk caveats, disqualification flags, and the exact statement: “This MVP cannot place orders and is not approval for live trading.”
10. `docs/market-comparison.md` cites official/current sources and recommends a first implementation path without authorizing live trading.

## 9. Risks and Mitigations

| Risk | Mitigation |
|---|---|
| Backtest overstates returns | next-bar execution, costs/slippage, walk-forward split, benchmark comparison |
| Accidental live trading | no live adapter, no broker credentials, safety tests, hard non-goal in docs |
| Bad market-data assumptions | source-backed market comparison, recheck official docs before adapters |
| Overcomplex first version | pure-Python core; defer LEAN/broker SDK |
| User expects guaranteed profit | reports must state limitations and disqualification reasons |

## 10. Available-Agent-Types Roster

- `executor` (`gpt-5.5`, medium): implementation.
- `test-engineer` (`gpt-5.5`, medium): test design and edge cases.
- `architect` (`gpt-5.5`, high): architecture/safety review.
- `critic` (`gpt-5.5`, high): plan and quality gate challenge.
- `dependency-expert` (`gpt-5.5`, high): future broker/data/library selection.
- `code-reviewer` (`gpt-5.5`, high): final review.
- `verifier` (`gpt-5.5`, high): evidence validation.

## 11. Follow-up Staffing Guidance

### Default: `$ultragoal`
Use one durable goal ledger with sequential stories: skeleton/safety, data+strategy, backtest, validation/reporting, docs/review.

### Team + Ultragoal (if parallelizing)
- Lane 1 `executor`: domain/data/backtest core.
- Lane 2 `test-engineer`: test fixtures and edge cases.
- Lane 3 `writer` or `dependency-expert`: market comparison doc/source updates.
- Leader checkpoints evidence in Ultragoal.

### Ralph fallback
Use `$ralph` only if a single persistent owner is explicitly preferred after planning; not the default.

## 12. Launch Hints

- Default durable execution: `$ultragoal .omx/plans/prd-stock-trading-bot-mvp.md`
- Parallel execution option: `$team .omx/plans/prd-stock-trading-bot-mvp.md`
- Consensus artifacts: PRD + test spec + Architect/Critic review record required before coding.

## 13. Team Verification Path

Team or solo execution must prove:
1. No live-order path exists.
2. Deterministic backtest accounting passes tests.
3. Report generation works on fixture data.
4. Market comparison cites sources and does not imply live authorization.
5. Final code review and safety review are clean.

## 14. Changelog

- Initial consensus draft created from deep-interview and source-backed research.
- Architect ITERATE feedback applied: MVP is now explicitly offline/local-simulator-only; remote broker paper APIs are deferred; safety tests now block network, broker SDK, endpoint, credential, and order-submission pathways.
