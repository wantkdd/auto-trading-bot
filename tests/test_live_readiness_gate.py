"""Tests for live-readiness blocker aggregation."""

from __future__ import annotations

from scripts.live_readiness_gate import candidate_readiness_blockers, paper_signal_blockers


def test_candidate_readiness_blocks_leverage_and_concentration() -> None:
    top = {
        "name": "bad",
        "symbols": ["TQQQ", "GLD"],
        "weights": [0.8, 0.2],
        "base_worst_mdd": -0.10,
        "recent_regime_status": "pass",
    }

    blockers = candidate_readiness_blockers(
        [top], top, min_passing_candidates=3, max_single_asset_weight=0.75
    )

    assert "too_few_passing_candidates_for_redundancy" in blockers
    assert "leveraged_or_inverse_symbol_present" in blockers
    assert "single_asset_concentration_above_limit" in blockers


def test_paper_signal_must_match_top_candidate_and_safety_boundary() -> None:
    top = {"symbols": ["AAPL", "GLD"], "weights": [0.3, 0.7]}
    signal = {
        "target_weights": {"AAPL": 0.3, "GLD": 0.7},
        "warnings": ["This is a dry-run target allocation only; do not place orders."],
        "safety": "dry-run target weights only; no orders; no broker; no investment advice",
    }

    signal["as_of_date"] = "2026-05-28"
    assert paper_signal_blockers(top, signal, expected_as_of="2026-05-28") == []


def test_paper_signal_blocks_mismatched_strategy() -> None:
    top = {"symbols": ["AAPL", "GLD"], "weights": [0.3, 0.7]}
    signal = {
        "target_weights": {"QQQ": 0.36, "GLD": 0.64},
        "warnings": [],
        "safety": "",
    }

    blockers = paper_signal_blockers(top, signal)

    assert "paper_signal_does_not_match_top_candidate" in blockers
    assert "paper_signal_missing_no_order_warning" in blockers
    assert "paper_signal_safety_boundary_missing" in blockers


def test_paper_signal_blocks_as_of_mismatch() -> None:
    top = {"symbols": ["AAPL", "GLD"], "weights": [0.3, 0.7]}
    signal = {
        "as_of_date": "2026-05-29",
        "target_weights": {"AAPL": 0.3, "GLD": 0.7},
        "warnings": ["This is a dry-run target allocation only; do not place orders."],
        "safety": "dry-run target weights only; no orders; no broker; no investment advice",
    }

    assert paper_signal_blockers(top, signal, expected_as_of="2026-05-28") == [
        "paper_signal_as_of_date_mismatch"
    ]
