"""Tests for the fundamentals/recent-regime research gate."""

from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest
from scripts.fundamental_macro_recent_gate import (
    extract_filing_risk,
    extract_fundamental_metrics,
    fundamental_failure_reasons,
    recent_windows,
)

from auto_trading_bot.domain import Bar


def test_extract_fundamental_metrics_from_sec_companyfacts_shape() -> None:
    payload = {
        "facts": {
            "us-gaap": {
                "Revenues": {
                    "units": {
                        "USD": [
                            {"form": "10-K", "fy": 2024, "filed": "2025-01-31", "val": 100.0},
                            {"form": "10-K", "fy": 2025, "filed": "2026-01-31", "val": 125.0},
                        ]
                    }
                },
                "NetIncomeLoss": {
                    "units": {"USD": [{"form": "10-Q", "filed": "2026-04-30", "val": 10.0}]}
                },
                "NetCashProvidedByUsedInOperatingActivities": {
                    "units": {"USD": [{"form": "10-Q", "filed": "2026-04-30", "val": 15.0}]}
                },
                "Liabilities": {
                    "units": {"USD": [{"form": "10-Q", "filed": "2026-04-30", "val": 40.0}]}
                },
                "StockholdersEquity": {
                    "units": {"USD": [{"form": "10-Q", "filed": "2026-04-30", "val": 20.0}]}
                },
                "AssetsCurrent": {
                    "units": {"USD": [{"form": "10-Q", "filed": "2026-04-30", "val": 30.0}]}
                },
                "LiabilitiesCurrent": {
                    "units": {"USD": [{"form": "10-Q", "filed": "2026-04-30", "val": 10.0}]}
                },
            }
        }
    }

    metrics = extract_fundamental_metrics(payload)

    assert metrics["revenue_growth_yoy"] == 0.25
    assert metrics["net_income"] == 10.0
    assert metrics["operating_cash_flow"] == 15.0
    assert metrics["debt_to_equity"] == 2.0
    assert metrics["current_ratio"] == 3.0
    assert fundamental_failure_reasons(metrics, []) == []


def test_fundamental_failure_reasons_are_conservative_on_missing_or_weak_data() -> None:
    metrics = {
        "revenue_growth_yoy": -0.2,
        "net_income": -1.0,
        "operating_cash_flow": None,
        "debt_to_equity": 7.0,
    }

    assert fundamental_failure_reasons(metrics, ["companyfacts_cache_missing"]) == [
        "revenue_decline_worse_than_minus_10pct",
        "net_income_not_positive",
        "operating_cash_flow_missing",
        "debt_to_equity_above_5x",
        "sec_data_incomplete",
    ]


def test_extract_filing_risk_counts_recent_8k_filings(monkeypatch) -> None:
    class FixedDate(date):
        @classmethod
        def today(cls) -> date:
            return cls(2026, 5, 30)

    monkeypatch.setattr("scripts.fundamental_macro_recent_gate.date", FixedDate)
    payload = {
        "filings": {
            "recent": {
                "form": ["8-K", "10-Q", "8-K/A", "8-K"],
                "filingDate": ["2026-05-01", "2026-04-01", "2026-03-15", "2025-01-01"],
            }
        }
    }

    assert extract_filing_risk(payload) == (2, "2026-05-01")


def test_recent_windows_include_ai_proxy_and_trailing_windows() -> None:
    dates = tuple(date(2019, 1, 1) + timedelta(days=index) for index in range(365 * 8))

    labels = [row[0] for row in recent_windows(dates)]

    assert "post_2020" in labels
    assert "post_2022" in labels
    assert "ai_proxy_post_2023" in labels
    assert "trailing_504d" in labels
    assert "trailing_252d" in labels


def test_no_bar_fixture_needed_but_domain_import_remains_valid() -> None:
    bar = Bar(
        timestamp=datetime(2026, 1, 1),
        open=1.0,
        high=1.1,
        low=0.9,
        close=1.0,
        volume=100.0,
    )

    assert bar.close == 1.0


def test_sec_facts_after_as_of_date_are_ignored_to_prevent_lookahead() -> None:
    payload = {
        "facts": {
            "us-gaap": {
                "Revenues": {
                    "units": {
                        "USD": [
                            {"form": "10-K", "fy": 2024, "filed": "2025-02-01", "val": 100.0},
                            {"form": "10-K", "fy": 2025, "filed": "2026-02-01", "val": 110.0},
                            {"form": "10-K", "fy": 2026, "filed": "2026-06-01", "val": 999.0},
                        ]
                    }
                },
                "NetIncomeLoss": {
                    "units": {
                        "USD": [
                            {"form": "10-Q", "filed": "2026-05-01", "val": 10.0},
                            {"form": "10-Q", "filed": "2026-06-01", "val": -999.0},
                        ]
                    }
                },
            }
        }
    }

    metrics = extract_fundamental_metrics(payload, as_of=date(2026, 5, 30))

    assert metrics["revenue_growth_yoy"] == pytest.approx(0.1)
    assert metrics["net_income"] == 10.0


def test_filing_risk_ignores_filings_after_as_of_date() -> None:
    payload = {
        "filings": {
            "recent": {
                "form": ["8-K", "8-K", "10-Q"],
                "filingDate": ["2026-05-01", "2026-06-01", "2026-06-02"],
            }
        }
    }

    assert extract_filing_risk(payload, as_of=date(2026, 5, 30)) == (1, "2026-05-01")
