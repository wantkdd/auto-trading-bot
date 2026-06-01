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

## Future live-trading work

Any paper or live trading proposal must pass a separate approval gate before design or implementation. See `docs/future-live-trading-gate.md`. Until that gate is approved, this repository remains local-simulator-only and must not add broker SDKs, network clients, credential storage, account reads, or order-routing paths.
