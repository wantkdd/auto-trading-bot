# Auto Trading Bot Offline MVP

This repository is an offline validation-first stock trading research MVP. It loads local OHLCV CSV files, runs deterministic local backtests, and writes Markdown/JSON validation reports.

**Safety boundary:** This MVP cannot place orders and is not approval for live trading. It has no broker integration, no network client, no credential handling, no account access, and no paper/live adapter path. Outputs are research artifacts only; they are not investment advice and do not guarantee profit.

## Local setup

Requirements:

- Python 3.11 or newer
- [`uv`](https://docs.astral.sh/uv/) for local command execution

Install/run from the repository root:

```bash
uv run --with pytest python -m pytest -q
```

Optional static checks used by maintainers:

```bash
uvx ruff check .
uvx mypy --python-version 3.11 --strict --explicit-package-bases src/auto_trading_bot
uvx mypy --python-version 3.11 --ignore-missing-imports tests
python3 -m compileall -q src tests
python3 -m tabnanny src tests
```

## CSV input schema

Backtests read a local CSV file with this exact header:

```csv
timestamp,open,high,low,close,volume
```

Rows must satisfy these rules:

- `timestamp`: ISO-8601-compatible timestamp, strictly increasing and unique.
- `open`, `high`, `low`, `close`: positive numeric prices with valid OHLC relationships.
- `volume`: nonnegative numeric volume.
- Files are read from local disk only; the CLI does not download market data.

A deterministic fixture is committed at `examples/data/sample_ohlcv.csv`. The `SAMPLE` / `offline-fixture` data is synthetic and pedagogical; its metrics are for report-shape demonstration only, not market-performance evidence.

## Run the sample backtest

Generate the committed sample report shape from local data:

```bash
uv run python -m auto_trading_bot.cli backtest \
  --csv examples/data/sample_ohlcv.csv \
  --output-dir examples/reports \
  --strategy moving-average \
  --symbol SAMPLE \
  --market offline-fixture \
  --short-window 3 \
  --long-window 8 \
  --train-fraction 0.65 \
  --data-provenance synthetic_offline_fixture \
  --example-only \
  --min-trades 0
```

The command writes:

- `examples/reports/moving-average-report.md`
- `examples/reports/moving-average-report.json`

The report bundle includes the strategy name, local data period, assumptions, costs, benchmark metrics, holdout validation metrics, disqualification flags, warnings, `example_only=true`, `data_provenance=synthetic_offline_fixture`, and `live_trading_authorized=false`.

## Report interpretation

- Headline metrics use the out-of-sample holdout slice when `--validation-mode holdout` is used.
- Training metrics are diagnostic only and are included to make the split auditable.
- Costs are included through `--commission-rate` and `--slippage-bps` assumptions.
- Disqualification flags are local review gates, not trading approval.
- Even when no flags are triggered, the report still does not authorize live trading.

## Market-wide paper observation

The cloud paper workflow can scan a broad non-leveraged large/liquid universe while keeping the current strategy as a locked paper baseline. See `docs/market-wide-paper-trading-plan.md`. The scan logs hypothetical `would_buy`, `would_sell`, or `would_hold` intents only; it never creates broker orders.

## Data and modeling roadmap

The next research layer is point-in-time data modeling, not immediate LLM fine-tuning. See `docs/training-data-and-modeling-roadmap.md` and generate the source registry with:

```bash
uv run python scripts/modeling_data_source_registry.py
```

The registry records which price, SEC, macro, news, and portfolio-risk data sources are candidates for future no-order modeling.

Refresh the broad public US symbol universe with:

```bash
uv run python scripts/us_symbol_universe_refresh.py
```

The latest refresh found 12,708 listed rows and 5,386 common-equity candidates from Nasdaq Trader public directories. See `docs/free-data-source-expansion.md` for the full free/free-key source queue.

Build the current point-in-time daily feature/label dataset from cached OHLCV plus BLS macro context with:

```bash
uv run python scripts/point_in_time_dataset.py
```

This writes `.omx/datasets/point-in-time-daily.csv` plus `.omx/reports/point-in-time-dataset-latest.json` / `.md`. Features use only data available at each `as_of_date`; BLS macro points are conservatively lagged before joining, and forward labels are for offline evaluation only.

Collect a no-key BLS macro snapshot with:

```bash
uv run python scripts/bls_macro_snapshot.py
```

This writes `.omx/reports/bls-macro-snapshot-latest.json` / `.md` for CPI, unemployment, and nonfarm payroll context without API keys.

Collect a no-key GDELT news-attention snapshot with rate-limit-safe reporting:

```bash
uv run python scripts/gdelt_news_attention_snapshot.py --symbols AAPL MSFT --max-symbols 2
```

This records article samples/counts when GDELT allows it and writes `rate_limited` instead of failing the research loop when public throttles apply.

Build the cached SEC fundamental feature snapshot with:

```bash
uv run python scripts/sec_fundamental_feature_snapshot.py --as-of 2026-05-29
```

This writes `.omx/features/sec-fundamental-snapshot.csv` plus a latest report. It uses SEC filed dates as the point-in-time boundary and defaults to local cache-only mode.

Evaluate the first auditable no-order scorecard baseline with:

```bash
uv run python scripts/scorecard_baseline_report.py
```

This ranks symbols from feature columns only and evaluates forward labels offline; it is not an order signal or investment recommendation.

## Broker API comparison

Broker API work is gated before credentials or orders. See `docs/broker-api-comparison.md` and generate the current comparison report with:

```bash
uv run python scripts/broker_api_comparison.py
```

The current recommendation is to defer broker connection and start with a broker-neutral no-order adapter contract only after explicit approval.

## No-order broker adapter contract

`src/auto_trading_bot/broker_contract.py` defines the current broker boundary: validated `would_buy` / `would_sell` paper intents can be previewed by a fixture adapter, but every plan keeps `order_created=false`, `paper_api_authorized=false`, and `live_trading_authorized=false`. The contract has no broker SDK, network client, credential lookup, or account access.

Generate the latest local preview report from paper intent logs with:

```bash
uv run python scripts/no_order_preview_report.py
```

The report is written to `.omx/reports/no-order-preview-latest.json` and `.md` and is also persisted by the scheduled paper-observation workflow.

Generate the latest no-order operational risk gate with:

```bash
uv run python scripts/operational_risk_gate.py
```

This writes `.omx/reports/operational-risk-gate-latest.json` and `.md` with stale-data, drift/loss-limit, manual kill-switch, and trade-intent safety checks. It can only halt or block promotion; it cannot approve live trading.

Generate the latest independent price replication gate with:

```bash
uv run python scripts/independent_price_replication_gate.py
```

This compares the latest Yahoo-derived paper-signal closes with an independent provider. `ALPHA_VANTAGE_API_KEY` is used in auto mode when present; `STOOQ_API_KEY` remains optional and is not required if the captcha-based Stooq key is unavailable.

## No-order blocker review

The current blocker and improvement queue is tracked in `docs/no-order-blockers-and-improvements.md`. It records live-readiness blockers, paper-only evidence gaps, and safe follow-up work while preserving `order_created=false`, `paper_api_authorized=false`, and `live_trading_authorized=false`.

## Future live-trading work

Any paper or live trading proposal must pass a separate approval gate before design or implementation. See `docs/future-live-trading-gate.md`. Until that gate is approved, this repository remains local-simulator-only and must not add broker SDKs, network clients, credential storage, account reads, or order-routing paths.
