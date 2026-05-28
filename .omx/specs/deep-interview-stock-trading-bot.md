# Execution-Ready Spec: Stock Auto-Trading Bot MVP

## Metadata
- Profile: standard deep-interview
- Context type: greenfield; no source files found except `.omx/` state directory
- Rounds: 6
- Final ambiguity: 12.9%
- Threshold: 20%
- Context snapshot: ``
- Transcript: `.omx/interviews/stock-trading-bot-20260528T081308Z.md`
- Prompt-safe initial-context summary: not needed

## Clarity Breakdown
| Dimension | Score | Notes |
|---|---:|---|
| Intent | 0.90 | 수익 목적이지만 검증 우선, 정확도/안전성 최우선으로 정리됨 |
| Outcome | 0.84 | 백테스트+워크포워드+모의투자 기반 검증 시스템 |
| Scope | 0.88 | MVP는 실거래 자동주문 제외, 레버리지/미수/공매도 제외 |
| Constraints | 0.86 | 실제 돈 전 단계 승인, 손실한도, 보수적 검증, 정확도 우선 |
| Success | 0.86 | 검증 리포트, 시장 비교, 전략 후보 평가, 모의검증 통과 기준 |

## Intent
Build a stock auto-trading project that can eventually manage real capital, but only after rigorous validation. The user's priority is not flashy automation; it is a highly reliable, thoroughly researched, testable system where correctness and risk controls come before speed.

## Desired Outcome
A greenfield MVP that can:
1. Compare Korean vs US stock-market feasibility for the user's goal.
2. Recommend an MVP market based on data availability, broker/API feasibility, cost, legal/operational constraints, and validation quality.
3. Backtest candidate strategies on historical data with transaction costs and realistic assumptions.
4. Run robust validation: train/test or period split, walk-forward checks, overfitting guards, drawdown analysis, and paper-trading readiness.
5. Produce readable reports that explain performance, maximum drawdown, assumptions, weaknesses, and whether a strategy is disqualified.

## In Scope
- Python-oriented greenfield project structure unless later research strongly justifies otherwise.
- Data-source and broker/API candidate research for Korea and US markets.
- Initial strategy candidates chosen by the agent after research; likely simple, explainable baselines before complex ML.
- Validation metric design: return, max drawdown, volatility, Sharpe/Sortino where appropriate, win/loss stats, turnover, fees/slippage sensitivity, benchmark comparison.
- Backtesting and paper-trading architecture planning.
- Risk-management model for future live phase, including stop conditions and capital-scaling gates.

## Out of Scope / Non-goals for MVP
- No live automatic order execution in the first MVP.
- No leverage, margin, short selling, futures/options, or other high-risk amplified instruments.
- No promise or guarantee of profit.
- No direct use of real broker credentials or real-money trading without a later explicit approval gate.

## Decision Boundaries
OMX/Codex may decide without further confirmation:
- Technical stack and project structure.
- Data-source candidates to investigate and recommend.
- Initial strategy candidates to test.
- Validation metrics and default reporting structure.
- File/module organization and testing approach.

Must require explicit user confirmation later:
- Any real-money trading or live automatic order placement.
- Any broker credential handling.
- Any paid data/API subscription.
- Any use of leverage/margin/shorting or similarly risky instruments.
- Any capital increase beyond the initial small test amount.

## Constraints
- Accuracy and rigorous validation are top priority, even if research/planning uses more time/tokens.
- Because actual money may later be involved, use official/current sources for broker/data APIs, market calendars, fees, and limitations during planning.
- Treat backtest results skeptically: account for overfitting, survivorship bias, look-ahead bias, transaction costs, slippage, and regime changes.
- First live phase, if later approved, should include a kill-switch. The user's provisional tolerance is moderate: roughly -10% to -20% initial capital drawdown with staged warning/reduction/stop behavior.

## Testable Acceptance Criteria
Planning output should define:
1. A Korea-vs-US market comparison with source-backed data/API/broker feasibility.
2. A recommended MVP market and rationale.
3. A minimal project architecture for data ingestion, backtesting, strategy modules, validation, reports, and future paper/live adapters.
4. At least 2–4 explainable baseline strategy candidates and disqualification criteria.
5. A validation protocol including backtest, period split/walk-forward, costs/slippage, drawdown, benchmark comparison, and paper-trading readiness.
6. Clear safety gates that prevent live automatic order execution in MVP.
7. Tests/static checks for calculation correctness and no accidental live-order pathways.

## Assumptions Exposed + Resolutions
- Assumption: A smart bot can simply earn money well. Resolution: The MVP cannot guarantee profit; it can build a rigorous validation and risk-control system.
- Assumption: Passing validation means safe live trading. Resolution: Live trading remains risky; MVP excludes live auto-orders and later live trading requires explicit approval and kill-switch gates.
- Assumption: Market choice can wait. Resolution: Korea vs US materially changes data, broker/API, fees, tax/market calendars, and implementation; planning must compare both and recommend one.

## Pressure-pass Findings
Round 3 challenged the Round 2 validation assumption. The resulting spec separates validation from real-money automation and adds explicit risk/approval gates.

## Technical Context Findings
- Repository is currently greenfield: no implementation files found under `/Users/SangwanYu/Documents/자동매매봇` except `.omx/`.
- Next stage should perform official/current external research before selecting data providers, broker APIs, or market-specific assumptions.

## Condensed Transcript
# Deep Interview Transcript: Stock Trading Bot

- Profile: standard
- Context type: greenfield
- Final ambiguity: 12.9%
- Threshold: 20%
- Context snapshot: ``

## Rounds
1. Intent/risk posture → `검증 우선`: 백테스트·모의투자에서 먼저 증명.
2. Success criteria → `보수적 검증 패키지`: 백테스트, 워크포워드/기간분리, 모의투자, 손실한도 테스트.
3. Contrarian pressure / risk boundary → `중립적`: 초기 실거래 단계에서는 -10%~-20% 범위에 경고/축소/중지 로직 필요. 단, MVP 실거래 자동주문은 제외.
4. Non-goals → `실거래 자동주문 제외`, `레버리지/미수/공매도 제외`.
5. Decision boundaries → Agent may decide tech stack, data-source candidates, strategy candidates, validation metrics, project structure. User emphasized rigorous research and accuracy because real money may later be involved.
6. Market scope → `한국/미국 둘 다 후보 조사`: compare and recommend MVP market.

## Pressure-pass finding
The assumption that robust validation permits live trading was challenged: even after validation, live losses can occur. The spec therefore separates MVP validation from live auto-ordering and requires an explicit later approval gate.

