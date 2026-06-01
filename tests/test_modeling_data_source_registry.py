"""Tests for no-order modeling data-source registry."""

from __future__ import annotations

import json

from scripts.modeling_data_source_registry import build_registry, main

from conftest import PROJECT_ROOT


def test_registry_preserves_no_order_and_defers_fine_tuning() -> None:
    registry = build_registry()

    assert registry["live_trading_authorized"] is False
    assert "no broker" in registry["safety"]
    assert registry["summary"]["fine_tuning_status"] == (
        "defer_until_labeled_decision_outcome_dataset_exists"
    )
    assert registry["modeling_stages"][0]["stage"] == "S1_feature_registry_and_labels"
    assert "fine-tuning before" in registry["modeling_stages"][0]["rejected_shortcut"]


def test_registry_covers_price_fundamental_macro_news_and_portfolio_features() -> None:
    registry = build_registry()

    categories = {source["category"] for source in registry["data_sources"]}
    names = {source["name"] for source in registry["data_sources"]}
    assert "historical_price_ohlcv" in categories
    assert "independent_historical_price_ohlcv" in categories
    assert "fundamentals_and_filings" in categories
    assert "korea_fundamentals_and_filings" in categories
    assert "macro_regime" in categories
    assert "korea_macro_regime" in categories
    assert "global_news_attention" in categories
    assert "price_fundamental_news_sentiment" in categories
    assert "portfolio_risk" in {group["name"] for group in registry["feature_groups"]}
    assert "Nasdaq Trader symbol directories" in names
    assert "OpenDART" in names
    assert "GDELT DOC API" in names


def test_registry_references_official_source_docs() -> None:
    refs = build_registry()["primary_references"]

    assert refs["sec_edgar"].startswith("https://www.sec.gov/")
    assert refs["fred"].startswith("https://fred.stlouisfed.org/")
    assert refs["alpaca_market_data"].startswith("https://docs.alpaca.markets/")
    assert refs["polygon_stocks"].startswith("https://polygon.io/")
    assert refs["finra_day_trading"].startswith("https://www.finra.org/")
    assert refs["nasdaq_trader_symbol_directory"].startswith("https://www.nasdaqtrader.com/")
    assert refs["opendart"].startswith("https://opendart.fss.or.kr/")
    assert refs["bls_api"].startswith("https://www.bls.gov/")


def test_registry_script_writes_json_and_markdown(tmp_path) -> None:
    output = tmp_path / "registry.json"
    markdown = tmp_path / "registry.md"

    assert main(["--output", str(output), "--markdown", str(markdown)]) == 0

    payload = json.loads(output.read_text(encoding="utf-8"))
    text = markdown.read_text(encoding="utf-8")
    assert payload["summary"]["sources"] >= 5
    assert "No-lookahead controls" in text
    assert "no broker" in text


def test_training_roadmap_documents_point_in_time_labels_and_no_live_orders() -> None:
    text = (PROJECT_ROOT / "docs" / "training-data-and-modeling-roadmap.md").read_text(
        encoding="utf-8"
    )

    assert "point-in-time" in text
    assert "Do **not** fine-tune first" in text
    assert "would_buy" in text
    assert "would_sell" in text
    assert "live orders" in text
    assert "Label" in text or "Labels" in text
