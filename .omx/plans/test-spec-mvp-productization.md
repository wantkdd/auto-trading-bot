# Test Spec: Offline MVP Productization

## Test claims
1. Existing behavior still passes its full regression suite.
2. Example reports are generated from the committed example CSV by the committed CLI.
3. Committed example reports contain the required no-live-trading safety fields/caveats.
4. README and docs do not imply live trading authorization.
5. Static safety gates still prevent broker/network/credential/live-order pathways.

## Required checks
- `uv run --with pytest python -m pytest -q`
- `uvx ruff check .`
- `uvx mypy --python-version 3.11 --strict --explicit-package-bases src/auto_trading_bot`
- `uvx mypy --python-version 3.11 --ignore-missing-imports tests`
- `python3 -m compileall -q src tests`
- `python3 -m tabnanny src tests`
- CLI smoke to regenerate sample reports into a temp directory and compare committed sample JSON against regenerated JSON, allowing only intentional local path differences such as `assumptions.data_source`.

## New regression tests
- `test_committed_example_report_matches_regenerated_cli_output`
  - Runs CLI against `examples/data/sample_ohlcv.csv` into temp output.
  - Loads regenerated and committed `examples/reports/moving-average-report.json`.
  - Normalizes only path-dependent fields (`assumptions.data_source`) and then asserts the JSON payloads are equal.
  - Asserts generated and committed JSON have the safety statement, `live_trading_authorized=false`, holdout headline metrics, and costs included.
- `test_docs_document_offline_boundary_and_example_command`
  - Verifies README mentions the sample CSV, exact backtest command shape, generated report names, and no-live-trading safety statement.
  - Verifies future-live-trading gate docs preserve the approval-gated boundary and do not authorize live trading.

## Manual spot checks
- Read `README.md` for a new-user flow.
- Inspect `examples/reports/moving-average-report.md` for readable caveats, metrics, validation, and flags.
