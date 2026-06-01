"""Document the data/modeling plan for no-order auto-trading research.

This script is intentionally a registry generator, not a downloader. It records
which public/professional data sources should feed future modeling, how each data
type should be used, and which leakage/risk controls are mandatory before any
paper or live gate. It never connects to brokers, reads credentials, or places
orders.
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
class DataSource:
    name: str
    category: str
    url: str
    collection_status: str
    requires_api_key: bool
    current_repo_use: str
    modeling_use: tuple[str, ...]
    leakage_controls: tuple[str, ...]
    limitations: tuple[str, ...]


@dataclass(frozen=True)
class FeatureGroup:
    name: str
    inputs: tuple[str, ...]
    features: tuple[str, ...]
    decision_use: str
    validation_controls: tuple[str, ...]


@dataclass(frozen=True)
class ModelingStage:
    stage: str
    objective: str
    recommended_methods: tuple[str, ...]
    promotion_gate: tuple[str, ...]
    rejected_shortcut: str


SEC_EDGAR_DOC_URL = "https://www.sec.gov/edgar/sec-api-documentation"
SEC_FAIR_ACCESS_URL = (
    "https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data"
)
FRED_DOC_URL = "https://fred.stlouisfed.org/docs/api/fred/"
ALPHA_VANTAGE_DOC_URL = "https://www.alphavantage.co/documentation/"
ALPACA_MARKET_DATA_DOC_URL = "https://docs.alpaca.markets/us/docs/about-market-data-api"
POLYGON_STOCKS_DOC_URL = "https://polygon.io/docs/rest/stocks/overview/"
NASDAQ_TRADER_SYMBOL_DIR_URL = "https://www.nasdaqtrader.com/trader.aspx?id=symboldirdefs"
STOOQ_HISTORICAL_URL = "https://stooq.com/db/h/"
GDELT_DOC_API_URL = "https://blog.gdeltproject.org/gdelt-doc-2-0-api-debuts/"
OPENDART_API_URL = "https://opendart.fss.or.kr/guide/main.do"
KRX_DATA_URL = "https://data.krx.co.kr/"
BLS_API_URL = "https://www.bls.gov/developers/"
BANK_OF_KOREA_ECOS_URL = "https://ecos.bok.or.kr/api/"
FINRA_DAY_TRADING_URL = (
    "https://www.finra.org/investors/investing/investment-products/stocks/day-trading"
)
CFA_REASONABLE_BASIS_URL = (
    "https://www.cfainstitute.org/standards/professionals/code-ethics-standards/"
    "standards-of-practice-v-a"
)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Write no-order modeling data-source registry.")
    parser.add_argument("--output", default=".omx/reports/modeling-data-source-registry.json")
    parser.add_argument("--markdown", default=".omx/reports/modeling-data-source-registry.md")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    registry = build_registry()
    output = Path(args.output)
    markdown = Path(args.markdown)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(registry, indent=2, ensure_ascii=False), encoding="utf-8")
    write_markdown(markdown, registry)
    print(
        "modeling registry status={status} sources={sources} stages={stages}".format(
            **registry["summary"]
        )
    )
    print(f"json={output}")
    print(f"markdown={markdown}")
    return 0


def build_registry() -> dict[str, Any]:
    sources = data_sources()
    feature_groups = feature_groups_from_sources()
    stages = modeling_stages()
    return {
        "status": "ok",
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "safety": (
            "research and paper-observation planning only; no broker, no credentials, "
            "no orders, no personalized investment advice"
        ),
        "summary": {
            "status": "ok",
            "sources": len(sources),
            "feature_groups": len(feature_groups),
            "stages": len(stages),
            "recommended_next_stage": stages[0].stage,
            "fine_tuning_status": "defer_until_labeled_decision_outcome_dataset_exists",
            "live_trading_authorized": False,
        },
        "data_sources": [asdict(source) for source in sources],
        "feature_groups": [asdict(group) for group in feature_groups],
        "modeling_stages": [asdict(stage) for stage in stages],
        "global_controls": {
            "no_lookahead": [
                (
                    "Every feature must use publication/filing/release timestamp "
                    "<= decision timestamp."
                ),
                "SEC fundamentals must use filed date, not fiscal-period end date alone.",
                (
                    "Macro series must use real-time/vintage-aware values "
                    "when the source supports them."
                ),
                "News features must use article published time and deduplicate syndicated copies.",
            ],
            "risk_controls": [
                "long-only cash-account assumption",
                "no leverage, inverse products, margin, shorting, derivatives, or options",
                "position caps, sector caps, drawdown stops, and kill-switch before broker sandbox",
                "transaction cost, slippage, delayed-data, and missing-data penalties",
            ],
            "evaluation_controls": [
                "chronological train/validation/test split",
                "walk-forward validation",
                "symbol-level and regime-level holdouts",
                "benchmark against simple baselines before accepting complex models",
                "paper observation before any promotion",
            ],
        },
        "primary_references": {
            "sec_edgar": SEC_EDGAR_DOC_URL,
            "sec_fair_access": SEC_FAIR_ACCESS_URL,
            "fred": FRED_DOC_URL,
            "alpha_vantage": ALPHA_VANTAGE_DOC_URL,
            "alpaca_market_data": ALPACA_MARKET_DATA_DOC_URL,
            "polygon_stocks": POLYGON_STOCKS_DOC_URL,
            "nasdaq_trader_symbol_directory": NASDAQ_TRADER_SYMBOL_DIR_URL,
            "stooq_historical_data": STOOQ_HISTORICAL_URL,
            "gdelt_doc_api": GDELT_DOC_API_URL,
            "opendart": OPENDART_API_URL,
            "krx_data": KRX_DATA_URL,
            "bls_api": BLS_API_URL,
            "bank_of_korea_ecos": BANK_OF_KOREA_ECOS_URL,
            "finra_day_trading": FINRA_DAY_TRADING_URL,
            "cfa_reasonable_basis": CFA_REASONABLE_BASIS_URL,
        },
        "live_trading_authorized": False,
    }


def data_sources() -> tuple[DataSource, ...]:
    return (
        DataSource(
            name="Nasdaq Trader symbol directories",
            category="us_symbol_universe",
            url=NASDAQ_TRADER_SYMBOL_DIR_URL,
            collection_status="used_for_broad_us_symbol_universe",
            requires_api_key=False,
            current_repo_use="official public symbol directory refresh for listed US candidates",
            modeling_use=(
                "expand beyond the seed watchlist into a broad US universe",
                "separate listed symbols, ETFs, test issues, and exchange metadata",
            ),
            leakage_controls=(
                "treat symbol membership as observed at refresh time",
                "do not infer historical membership without dated directory snapshots",
            ),
            limitations=(
                "not survivorship-bias-free for historical backtests unless snapshots are archived",
                "does not provide prices, fundamentals, sectors, or liquidity metrics",
            ),
        ),
        DataSource(
            name="Stooq historical data",
            category="independent_historical_price_ohlcv",
            url=STOOQ_HISTORICAL_URL,
            collection_status="candidate_no_key_independent_price_replication",
            requires_api_key=False,
            current_repo_use="not yet collected",
            modeling_use=(
                "independent daily OHLCV replication against Yahoo-derived caches",
                "sanity-check stale, missing, split-adjusted, or vendor-revised bars",
            ),
            leakage_controls=(
                "store ingestion timestamp and source URL for every cache refresh",
                "never overwrite historical raw cache without preserving prior snapshot metadata",
            ),
            limitations=(
                "coverage and adjustment methodology must be verified per symbol",
                "terms/robots and rate behavior must be respected before bulk download",
            ),
        ),
        DataSource(
            name="Yahoo Finance chart endpoint cache",
            category="historical_price_ohlcv",
            url="https://query1.finance.yahoo.com/v8/finance/chart/{symbol}",
            collection_status="already_used_for_research_cache",
            requires_api_key=False,
            current_repo_use="daily OHLCV cache for backtests and paper observation",
            modeling_use=(
                "daily returns, volatility, trend, drawdown, relative strength",
                "baseline labels such as forward 1/5/20-day excess return",
            ),
            leakage_controls=(
                "use only bars with timestamp <= decision time",
                "store raw cache path and as-of date in each report",
            ),
            limitations=(
                "unofficial endpoint; may revise, throttle, or fail",
                "not a sufficient independent data source for live readiness",
            ),
        ),
        DataSource(
            name="SEC EDGAR APIs",
            category="fundamentals_and_filings",
            url=SEC_EDGAR_DOC_URL,
            collection_status="partially_used_for_companyfacts_and_submissions",
            requires_api_key=False,
            current_repo_use="companyfacts, filing recency, and 8-K event-risk gates",
            modeling_use=(
                "revenue growth, profitability, cash-flow, debt/liquidity flags",
                "filing-event indicators around 8-K, 10-Q, 10-K, and amendments",
            ),
            leakage_controls=(
                "filter by SEC filed date <= market decision date",
                "preserve CIK and source filing date for every feature",
            ),
            limitations=(
                "company fundamentals do not apply to ETFs",
                "taxonomy differences require missing-data handling",
            ),
        ),
        DataSource(
            name="OpenDART",
            category="korea_fundamentals_and_filings",
            url=OPENDART_API_URL,
            collection_status="candidate_free_key_korea_filings",
            requires_api_key=True,
            current_repo_use="not yet collected",
            modeling_use=(
                "Korean company filings, financial statements, and disclosure events",
                "domestic equity fundamental and event-risk features",
            ),
            leakage_controls=(
                "filter every feature by receipt/disclosure timestamp <= decision timestamp",
                "preserve corp code, report code, and receipt number for audit",
            ),
            limitations=(
                "free API key setup is required",
                "Korean taxonomy and report timing differ from SEC data",
            ),
        ),
        DataSource(
            name="KRX data portal",
            category="korea_market_reference_data",
            url=KRX_DATA_URL,
            collection_status="candidate_manual_or_automated_korea_market_data",
            requires_api_key=False,
            current_repo_use="not yet collected",
            modeling_use=(
                "Korean listed symbol universe, market classification, and reference data",
                "domestic liquidity filters before any Korean paper strategy",
            ),
            leakage_controls=(
                "archive dated downloads and do not backfill future listing state",
                "separate listing metadata from historical tradability assumptions",
            ),
            limitations=(
                "automated access behavior may require endpoint-specific validation",
                "not a replacement for licensed real-time KRX data",
            ),
        ),
        DataSource(
            name="FRED/ALFRED API",
            category="macro_regime",
            url=FRED_DOC_URL,
            collection_status="planned_api_key_optional",
            requires_api_key=True,
            current_repo_use="not yet collected; price-based macro proxies used instead",
            modeling_use=(
                "rates, yield curve, inflation, labor, credit, dollar/liquidity regime",
                "market-regime features and macro stress filters",
            ),
            leakage_controls=(
                "use release/vintage dates rather than revised final values when available",
                "lag monthly/weekly series until public release time is known",
            ),
            limitations=(
                "API key/login required for normal use",
                "macro data frequency is lower than intraday equity decisions",
            ),
        ),
        DataSource(
            name="GDELT DOC API",
            category="global_news_attention",
            url=GDELT_DOC_API_URL,
            collection_status="candidate_no_key_news_attention_source",
            requires_api_key=False,
            current_repo_use="not yet collected",
            modeling_use=(
                "global article-count and event-attention features by company/query",
                "news-volume shock flags before adding paid or keyed news sentiment",
            ),
            leakage_controls=(
                "use article publication datetime and query datetime separately",
                "deduplicate syndicated or near-identical article URLs before scoring",
            ),
            limitations=(
                "entity matching is noisy and needs ticker/company-name disambiguation",
                "article tone/volume is a proxy and must be validated out-of-sample",
            ),
        ),
        DataSource(
            name="BLS Public Data API",
            category="labor_macro_regime",
            url=BLS_API_URL,
            collection_status="candidate_no_key_or_registered_key_macro_source",
            requires_api_key=False,
            current_repo_use="not yet collected",
            modeling_use=(
                "labor, CPI/PPI, employment, and wage regime features",
                "macro stress filters alongside FRED/ALFRED",
            ),
            leakage_controls=(
                "respect survey release dates and do not use later revisions early",
                "align monthly releases to the first tradable decision after publication",
            ),
            limitations=(
                "higher limits may require registration key",
                "macro frequency is low relative to daily/intraday trading",
            ),
        ),
        DataSource(
            name="Bank of Korea ECOS API",
            category="korea_macro_regime",
            url=BANK_OF_KOREA_ECOS_URL,
            collection_status="candidate_free_key_korea_macro_source",
            requires_api_key=True,
            current_repo_use="not yet collected",
            modeling_use=(
                "Korean rates, FX, money, and macro regime features",
                "domestic equity risk throttle and Korea-US macro comparison",
            ),
            leakage_controls=(
                "use publication/release date and preserve vintage where available",
                "lag low-frequency values until public release is known",
            ),
            limitations=(
                "API key setup is required",
                "series discovery and Korean metadata mapping must be maintained",
            ),
        ),
        DataSource(
            name="Alpha Vantage",
            category="price_fundamental_news_sentiment",
            url=ALPHA_VANTAGE_DOC_URL,
            collection_status="candidate_paid_or_keyed_source",
            requires_api_key=True,
            current_repo_use="not yet collected",
            modeling_use=(
                "independent OHLCV replication",
                "historical/live market news and sentiment features",
                "fundamental and economic indicator cross-checks",
            ),
            leakage_controls=(
                "record query timestamp, article publication time, and source URL",
                "cap per-ticker article influence to avoid syndicated-news duplication",
            ),
            limitations=(
                "API key, rate limits, and plan coverage constraints",
                "sentiment scores must be validated, not trusted directly",
            ),
        ),
        DataSource(
            name="Alpaca Market Data API",
            category="realtime_and_historical_market_data",
            url=ALPACA_MARKET_DATA_DOC_URL,
            collection_status="future_intraday_or_broker_sandbox_candidate",
            requires_api_key=True,
            current_repo_use="not connected by design",
            modeling_use=(
                "intraday bars/trades/quotes for no-order observation",
                "paper-vs-live execution readiness only after separate approval",
            ),
            leakage_controls=(
                "separate market-data-only credentials from any trading credentials",
                "fail closed on delayed/stale data or market-hours ambiguity",
            ),
            limitations=(
                "requires account/API setup and may have data-plan limits",
                "paper fills still do not prove live fill quality",
            ),
        ),
        DataSource(
            name="Polygon Stocks API",
            category="realtime_historical_news_reference_data",
            url=POLYGON_STOCKS_DOC_URL,
            collection_status="candidate_independent_market_data_source",
            requires_api_key=True,
            current_repo_use="not yet collected",
            modeling_use=(
                "independent price replication, corporate/reference data, and news",
                "intraday no-order observer if plan supports required timeliness",
            ),
            leakage_controls=(
                "store exchange timestamp and ingestion timestamp separately",
                "treat delayed feeds as delayed; never backfill into earlier decisions",
            ),
            limitations=(
                "API key and subscription plan determine coverage/timeliness",
                "cost and licensing review required before heavy collection",
            ),
        ),
    )


def feature_groups_from_sources() -> tuple[FeatureGroup, ...]:
    return (
        FeatureGroup(
            name="price_action",
            inputs=("daily/intraday OHLCV",),
            features=(
                "returns_1d_5d_20d",
                "realized_volatility",
                "drawdown_from_recent_high",
                "relative_strength_vs_SPY_QQQ_DIA",
                "volume_zscore",
            ),
            decision_use="trend, risk, and mean-reversion context",
            validation_controls=("walk-forward windows", "transaction-cost sensitivity"),
        ),
        FeatureGroup(
            name="fundamental_quality",
            inputs=("SEC companyfacts", "SEC submissions"),
            features=(
                "revenue_growth_yoy",
                "net_income_positive",
                "operating_cash_flow_positive",
                "debt_to_equity",
                "current_ratio",
                "recent_8k_count_90d",
            ),
            decision_use="avoid weak balance-sheet or event-risk names despite price momentum",
            validation_controls=("filed-date as-of filtering", "missing-fundamental review state"),
        ),
        FeatureGroup(
            name="macro_regime",
            inputs=("FRED/ALFRED", "bond/gold/sector ETF proxies"),
            features=(
                "yield_curve_slope",
                "rates_change",
                "inflation_trend",
                "credit_stress_proxy",
                "defensive_asset_momentum",
            ),
            decision_use=(
                "change exposure by regime rather than fitting one static market condition"
            ),
            validation_controls=("vintage-aware macro values", "regime holdout tests"),
        ),
        FeatureGroup(
            name="news_and_events",
            inputs=("news/sentiment APIs", "SEC filing events", "earnings calendar"),
            features=(
                "article_count_by_ticker",
                "negative_event_flag",
                "earnings_window_flag",
                "filing_amendment_flag",
                "sentiment_delta_if_validated",
            ),
            decision_use="reduce position size or require confirmation around event shocks",
            validation_controls=(
                "publication-time as-of filtering",
                "deduplication",
                "source reliability log",
            ),
        ),
        FeatureGroup(
            name="portfolio_risk",
            inputs=("positions", "target weights", "market data"),
            features=(
                "weight_drift",
                "position_concentration",
                "sector_concentration",
                "paper_equity_drawdown",
                "liquidity_notional_ratio",
            ),
            decision_use="convert model scores into buy/sell/hold with caps and kill-switches",
            validation_controls=(
                "paper-only intent logs",
                "no-order invariant",
                "daily risk summary",
            ),
        ),
    )


def modeling_stages() -> tuple[ModelingStage, ...]:
    return (
        ModelingStage(
            stage="S1_feature_registry_and_labels",
            objective=(
                "Build a point-in-time dataset where every row is a decision timestamp, "
                "symbol, features, and forward outcome label."
            ),
            recommended_methods=(
                "deterministic feature engineering",
                "forward excess-return labels",
                "buy/sell/hold label generation from future windows for research only",
            ),
            promotion_gate=(
                "dataset has no future-dated features",
                "source coverage and missingness are reported",
                "baselines can reproduce current paper metrics",
            ),
            rejected_shortcut="fine-tuning before a labeled point-in-time dataset exists",
        ),
        ModelingStage(
            stage="S2_interpretable_baselines",
            objective=(
                "Benchmark simple rules and transparent statistical models before complex AI."
            ),
            recommended_methods=("scorecard", "logistic regression", "regularized linear models"),
            promotion_gate=(
                "beats cash/equal-weight/simple momentum baselines after costs",
                "stable across walk-forward/regime holdouts",
                "drawdown and turnover stay within limits",
            ),
            rejected_shortcut="optimizing one top backtest curve without regime holdouts",
        ),
        ModelingStage(
            stage="S3_tree_models_if_baselines_pass",
            objective=(
                "Use non-linear tabular models only after baselines define a credible benchmark."
            ),
            recommended_methods=(
                "random forest",
                "gradient boosted trees",
                "calibrated probability model",
            ),
            promotion_gate=(
                "out-of-sample probability calibration",
                "feature-importance sanity checks",
                "paper-observation score drift monitoring",
            ),
            rejected_shortcut="black-box model with no feature audit or calibration",
        ),
        ModelingStage(
            stage="S4_llm_event_assistant_not_order_engine",
            objective=(
                "Use LLMs to summarize filings/news and extract risk flags, "
                "not to directly submit trades."
            ),
            recommended_methods=(
                "retrieval summarization",
                "structured event extraction",
                "reason-code generation",
            ),
            promotion_gate=(
                "summaries cite source timestamps",
                "extracted flags improve validation metrics",
                "human-readable reasons match deterministic features",
            ),
            rejected_shortcut="LLM directly decides buy/sell without auditable features",
        ),
        ModelingStage(
            stage="S5_fine_tuning_only_after_dataset_maturity",
            objective=(
                "Consider fine-tuning only when many labeled decisions and audited outcomes exist."
            ),
            recommended_methods=(
                "supervised fine-tune for event classification",
                "not portfolio action routing",
            ),
            promotion_gate=(
                "large labeled corpus across regimes",
                "clear uplift over retrieval + baseline model",
                "strict train/test time split and leakage audit",
            ),
            rejected_shortcut="fine-tuning on unlabeled articles or hindsight explanations",
        ),
    )


def write_markdown(path: Path, registry: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Modeling data-source registry",
        "",
        "Safety: research/paper planning only; no broker, no credentials, no orders, no advice.",
        "",
        "## Summary",
        "",
        f"- Sources: {registry['summary']['sources']}",
        f"- Feature groups: {registry['summary']['feature_groups']}",
        f"- Modeling stages: {registry['summary']['stages']}",
        f"- Recommended next stage: `{registry['summary']['recommended_next_stage']}`",
        f"- Fine-tuning: `{registry['summary']['fine_tuning_status']}`",
        f"- Live trading authorized: `{registry['summary']['live_trading_authorized']}`",
        "",
        "## Data sources",
        "",
        "| Source | Category | Status | API key | Current use | Modeling use |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for source in registry["data_sources"]:
        lines.append(
            "| {name} | {category} | {status} | {key} | {current} | {modeling} |".format(
                name=source["name"],
                category=source["category"],
                status=source["collection_status"],
                key=source["requires_api_key"],
                current=source["current_repo_use"],
                modeling="; ".join(source["modeling_use"]),
            )
        )
    lines.extend(["", "## Modeling stages", ""])
    for stage in registry["modeling_stages"]:
        lines.extend(
            [
                f"### {stage['stage']}",
                "",
                stage["objective"],
                "",
                "Promotion gate:",
                *[f"- {item}" for item in stage["promotion_gate"]],
                f"- Rejected shortcut: {stage['rejected_shortcut']}",
                "",
            ]
        )
    lines.extend(
        [
            "## Global controls",
            "",
            "No-lookahead controls:",
            *[f"- {item}" for item in registry["global_controls"]["no_lookahead"]],
            "",
            "Risk controls:",
            *[f"- {item}" for item in registry["global_controls"]["risk_controls"]],
            "",
            "Evaluation controls:",
            *[f"- {item}" for item in registry["global_controls"]["evaluation_controls"]],
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
