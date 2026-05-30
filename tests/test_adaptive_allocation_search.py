"""Safety and deterministic checks for adaptive allocation search."""

from __future__ import annotations

import pytest
from scripts.adaptive_allocation_search import AdaptivePolicy, build_policy_grid, target_weight


def test_policy_grid_keeps_risk_off_below_risk_on() -> None:
    policies = build_policy_grid()

    assert policies
    assert all(policy.risk_off_qqq_weight < policy.risk_on_qqq_weight for policy in policies)
    assert all(0 <= policy.risk_off_qqq_weight <= 1 for policy in policies)
    assert all(0 <= policy.risk_on_qqq_weight <= 1 for policy in policies)


def test_target_weight_switches_between_policy_actions() -> None:
    policy = AdaptivePolicy(
        name="test",
        sma_window=3,
        momentum_window=2,
        momentum_threshold=0.0,
        risk_on_qqq_weight=0.75,
        risk_off_qqq_weight=0.20,
        rebalance_days=21,
    )

    assert target_weight(policy, [10, 11, 12, 13], 3, 3) == pytest.approx(0.20)
    assert target_weight(policy, [10, 11, 12, 13, 14], 4, 3) == pytest.approx(0.75)
    assert target_weight(policy, [14, 13, 12, 11, 10], 4, 3) == pytest.approx(0.20)
