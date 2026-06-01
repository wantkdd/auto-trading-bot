"""Static checks for cloud paper-observation automation."""

from __future__ import annotations

from conftest import PROJECT_ROOT


def test_github_actions_paper_observation_workflow_preserves_safety_boundary() -> None:
    workflow = (PROJECT_ROOT / ".github" / "workflows" / "paper-observation.yml").read_text(
        encoding="utf-8"
    )

    assert "30 2 * * 2-6" in workflow
    assert "workflow_dispatch" in workflow
    assert "paper_observation_log.py" in workflow
    assert "no_order_preview_report.py" in workflow
    assert "operational_risk_gate.py" in workflow
    assert "independent_price_replication_gate.py" in workflow
    assert "sec_fundamental_feature_snapshot.py" in workflow
    assert "bls_macro_snapshot.py" in workflow
    assert "market_universe_candidate_scan.py" in workflow
    assert "live_readiness_gate.py" in workflow
    assert "paper-observation-state" in workflow
    assert "STRATEGY_WEIGHTS" in workflow
    assert "market-universe-scan-latest" in workflow
    assert "no-order-preview-latest" in workflow
    assert "operational-risk-gate-latest" in workflow
    assert "independent-price-replication-latest" in workflow
    assert "sec-fundamental-feature-snapshot-latest" in workflow
    assert "bls-macro-snapshot-latest" in workflow
    assert "broker" not in workflow.lower()
    assert "ALPHA_VANTAGE_API_KEY: ${{ secrets.ALPHA_VANTAGE_API_KEY }}" in workflow
    assert "BROKER" not in workflow


def test_cloud_observation_docs_explain_macbook_not_required_and_no_orders() -> None:
    text = (PROJECT_ROOT / "docs" / "cloud-paper-observation.md").read_text(encoding="utf-8")

    assert "MacBook can be off" in text
    assert "no broker" in text
    assert "no orders" in text
    assert "paper-observation-state" in text
    assert "not live trading" in text
    assert "market-universe-scan-latest" in text
    assert "no-order-preview-latest" in text
    assert "operational-risk-gate-latest" in text
    assert "manual kill-switch" in text
    assert "independent-price-replication-latest" in text
    assert "Alpha Vantage" in text


def test_market_wide_plan_documents_buy_sell_and_no_orders() -> None:
    text = (PROJECT_ROOT / "docs" / "market-wide-paper-trading-plan.md").read_text(encoding="utf-8")

    assert "would_buy" in text
    assert "would_sell" in text
    assert "order_created: false" in text
    assert "no broker" in text
    assert "Non-leveraged" in text or "non-leveraged" in text
