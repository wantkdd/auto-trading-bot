# Test Spec: Stock Auto-Trading Bot MVP

## Scope
Verification for the validation-first MVP. Tests must run locally without network, credentials, broker accounts, or live order side effects.

## Test Layers

### Unit Tests
1. Domain model validation:
   - Bars reject invalid OHLCV values.
   - Orders/trades are immutable where practical.
2. CSV loader:
   - Accepts valid fixture.
   - Rejects duplicate timestamps.
   - Rejects unsorted timestamps.
   - Rejects negative/zero invalid OHLC prices.
3. Strategies:
   - Moving-average crossover emits expected buy/sell/hold sequence.
   - Momentum strategy respects lookback and emits no signal before enough data.
4. Backtest accounting:
   - Buy reduces cash by price + commission + slippage.
   - Sell increases cash net of costs.
   - Cannot buy more than available cash in cash-only mode.
   - Cannot short in MVP.
   - Signal at bar `t` executes at bar `t+1` open.
5. Metrics:
   - Total return, max drawdown, Sharpe, win rate, turnover against known values.
6. Validation:
   - Train/test split has no overlap.
   - Walk-forward windows are ordered and complete.
7. Reports:
   - Markdown and JSON reports include strategy, data period, assumptions, metrics, caveats, disqualification flags.

### Integration Tests
1. Run CLI on fixture CSV and generate reports.
2. Run two baseline strategies on same fixture and compare output schema.
3. Confirm all report paths are under local output directory.

### Safety Tests
1. Static import test: production code must not import broker SDKs or network clients (`requests`, `httpx`, `urllib.request`, `websocket`, `websockets`, `alpaca`, `ib_insync`, `koreainvestment`, `kiwoom`, `pykiwoom`).
2. Static endpoint test: production code must not contain broker/data endpoint literals such as `alpaca.markets`, `paper-api`, `apiportal.koreainvestment`, `openapi.krx`, `interactivebrokers`, `kis`, `appkey`, `secretkey`.
3. Credential test: production code and fixtures must not read trading-related environment variables or depend on `.env`.
4. Order-path test: no method/function name may imply remote order submission (`submit_order`, `place_order`, `send_order`, `buy_live`, `sell_live`) outside the local simulator.
5. No environment variable is required for tests.
6. No network calls in tests or production MVP runtime.
7. Any broker interface in MVP must be local-simulator-only and explicitly unable to reach remote services.

### Observability / Audit
1. Backtest result includes warnings/caveats.
2. Report records commission/slippage assumptions.
3. Report records disqualification reasons when thresholds fail.
4. Logs/errors should be deterministic and not leak secrets.

## Acceptance Gates

- `python -m pytest` passes.
- CLI smoke test passes on fixture data.
- Source tree contains no live-order implementation.
- Documentation states MVP cannot trade real money.
- Code review approves safety/architecture.

## Known Non-Tested Gaps Allowed in MVP

- No real broker paper endpoint integration yet; remote broker paper APIs are a separate future approval-gated story.
- No paid/credentialed data source integration.
- No tax/legal automation.
- No ML/LLM trading decisions.
