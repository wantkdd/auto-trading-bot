# ruff: noqa: E501
"""Generate a no-order broker API comparison report.

This registry compares broker/API candidates for a future paper-trading adapter.
It does not import broker SDKs, read credentials, connect to accounts, or place
orders. Any future adapter must pass a separate approval gate.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class BrokerCandidate:
    name: str
    official_docs: str
    account_requirement: str
    paper_support: str
    live_support: str
    market_data_notes: str
    auth_boundary: str
    integration_complexity: str
    fit_for_this_project: str
    required_user_checks: tuple[str, ...]
    blockers_before_any_live_use: tuple[str, ...]


@dataclass(frozen=True)
class BrokerDecision:
    recommendation: str
    rationale: tuple[str, ...]
    rejected_now: tuple[str, ...]
    next_safe_action: str


ALPACA_TRADING_DOCS = "https://docs.alpaca.markets/v1.3/docs/trading-api"
ALPACA_MARKET_DATA_DOCS = "https://docs.alpaca.markets/us/docs/about-market-data-api"
ALPACA_ACCOUNT_REQUIREMENTS = "https://alpaca.markets/support/requirements-alpaca-brokerage-account"
IBKR_API_DOCS = "https://www.interactivebrokers.com/campus/ibkr-api-page/"
IBKR_WEB_API_DOCS = "https://www.interactivebrokers.com/campus/ibkr-api-page/webapi-doc/"
IBKR_CPAPI_DOCS = "https://www.interactivebrokers.com/campus/ibkr-api-page/cpapi-v1/"
TRADIER_TRADING_DOCS = "https://docs.tradier.com/docs/trading"
TRADIER_ENDPOINTS_DOCS = "https://docs.tradier.com/docs/endpoints"
TRADESTATION_SIM_DOCS = "https://api.tradestation.com/docs/fundamentals/sim-vs-live/"
TRADESTATION_AUTH_DOCS = "https://api.tradestation.com/docs/fundamentals/authentication/auth-overview/"
TASTYTRADE_SANDBOX_DOCS = "https://developer.tastytrade.com/sandbox/"
ETRADE_ORDER_DOCS = "https://apisb.etrade.com/docs/api/order/api-order-v1.html"
ETRADE_AUTH_DOCS = "https://apisb.etrade.com/docs/api/authorization/get_access_token.html"
SCHWAB_TRADER_API_DOCS = "https://developer.schwab.com/products/trader-api--individual"
FINRA_DAY_TRADING = (
    "https://www.finra.org/investors/investing/investment-products/stocks/day-trading"
)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Write no-order broker API comparison report.")
    parser.add_argument("--output", default=".omx/reports/broker-api-comparison-latest.json")
    parser.add_argument("--markdown", default=".omx/reports/broker-api-comparison-latest.md")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    report = build_report()
    output = Path(args.output)
    markdown = Path(args.markdown)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    write_markdown(markdown, report)
    print(
        "broker comparison status={status} candidates={candidates} recommendation={recommendation}".format(
            **report["summary"]
        )
    )
    print(f"json={output}")
    print(f"markdown={markdown}")
    return 0


def build_report() -> dict[str, Any]:
    candidates = broker_candidates()
    decision = BrokerDecision(
        recommendation="start_with_alpaca_paper_only_after_no_order_adapter_contract",
        rationale=(
            "User chose broker comparison, not credentialed integration.",
            "Alpaca appears simplest for a future paper-first US equities API path, "
            "because official docs describe a paper-only account, separate paper keys, and a separate paper endpoint.",
            "tastytrade and TradeStation have strong sandbox/SIM separation, but introduce delayed-data, daily-reset, "
            "or API-key/account setup constraints that make them better second-phase candidates.",
            "Tradier and E*TRADE document sandbox endpoints but require brokerage/OAuth/account plumbing before safe use.",
            "IBKR is broad and powerful but has higher operational complexity and gateway/session handling; Schwab was "
            "not selected because no official public paper/sandbox evidence was verifiable from the accessed portal pages.",
        ),
        rejected_now=(
            "live order routing",
            "paper order routing",
            "reading API keys from environment",
            "adding broker SDK dependencies",
            "storing account IDs or credentials",
        ),
        next_safe_action=(
            "Keep the broker-neutral no-order adapter contract as the next implementation gate; if paper API work is "
            "later approved, prototype Alpaca paper-only first with hard-coded live-endpoint rejection tests."
        ),
    )
    return {
        "status": "ok",
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "safety": "comparison only; no broker SDKs; no credentials; no account access; no orders",
        "summary": {
            "status": "ok",
            "candidates": len(candidates),
            "recommendation": decision.recommendation,
            "live_trading_authorized": False,
            "paper_api_authorized": False,
        },
        "candidates": [asdict(candidate) for candidate in candidates],
        "decision": asdict(decision),
        "universal_preconditions": universal_preconditions(),
        "references": {
            "alpaca_trading_api": ALPACA_TRADING_DOCS,
            "alpaca_market_data": ALPACA_MARKET_DATA_DOCS,
            "alpaca_account_requirements": ALPACA_ACCOUNT_REQUIREMENTS,
            "ibkr_api_home": IBKR_API_DOCS,
            "ibkr_web_api": IBKR_WEB_API_DOCS,
            "ibkr_client_portal_v1": IBKR_CPAPI_DOCS,
            "tradier_trading": TRADIER_TRADING_DOCS,
            "tradier_endpoints": TRADIER_ENDPOINTS_DOCS,
            "tradestation_sim": TRADESTATION_SIM_DOCS,
            "tradestation_auth": TRADESTATION_AUTH_DOCS,
            "tastytrade_sandbox": TASTYTRADE_SANDBOX_DOCS,
            "etrade_order": ETRADE_ORDER_DOCS,
            "etrade_auth": ETRADE_AUTH_DOCS,
            "schwab_trader_api": SCHWAB_TRADER_API_DOCS,
            "finra_day_trading": FINRA_DAY_TRADING,
        },
        "live_trading_authorized": False,
        "paper_api_authorized": False,
    }


def broker_candidates() -> tuple[BrokerCandidate, ...]:
    return (
        BrokerCandidate(
            name="Alpaca Trading API",
            official_docs=ALPACA_TRADING_DOCS,
            account_requirement=(
                "Paper-only account can be created globally according to Alpaca docs; live brokerage "
                "eligibility depends on country/KYC and must be verified by the user."
            ),
            paper_support=(
                "Paper trading is documented as free and available to Alpaca users; paper/live use "
                "separate API environments and keys."
            ),
            live_support="US stocks/ETFs trading API exists, but live account approval is external.",
            market_data_notes=(
                "Basic plan provides limited real-time equities coverage through IEX, 30 websocket "
                "symbols, historical data since 2016, and latest-15-minute historical limitation; "
                "broader coverage requires paid plan."
            ),
            auth_boundary="Trading API uses key/secret headers; keys must stay outside this repo.",
            integration_complexity="low_to_medium",
            fit_for_this_project=(
                "Best first candidate for a future paper-only adapter if the user can create an account "
                "and accepts data-plan limits."
            ),
            required_user_checks=(
                "Confirm Alpaca account availability for user's residency/KYC.",
                "Confirm paper API access without live funding if only simulation is desired.",
                "Confirm whether IEX-only Basic data is acceptable for paper observation.",
            ),
            blockers_before_any_live_use=(
                "live account approval missing",
                "independent data replication missing",
                "kill-switch/order-reconciliation adapter missing",
            ),
        ),
        BrokerCandidate(
            name="Interactive Brokers API",
            official_docs=IBKR_API_DOCS,
            account_requirement=(
                "IBKR Web API documentation says individual Web API usage requires IBKR username/password; "
                "live or simulated paper access requires a fully open and funded live IBKR Pro account."
            ),
            paper_support=(
                "Paper account can be used with a unique paper username/password in Client Portal Gateway."
            ),
            live_support="Broad live trading/API capability after account approval and subscriptions.",
            market_data_notes=(
                "API market data requires IBKR market data subscriptions; paper data linkage must be configured."
            ),
            auth_boundary=(
                "Client Portal Gateway commonly runs on localhost with interactive login/2FA; "
                "OAuth paths exist but add operational complexity."
            ),
            integration_complexity="high",
            fit_for_this_project=(
                "Powerful later-stage choice, but not the simplest first paper adapter because gateway, "
                "session resets, account type, and data subscriptions add complexity."
            ),
            required_user_checks=(
                "Confirm IBKR Pro eligibility and account funding requirement.",
                "Confirm paper username/password and data subscription sharing.",
                "Confirm whether local gateway uptime is acceptable for cloud automation.",
            ),
            blockers_before_any_live_use=(
                "funded live account requirement unresolved",
                "gateway/session reset handling missing",
                "market-data subscription and paper sharing unverified",
            ),
        ),
        BrokerCandidate(
            name="TradeStation API",
            official_docs=TRADESTATION_SIM_DOCS,
            account_requirement=(
                "Official docs expose a v3 brokerage/market-data API and simulator/live base URLs; API-key/account "
                "setup still must be confirmed before any integration."
            ),
            paper_support=(
                "Simulator API is documented as a paper-trading environment with fake funded accounts, simulated "
                "executions, and a separate `https://sim-api.tradestation.com/v3` base URL."
            ),
            live_support="Live v3 API uses `https://api.tradestation.com/v3` after account/API authorization.",
            market_data_notes=(
                "Official rate-limit docs define separate quotas by resource category; streaming should be preferred "
                "for frequent quote/account updates."
            ),
            auth_boundary=(
                "OAuth/API-key setup is required; SIM and live base URLs must be blocked from runtime switching "
                "without an explicit future approval gate."
            ),
            integration_complexity="medium",
            fit_for_this_project=(
                "Strong second-phase sandbox/SIM candidate, especially if multi-asset support matters, but not safer "
                "than Alpaca for the first equities-only paper path because account/API-key setup is heavier."
            ),
            required_user_checks=(
                "Confirm TradeStation account/API-key eligibility.",
                "Confirm whether SIM accounts are available before live funding or only after account approval.",
                "Confirm rate-limit fit for planned polling/streaming cadence.",
            ),
            blockers_before_any_live_use=(
                "API-key/account eligibility unresolved",
                "SIM/live base URL guard missing",
                "rate-limit backoff and stream reconnect logic missing",
            ),
        ),
        BrokerCandidate(
            name="tastytrade API",
            official_docs=TASTYTRADE_SANDBOX_DOCS,
            account_requirement=(
                "Official sandbox docs require signing in with sandbox user credentials; production account/API "
                "eligibility must be separately confirmed."
            ),
            paper_support=(
                "Sandbox is documented as a controlled open-API system with separate REST and websocket hosts; "
                "trades, transactions, positions, and balances reset every 24 hours."
            ),
            live_support="Production trading exists through the tastytrade API but is out of scope for this review.",
            market_data_notes="Sandbox quotes are documented as always 15 minutes delayed.",
            auth_boundary=(
                "Sandbox credentials and production credentials must never share storage, config keys, logs, or runtime paths."
            ),
            integration_complexity="medium",
            fit_for_this_project=(
                "Good sandbox lab candidate, but daily resets and delayed quotes make it less suitable than Alpaca "
                "for continuous paper-observation history."
            ),
            required_user_checks=(
                "Confirm sandbox account creation and API terms.",
                "Confirm delayed quotes are acceptable.",
                "Confirm daily reset behavior will not invalidate observation metrics.",
            ),
            blockers_before_any_live_use=(
                "production eligibility unresolved",
                "daily-reset reconciliation not modeled",
                "delayed market-data labeling missing",
            ),
        ),
        BrokerCandidate(
            name="E*TRADE API",
            official_docs=ETRADE_ORDER_DOCS,
            account_requirement=(
                "Official docs require OAuth access tokens and account keys for account/order APIs."
            ),
            paper_support=(
                "Official docs publish sandbox URLs for accounts and orders, including preview and place-order endpoints."
            ),
            live_support="Live URLs are documented beside sandbox URLs for the same order/account resources.",
            market_data_notes=(
                "Quote docs indicate real-time market data requires a market-data agreement and OAuth; otherwise "
                "data may be delayed."
            ),
            auth_boundary=(
                "OAuth 1.0a token lifecycle and callback flow add complexity; preview IDs are required before place order."
            ),
            integration_complexity="medium_to_high",
            fit_for_this_project=(
                "Useful only after a no-order preview contract exists; sandbox support is clear but OAuth/account-key "
                "handling is heavier than Alpaca for first paper work."
            ),
            required_user_checks=(
                "Confirm developer access and sandbox account fixtures.",
                "Confirm callback/OAuth flow can be completed without storing secrets in repo.",
                "Confirm market-data agreement/delay expectations.",
            ),
            blockers_before_any_live_use=(
                "OAuth callback/token storage design missing",
                "preview-id expiry/retry behavior not modeled",
                "account-key handling not approved",
            ),
        ),
        BrokerCandidate(
            name="Charles Schwab Trader API",
            official_docs=SCHWAB_TRADER_API_DOCS,
            account_requirement=(
                "Official developer portal exists, but the accessed public portal pages did not expose crawlable details "
                "for account, paper, or sandbox requirements in this environment."
            ),
            paper_support=(
                "No official public paper/sandbox support evidence was verified during this review."
            ),
            live_support="Not evaluated beyond the official Trader API portal because paper/sandbox evidence was missing.",
            market_data_notes="Not evaluated; official public paper/sandbox source evidence was unavailable.",
            auth_boundary="OAuth/app approval details must be verified from Schwab official docs before any design work.",
            integration_complexity="unknown_high",
            fit_for_this_project=(
                "Not a safe first candidate until official paper/sandbox documentation is available and reviewed."
            ),
            required_user_checks=(
                "Confirm from Schwab official docs whether an individual paper/sandbox environment exists.",
                "Confirm account and app approval requirements.",
                "Confirm market-data and order-preview constraints.",
            ),
            blockers_before_any_live_use=(
                "official paper/sandbox support not verified",
                "official auth/app approval requirements not captured",
                "no no-order contract mapping",
            ),
        ),
        BrokerCandidate(
            name="Tradier API",
            official_docs=TRADIER_TRADING_DOCS,
            account_requirement=(
                "Trading docs require a Tradier Brokerage account, API token, and account ID."
            ),
            paper_support=(
                "Sandbox base URL supports paper trading; docs recommend testing order logic in sandbox."
            ),
            live_support="Production base URL supports live brokerage API after account/API access.",
            market_data_notes=(
                "Sandbox works with delayed market data; production can provide real-time/streaming data "
                "depending on account/data access."
            ),
            auth_boundary="Bearer token per environment; live and sandbox tokens must be separated.",
            integration_complexity="medium",
            fit_for_this_project=(
                "Good candidate if the user can open/maintain Tradier Brokerage access; sandbox separation is clear."
            ),
            required_user_checks=(
                "Confirm Tradier account availability for user's residency.",
                "Confirm sandbox token/account creation.",
                "Confirm data delay and real-time data requirements.",
            ),
            blockers_before_any_live_use=(
                "brokerage account eligibility unresolved",
                "sandbox delayed-data behavior not modeled",
                "order preview/reconciliation adapter missing",
            ),
        ),
    )


def universal_preconditions() -> tuple[str, ...]:
    return (
        "No live trading until an explicit later human approval gate is passed.",
        "Start with paper-only and preferably read-only/no-order fixtures before any API key exists.",
        "Keep live and paper credentials, base URLs, accounts, and logs separated.",
        "Block leverage, inverse products, margin, shorting, options, and crypto unless separately approved.",
        "Implement max notional, max daily loss, duplicate-order idempotency, and kill-switch before paper orders.",
        "Record request timestamp, broker response, order state, partial fill, reject, cancel, and reconciliation logs.",
        "Treat delayed or partial market data as delayed; never report it as real-time.",
        "FINRA day-trading and margin rules must be reviewed before any higher-frequency live strategy.",
    )


def write_markdown(path: Path, report: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Broker API comparison",
        "",
        "Safety: comparison only; no broker SDKs, no credentials, no account access, no orders.",
        "",
        "## Summary",
        "",
        f"- Candidates: {report['summary']['candidates']}",
        f"- Recommendation: `{report['summary']['recommendation']}`",
        f"- Paper API authorized: `{report['summary']['paper_api_authorized']}`",
        f"- Live trading authorized: `{report['summary']['live_trading_authorized']}`",
        "",
        "## Comparison",
        "",
        "| Broker | Paper support | Market data | Complexity | Fit | User checks |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for candidate in report["candidates"]:
        lines.append(
            "| {name} | {paper} | {data} | {complexity} | {fit} | {checks} |".format(
                name=candidate["name"],
                paper=candidate["paper_support"],
                data=candidate["market_data_notes"],
                complexity=candidate["integration_complexity"],
                fit=candidate["fit_for_this_project"],
                checks="; ".join(candidate["required_user_checks"]),
            )
        )
    lines.extend(
        [
            "",
            "## Decision",
            "",
            f"Recommendation: `{report['decision']['recommendation']}`",
            "",
            "Rationale:",
            *[f"- {item}" for item in report["decision"]["rationale"]],
            "",
            "Rejected now:",
            *[f"- {item}" for item in report["decision"]["rejected_now"]],
            "",
            f"Next safe action: {report['decision']['next_safe_action']}",
            "",
            "## Universal preconditions",
            "",
            *[f"- {item}" for item in report["universal_preconditions"]],
            "",
            "## References",
            "",
        ]
    )
    for label, url in report["references"].items():
        lines.append(f"- {label}: {url}")
    path.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
