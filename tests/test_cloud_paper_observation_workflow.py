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
    assert "paper_challenger_signal.py" in workflow
    assert "discord_paper_report.py" in workflow
    assert "no_order_preview_report.py" in workflow
    assert "operational_risk_gate.py" in workflow
    assert "independent_price_replication_gate.py" in workflow
    assert "sec_fundamental_feature_snapshot.py" in workflow
    assert "bls_macro_snapshot.py" in workflow
    assert "build_us_liquid_universe.py" in workflow
    assert "market_universe_candidate_scan.py" in workflow
    assert "adaptive_allocation_search.py" in workflow
    assert "live_readiness_gate.py" in workflow
    assert "broker_execution_preflight_report.py" in workflow
    assert "no_order_gate_status.py" in workflow
    assert "paper-observation-state" in workflow
    assert "STRATEGY_WEIGHTS" in workflow
    assert "market-universe-scan-latest" in workflow
    assert "adaptive-allocation-search-latest" in workflow
    assert "us_dynamic_liquid_watchlist.txt" in workflow
    assert "us-dynamic-liquid-universe-latest" in workflow
    assert "--symbols-file data/universe/us_dynamic_liquid_watchlist.txt" in workflow
    assert "--min-history-rows 1100" in workflow
    assert "--min-selected-symbols 10" in workflow
    assert "no-order-preview-latest" in workflow
    assert "paper-challenger-selection-latest" in workflow
    assert "paper-challenger-signal-latest" in workflow
    assert 'if [[ -f reports/paper-challenger-signal-latest.json ]]' in workflow
    assert "market_scan_has_no_safe_passed_challenger" in workflow
    assert "paper-challenger-observation-log.jsonl" in workflow
    assert "paper-challenger-observation-summary-latest" in workflow
    assert "operational-risk-gate-latest" in workflow
    assert "independent-price-replication-latest" in workflow
    assert "no-order-gate-status-latest" in workflow
    assert "broker-execution-preflight-latest" in workflow
    assert "discord-paper-report-latest" in workflow
    assert "retention-days: 1" in workflow
    assert 'steps.gate_status.outputs.mode }}" == "action-needed"' in workflow
    assert "DISCORD_WEBHOOK_URL: ${{ secrets.DISCORD_WEBHOOK_URL }}" in workflow
    assert "reports/intraday-no-order-log.jsonl" in workflow
    assert "sec-fundamental-feature-snapshot-latest" in workflow
    assert "bls-macro-snapshot-latest" in workflow
    assert ".omx/features/sec-fundamental-snapshot.csv" in workflow
    assert 'add -f reports .omx/reports .omx/features data/universe' in workflow
    assert "broker_api_key" not in workflow.lower()
    assert "broker_order_id" not in workflow.lower()
    assert "ALPHA_VANTAGE_API_KEY: ${{ secrets.ALPHA_VANTAGE_API_KEY }}" in workflow
    assert "BROKER" not in workflow


def test_intraday_no_order_workflow_runs_five_minute_public_guard() -> None:
    workflow = (
        PROJECT_ROOT / ".github" / "workflows" / "intraday-no-order-monitor.yml"
    ).read_text(encoding="utf-8")

    assert '*/5 13-21 * * 1-5' in workflow
    assert "intraday_no_order_monitor.py" in workflow
    assert "--max-symbols 10" in workflow
    assert "--max-log-entries 1000" in workflow
    assert "--send-discord" not in workflow
    assert "retention-days: 1" in workflow
    assert "github.repository_visibility == 'public'" in workflow
    assert "cancel-in-progress: true" in workflow
    assert "FINNHUB_API_KEY: ${{ secrets.FINNHUB_API_KEY }}" in workflow
    assert "intraday-no-order-state" in workflow
    assert "broker" not in workflow.lower()
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
    assert "sec-fundamental-snapshot.csv" in text
    assert "Alpha Vantage" in text


def test_market_wide_plan_documents_buy_sell_and_no_orders() -> None:
    text = (PROJECT_ROOT / "docs" / "market-wide-paper-trading-plan.md").read_text(encoding="utf-8")

    assert "would_buy" in text
    assert "would_sell" in text
    assert "order_created: false" in text
    assert "no broker" in text
    assert "Non-leveraged" in text or "non-leveraged" in text
