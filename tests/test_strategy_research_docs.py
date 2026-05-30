"""Research-loop documentation safety checks."""

from __future__ import annotations

import json

from conftest import PROJECT_ROOT


def test_strategy_research_loop_preserves_safety_boundary() -> None:
    text = (PROJECT_ROOT / "docs" / "strategy-research-loop.md").read_text(encoding="utf-8")

    assert "offline research simulator" in text
    assert "No result" in text
    assert "authorizes live trading" in text
    assert "explicit human" in text
    assert "approval" in text
    assert "SEC fundamentals" in text
    assert "recent-regime validation" in text
    assert "no leverage" in text
    assert "no live-trading authorization" in text


def test_candidate_registry_keeps_candidate_at_research_level() -> None:
    registry_path = PROJECT_ROOT / ".omx" / "research" / "strategy-candidate-registry.json"
    if not registry_path.exists():
        return
    registry = json.loads(registry_path.read_text(encoding="utf-8"))

    candidate = registry["candidates"][0]
    assert candidate["optimizer_status"] == "pass"
    assert candidate["deep_analysis_status"] == "review"
    assert candidate["promotion_level"] == "paper_trading_research_candidate_only"
