"""Tests for no-order quant paper candidate generation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from unittest.mock import patch

from scripts.paper_signal_dry_run import DryRunSignal
from scripts.quant_paper_signal import build_candidates, build_report, select_candidate


def feature(
    symbol: str,
    *,
    ret20: float,
    ret63: float,
    vol: float = 0.20,
    drawdown: float = -0.05,
    above50: bool = True,
    above200: bool = True,
) -> dict[str, object]:
    return {
        "symbol": symbol,
        "status": "ok",
        "return_20d": ret20,
        "return_63d": ret63,
        "realized_vol_20d": vol,
        "max_drawdown_63d": drawdown,
        "above_sma50": above50,
        "above_sma200": above200,
        "avg_dollar_volume_20d": 1_000_000_000.0,
    }


def market_feature_report(regime: str = "risk_on") -> dict[str, object]:
    return {
        "summary": {"status": "pass" if regime == "risk_on" else "review"},
        "quality_gate": {"blockers": []},
        "regime": {"label": regime},
        "features": [
            feature("NVDA", ret20=0.12, ret63=0.28, vol=0.38, drawdown=-0.08),
            feature("MSFT", ret20=0.06, ret63=0.18, vol=0.20, drawdown=-0.04),
            feature("AVGO", ret20=0.08, ret63=0.20, vol=0.30, drawdown=-0.06),
            feature("META", ret20=0.05, ret63=0.16, vol=0.24, drawdown=-0.05),
            feature("XLK", ret20=0.07, ret63=0.15, vol=0.18, drawdown=-0.04),
            feature("XLV", ret20=0.02, ret63=0.05, vol=0.12, drawdown=-0.02),
            feature("XLP", ret20=0.01, ret63=0.04, vol=0.10, drawdown=-0.02),
            feature("XLU", ret20=0.01, ret63=0.03, vol=0.11, drawdown=-0.03),
            feature("SPY", ret20=0.03, ret63=0.07, vol=0.14, drawdown=-0.03),
            feature("QQQ", ret20=0.06, ret63=0.12, vol=0.21, drawdown=-0.04),
            feature("IWM", ret20=0.02, ret63=0.06, vol=0.25, drawdown=-0.06),
            feature("DIA", ret20=0.02, ret63=0.05, vol=0.13, drawdown=-0.03),
            feature("GLD", ret20=-0.01, ret63=0.02, vol=0.16, drawdown=-0.03),
            feature("SHY", ret20=0.002, ret63=0.006, vol=0.03, drawdown=-0.002),
            feature("IEF", ret20=0.004, ret63=0.01, vol=0.07, drawdown=-0.01),
            feature("TLT", ret20=0.005, ret63=0.02, vol=0.18, drawdown=-0.03),
            feature("TQQQ", ret20=0.30, ret63=0.50, vol=0.70, drawdown=-0.20),
        ],
    }


def args(tmp_path: Path, feature_gate: Path) -> argparse.Namespace:
    return argparse.Namespace(
        market_feature_gate=str(feature_gate),
        output=str(tmp_path / "quant-signal.json"),
        report=str(tmp_path / "quant-report.json"),
        markdown=str(tmp_path / "quant-report.md"),
        start="2015-01-01",
        end="2026-06-01",
        data_dir="data/external",
        force_refresh=False,
    )


def test_build_candidates_creates_diversified_quant_candidate_without_leverage() -> None:
    candidates = build_candidates(market_feature_report("risk_on"))
    selected = select_candidate(candidates)

    assert selected is not None
    assert selected.status == "pass"
    assert selected.name == "quant_momentum_top5_defensive"
    assert "TQQQ" not in selected.weights
    assert max(selected.weights.values()) <= 0.35
    assert sum(selected.weights.values()) == 1.0
    assert {"NVDA", "MSFT", "AVGO"}.issubset(selected.weights)


def test_build_report_writes_quant_signal_without_changing_primary(tmp_path: Path) -> None:
    feature_gate = tmp_path / "market-feature.json"
    feature_gate.write_text(json.dumps(market_feature_report("conflicted")), encoding="utf-8")
    fake_signal = DryRunSignal(
        generated_at="2026-06-02T00:00:00+00:00",
        as_of_date="2026-06-01",
        strategy="quant_momentum_top5_defensive",
        target_weights={"NVDA": 0.15, "MSFT": 0.15, "GLD": 0.2, "SHY": 0.5},
        source_bars={},
        warnings=("do not place orders",),
    )

    with patch("scripts.quant_paper_signal.build_signal", return_value=fake_signal):
        report = build_report(args(tmp_path, feature_gate))

    assert report["summary"]["status"] == "review"
    assert report["summary"]["primary_strategy_changed"] is False
    assert report["summary"]["use_for_strategy_promotion"] is False
    assert report["summary"]["order_created"] is False
    assert report["live_trading_authorized"] is False
    assert json.loads((tmp_path / "quant-signal.json").read_text())["strategy"].startswith(
        "quant_"
    )


def test_build_report_blocks_missing_market_feature_gate(tmp_path: Path) -> None:
    report = build_report(args(tmp_path, tmp_path / "missing.json"))

    assert report["summary"]["status"] == "blocked"
    assert report["summary"]["selected_strategy"] is None
    assert "market_feature_gate_missing_for_quant_signal" in report["blockers"]
    assert report["live_trading_authorized"] is False
