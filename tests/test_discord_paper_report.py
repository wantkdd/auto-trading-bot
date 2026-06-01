"""Tests for Discord no-order paper reporting."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from unittest.mock import patch

from scripts.discord_paper_report import build_report, main, post_discord


def _write(path: Path, payload: dict) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _args(tmp_path: Path, **overrides):
    values = {
        "webhook_url": "",
        "paper_summary": str(tmp_path / "paper.json"),
        "challenger_summary": str(tmp_path / "challenger.json"),
        "no_order_preview": str(tmp_path / "preview.json"),
        "readiness": str(tmp_path / "readiness.json"),
        "gate_status": str(tmp_path / "gate.json"),
        "dynamic_universe": str(tmp_path / "dynamic-universe.json"),
        "market_scan": str(tmp_path / "market.json"),
        "challenger_selection": str(tmp_path / "selection.json"),
        "intraday_log": str(tmp_path / "intraday.jsonl"),
        "adaptive_search": str(tmp_path / "adaptive.json"),
        "broker_preflight": str(tmp_path / "broker-preflight.json"),
        "market_feature_gate": str(tmp_path / "market-feature.json"),
        "run_url": "https://example.test/run",
        "output": str(tmp_path / "discord.json"),
        "markdown": str(tmp_path / "discord.md"),
        "dry_run": True,
        "weekly_day": 4,
        "final_observed_days": 15,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


def test_build_report_renders_daily_weekly_and_final_sections(tmp_path: Path) -> None:
    _write(
        tmp_path / "paper.json",
        {
            "latest_as_of_date": "2026-06-05",
            "latest_strategy": "AAPL_0.3_GLD_0.7",
            "observed_days": 15,
            "required_days": 30,
            "latest_virtual_equity": 10_500.0,
            "total_return_since_first_observation": 0.05,
            "max_drawdown_since_first_observation": -0.02,
        },
    )
    _write(
        tmp_path / "challenger.json",
        {
            "observed_days": 15,
            "latest_virtual_equity": 10_700.0,
            "total_return_since_first_observation": 0.07,
            "max_drawdown_since_first_observation": -0.03,
        },
    )
    _write(
        tmp_path / "preview.json",
        {
            "summary": {
                "decision": "would_hold",
                "accepted": 0,
                "rejected": 0,
                "total_notional": 0.0,
            }
        },
    )
    _write(
        tmp_path / "readiness.json",
        {
            "live_trading_authorized": False,
            "summary": {"paper_dry_run_ready": True},
            "live_blockers": ["human_approval_missing"],
        },
    )
    _write(tmp_path / "gate.json", {"summary": {"status": "pass"}})
    _write(
        tmp_path / "dynamic-universe.json",
        {
            "summary": {"selected": 150, "ranked": 142, "sources": 510},
            "top_selected_symbols": [
                "AAPL",
                "GLD",
                "NVDA",
                "MSFT",
                "AMZN",
                "META",
                "GOOGL",
                "AVGO",
                "LLY",
                "JPM",
            ],
        },
    )
    _write(tmp_path / "market.json", {"summary": {"top_candidate": "LLY_0.4_GLD_0.6"}})
    _write(tmp_path / "selection.json", {"summary": {"challenger_strategy": "LLY_0.4_GLD_0.6"}})
    _write(
        tmp_path / "adaptive.json",
        {
            "summary": {
                "status": "review",
                "median_excess": 0.054,
                "worst_max_drawdown": -0.232,
            },
            "static_baseline_summary": {"median_excess": 0.085},
        },
    )

    _write(
        tmp_path / "market-feature.json",
        {
            "summary": {
                "status": "review",
                "usable_assets": 142,
                "regime": "conflicted",
                "recommendation": "review_only_market_signals_are_conflicted",
            },
            "breadth": {"coverage_ratio": 0.94},
        },
    )
    _write(
        tmp_path / "broker-preflight.json",
        {
            "summary": {
                "status": "blocked",
                "ticket_count": 2,
                "blockers": 6,
                "order_created": False,
                "submit_attempted": False,
            }
        },
    )
    (tmp_path / "intraday.jsonl").write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "generated_at": "2026-06-05T14:00:00+00:00",
                        "summary": {"status": "ok", "changes": 1, "notable": 0},
                    }
                ),
                json.dumps(
                    {
                        "generated_at": "2026-06-05T14:05:00+00:00",
                        "summary": {"status": "ok", "changes": 0, "notable": 2},
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    report = build_report(_args(tmp_path))

    assert report["sections"] == ["daily", "weekly", "final"]
    assert "자동매매 가정 일일 리포트" in report["message"]
    assert "주간 요약" in report["message"]
    assert "3주 최종 점검" in report["message"]
    assert "동적 universe: `150`종목" in report["message"]
    assert "우선 관찰 10종목" in report["message"]
    assert "장중 5분 로그 요약" in report["message"]
    assert "저장된 장중 체크: `2`회" in report["message"]
    assert "판단 변화 합계: `1`" in report["message"]
    assert "특이 움직임 합계: `2`" in report["message"]
    assert "보정/튜닝 상태" in report["message"]
    assert "adaptive 후보 상태: `review`" in report["message"]
    assert "자동 교체/실거래 반영: `False`" in report["message"]
    assert "방대한 시장 데이터 게이트" in report["message"]
    assert "사용 가능 자산: `142`개" in report["message"]
    assert "브로커 API 연결 준비도" in report["message"]
    assert "API preflight: `blocked`" in report["message"]
    assert "adapter ticket 수: `2`" in report["message"]
    assert "NVDA" in report["message"]
    assert "실금액 자동매매는 아직 승인되지 않았습니다" in report["message"]


def test_main_dry_run_writes_outputs_without_posting(tmp_path: Path) -> None:
    output = tmp_path / "discord.json"
    markdown = tmp_path / "discord.md"

    assert main(["--dry-run", "--output", str(output), "--markdown", str(markdown)]) == 0

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["live_trading_authorized"] is False
    assert "NO-ORDER" in markdown.read_text(encoding="utf-8")


def test_post_discord_uses_json_webhook_payload() -> None:
    class Response:
        status = 204

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    with patch("urllib.request.urlopen", return_value=Response()) as urlopen:
        post_discord("https://discord.example/webhook", "hello")

    request = urlopen.call_args.args[0]
    assert request.method == "POST"
    assert json.loads(request.data.decode("utf-8"))["content"] == "hello"
