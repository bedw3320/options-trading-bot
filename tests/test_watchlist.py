"""Watchlist YAML schema: optional falsifier; existing rows stay valid."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from schemas.watchlist import WatchlistName, load_watchlist

REPO_WATCHLIST = Path("strategies/watchlist.yaml")

MINIMAL_ROW = {
    "ticker": "TEST",
    "allowed_direction": "bullish",
    "thesis": "A human-written thesis.",
    "financing_dependence": "TBD",
    "events_to_avoid": ["earnings: TBD"],
    "status": "record_only",
    "added_by": "test",
    "added_on": "2026-11-02",
}


def test_falsifier_is_optional():
    row = WatchlistName.model_validate(MINIMAL_ROW)
    assert row.falsifier is None
    assert "falsifier" not in MINIMAL_ROW


def test_falsifier_string_is_accepted():
    row = WatchlistName.model_validate(
        {**MINIMAL_ROW, "falsifier": "CDS back under ~600bp."}
    )
    assert row.falsifier == "CDS back under ~600bp."


def test_missing_thesis_is_invalid():
    bad = {k: v for k, v in MINIMAL_ROW.items() if k != "thesis"}
    with pytest.raises(ValidationError):
        WatchlistName.model_validate(bad)


def test_invalid_direction_is_rejected():
    with pytest.raises(ValidationError):
        WatchlistName.model_validate({**MINIMAL_ROW, "allowed_direction": "long"})


def test_repo_watchlist_loads():
    wl = load_watchlist(REPO_WATCHLIST)
    tickers = [n.ticker for n in wl.names]
    assert tickers == ["SPY", "CRWV"]


def test_spy_row_valid_without_falsifier():
    wl = load_watchlist(REPO_WATCHLIST)
    spy = next(n for n in wl.names if n.ticker == "SPY")
    assert spy.status == "active"
    assert spy.allowed_direction == "bullish"
    assert spy.falsifier is None


def test_crwv_falsifier_and_earnings():
    wl = load_watchlist(REPO_WATCHLIST)
    crwv = next(n for n in wl.names if n.ticker == "CRWV")
    assert crwv.status == "record_only"
    assert crwv.allowed_direction == "bearish"
    assert crwv.falsifier is not None
    assert "600bp" in crwv.falsifier
    assert "Nov 10, 2026" in crwv.falsifier
    earnings = [e for e in crwv.events_to_avoid if e.lower().startswith("earnings")]
    assert len(earnings) == 1
    assert "2026-11-10" in earnings[0]
    assert "5 PM ET" in earnings[0]
    assert "investors.coreweave.com" in earnings[0]
    assert "TBD" not in earnings[0]
