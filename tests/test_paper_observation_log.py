"""Tests for paper observation logging."""

from __future__ import annotations

import pytest
from scripts.paper_observation_log import (
    append_observation,
    build_observation,
    normalized_weights,
    weighted_return,
)


def signal(as_of: str, aapl_close: float, gld_close: float) -> dict[str, object]:
    return {
        "as_of_date": as_of,
        "strategy": "AAPL_0.3_GLD_0.7",
        "target_weights": {"AAPL": 0.3, "GLD": 0.7},
        "source_bars": {
            "AAPL": {"close": aapl_close, "volume": 100},
            "GLD": {"close": gld_close, "volume": 100},
        },
        "warnings": ["do not place orders"],
    }


def test_first_observation_initializes_virtual_equity() -> None:
    observation = build_observation(signal("2026-05-28", 100.0, 200.0), [], 10_000.0)

    assert observation["virtual_equity"] == 10_000.0
    assert observation["daily_return"] == 0.0
    assert observation["safety"].startswith("paper observation only")


def test_weighted_return_uses_previous_weights_and_prices() -> None:
    previous = build_observation(signal("2026-05-28", 100.0, 200.0), [], 10_000.0)

    assert weighted_return(previous, {"AAPL": 110.0, "GLD": 210.0}) == pytest.approx(
        0.3 * 0.10 + 0.7 * 0.05
    )


def test_append_observation_is_idempotent_for_same_date(tmp_path) -> None:
    log_path = tmp_path / "paper.jsonl"

    first = append_observation(
        signal=signal("2026-05-28", 100.0, 200.0),
        log_path=log_path,
        initial_equity=10_000.0,
        required_days=30,
        early_checkpoint_days=5,
    )
    second = append_observation(
        signal=signal("2026-05-28", 100.0, 200.0),
        log_path=log_path,
        initial_equity=10_000.0,
        required_days=30,
        early_checkpoint_days=5,
    )

    assert first.appended is True
    assert second.appended is False
    assert len(log_path.read_text(encoding="utf-8").splitlines()) == 1


def test_normalized_weights_rejects_bad_input() -> None:
    with pytest.raises(SystemExit):
        normalized_weights({"AAPL": -1.0})
