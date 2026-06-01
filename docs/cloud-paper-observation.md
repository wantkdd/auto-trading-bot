# Cloud paper-observation automation

This project can run paper observation without keeping a MacBook awake by using GitHub Actions scheduled workflows. The workflow is research-only: no broker, no credentials, no orders, and no investment advice.

## Selected option

Use `.github/workflows/paper-observation.yml` after this repository is pushed to GitHub.

Why this is the default:

- It runs on GitHub-hosted infrastructure, so the MacBook can be off.
- It needs no broker account, no trading credentials, and no paid server.
- It uses the existing no-order scripts and static safety tests before appending a paper observation.
- It stores the latest durable log on a separate `paper-observation-state` branch and uploads per-run artifacts for review.

## Schedule

The workflow runs at `02:30 UTC` Tuesday-Saturday, which is `11:30 KST`. That is after the regular US market close window and gives free data sources time to publish the prior US session bar.

GitHub scheduled workflows run from the latest commit on the default branch. Schedules may not execute at an exact wall-clock second, so the workflow is written to be idempotent for the same `as_of_date`.

## Broad market scan

Each scheduled run now also writes `.omx/reports/market-universe-scan-latest.json` and `.md`. This scans a broad non-leveraged large/liquid watchlist, but it does not automatically switch the locked paper strategy. Candidate replacement requires a separate promotion gate; the workflow remains no-order and not live trading.

## No-order preview

After writing the hypothetical trade-intent log, the workflow also writes `.omx/reports/no-order-preview-latest.json` and `.md`. This runs the local no-order adapter contract against the latest `would_buy` / `would_sell` rows and records accepted/rejected intents, accepted notional, and `order_created: false`. It is a validation report only: no broker, no credentials, no API calls, and no orders.

## State and artifacts

- Durable observation log: `paper-observation-state:reports/paper-observation-log.jsonl`
- Hypothetical trade-intent log: `paper-observation-state:reports/paper-trade-intent-log.jsonl`
- Latest no-order preview: `paper-observation-state:.omx/reports/no-order-preview-latest.json`
- Latest generated reports: `paper-observation-state:.omx/reports/*latest*`
- Per-run artifacts: uploaded by GitHub Actions with `retention-days: 90`

The state branch is intentionally separate from `master/main` so generated logs do not pollute source commits.

## How to activate

1. Push this repository to GitHub.
2. Ensure GitHub Actions is enabled for the repository.
3. Ensure the workflow file is on the default branch.
4. Run the workflow once manually with `workflow_dispatch` from the Actions tab.
5. Confirm the `paper-observation-state` branch is created and contains `reports/paper-observation-log.jsonl`.

## Limitations

- This is not live trading and cannot place orders.
- GitHub Actions scheduled runs can be delayed or skipped during service issues; manual dispatch can backfill a day if needed.
- Free public data can revise, lag, or fail. The log captures the data observed at run time but does not guarantee vendor completeness.
- A short paper-observation run is only an early checkpoint. It cannot prove stable profitability.
- Any future broker sandbox needs the separate API operational risk gate in `docs/api-operational-risk-gate.md`.

## Alternative options considered

| Option | Pros | Cons | Decision |
| --- | --- | --- | --- |
| GitHub Actions schedule | No Mac needed, no server admin, built-in logs/artifacts, easy manual run | Schedule timing is best-effort, requires GitHub repo | Selected |
| Always-on VPS cron | More control over timing and storage | Paid server, patching/security burden | Later if stricter timing is needed |
| Serverless cron | Low ops if packaged well | More cloud setup, logs/storage/egress complexity | Later if GitHub schedule proves unreliable |
| Mac launchd | Simple local setup | Mac must be awake and online | Rejected for this user constraint |
