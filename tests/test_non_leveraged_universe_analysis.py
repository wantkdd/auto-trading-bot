"""Safety checks for non-leveraged universe analysis."""

from __future__ import annotations

from scripts.non_leveraged_universe_analysis import looks_leveraged


def test_leveraged_and_inverse_symbols_are_blocked() -> None:
    for symbol in (
        "TQQQ",
        "SQQQ",
        "UPRO",
        "SPXL",
        "SOXL",
        "SSO",
        "SDS",
        "DXD",
        "DOG",
        "PSQ",
        "TBT",
        "TMF",
        "SH",
    ):
        assert looks_leveraged(symbol)


def test_plain_assets_are_not_marked_leveraged() -> None:
    for symbol in ("QQQ", "SPY", "GLD", "AAPL", "MSFT"):
        assert not looks_leveraged(symbol)
