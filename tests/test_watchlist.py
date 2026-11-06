"""Watchlist schema: structured falsifier, promotion helpers, CI lint; old rows still parse."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from schemas.watchlist import (
    WatchlistName,
    blocks_new_entries,
    can_promote_to_active,
    evidence_blocks_promotion,
    falsifier_blocks_new_entries,
    lint_watchlist,
    load_watchlist,
    thesis_agrees_with_skew,
)
from scripts.validate_watchlist import main as validate_main

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
    assert row.direction == "bullish"
    assert row.allowed_direction == "bullish"


def test_falsifier_string_is_accepted():
    row = WatchlistName.model_validate(
        {**MINIMAL_ROW, "falsifier": "CDS back under ~600bp."}
    )
    assert row.falsifier == "CDS back under ~600bp."
    assert row.structured_falsifier() is None


def test_structured_falsifier_parses():
    row = WatchlistName.model_validate({
        **MINIMAL_ROW,
        "falsifier": {
            "metric": "5y_cds_bp",
            "threshold": 600,
            "source": "ref",
            "expires": "2026-11-17",
        },
    })
    f = row.structured_falsifier()
    assert f is not None and f.metric == "5y_cds_bp" and f.threshold == 600
    assert f.expires == date(2026, 11, 17)


def test_missing_thesis_is_invalid():
    bad = {k: v for k, v in MINIMAL_ROW.items() if k != "thesis"}
    with pytest.raises(ValidationError):
        WatchlistName.model_validate(bad)


def test_invalid_direction_is_rejected():
    with pytest.raises(ValidationError):
        WatchlistName.model_validate({**MINIMAL_ROW, "allowed_direction": "long"})
    with pytest.raises(ValidationError):
        WatchlistName.model_validate({**MINIMAL_ROW, "direction": "long"})


def test_repo_watchlist_loads():
    wl = load_watchlist(REPO_WATCHLIST)
    tickers = [n.ticker for n in wl.names]
    assert tickers == ["SPY", "CRWV"]


def test_spy_row_valid_without_falsifier():
    wl = load_watchlist(REPO_WATCHLIST)
    spy = next(n for n in wl.names if n.ticker == "SPY")
    assert spy.status == "active"
    assert spy.direction == "bullish"
    assert spy.allowed_direction == "bullish"
    assert spy.falsifier is None
    assert spy.approved_by.lower() == "will"
    assert spy.exits is not None and spy.exits.dte_close == 21
    assert spy.narrative is None


def test_crwv_falsifier_and_earnings():
    wl = load_watchlist(REPO_WATCHLIST)
    crwv = next(n for n in wl.names if n.ticker == "CRWV")
    assert crwv.status == "record_only"
    assert crwv.direction == "bearish"
    f = crwv.structured_falsifier()
    assert f is not None
    assert f.threshold == 600
    assert f.expires == date(2026, 11, 17)
    assert crwv.narrative is not None
    assert "Nov 10, 2026" in crwv.narrative or "2026-11-10" in crwv.narrative
    assert crwv.sources
    assert any("investors.coreweave.com" in s for s in crwv.sources)
    assert crwv.forecast_horizon == "12 weeks"
    assert crwv.registered_at == date(2026, 10, 26)
    earnings = [e for e in crwv.events_to_avoid if e.lower().startswith("earnings")]
    assert len(earnings) == 1
    assert "2026-11-10" in earnings[0]
    assert "5 PM ET" in earnings[0]
    assert "investors.coreweave.com" in earnings[0]
    assert "TBD" not in earnings[0]


def test_repo_watchlist_lints_clean():
    wl = load_watchlist(REPO_WATCHLIST)
    assert lint_watchlist(wl) == []
    assert validate_main([]) == 0


def test_expired_falsifier_blocks_new_entries():
    row = WatchlistName.model_validate({
        **MINIMAL_ROW,
        "status": "active",
        "approved_by": "will",
        "approved_on": "2026-10-26",
        "falsifier": {
            "metric": "cds", "threshold": 600, "source": "ref", "expires": "2026-11-01",
        },
    })
    blocked, why = falsifier_blocks_new_entries(row, today=date(2026, 11, 6))
    assert blocked and why and why.startswith("falsifier_expired")
    blocked, why = blocks_new_entries(row, today=date(2026, 11, 6))
    assert blocked


def test_tripped_falsifier_blocks_new_entries():
    row = WatchlistName.model_validate({
        **MINIMAL_ROW,
        "status": "active",
        "approved_by": "will",
        "approved_on": "2026-10-26",
        "falsifier": {
            "metric": "cds", "threshold": 600, "source": "ref",
            "expires": "2026-12-01", "tripped": True, "tripped_on": "2026-11-05",
        },
    })
    blocked, why = falsifier_blocks_new_entries(row, today=date(2026, 11, 6))
    assert blocked and "falsifier_tripped" in (why or "")


def test_thesis_and_skew_must_agree():
    ok, why = thesis_agrees_with_skew("bullish", "put_rich")
    assert ok
    ok, why = thesis_agrees_with_skew("bearish", "call_rich")
    assert ok
    ok, why = thesis_agrees_with_skew("bullish", "call_rich")
    assert not ok and "disagrees" in why
    ok, why = thesis_agrees_with_skew("bearish", None)
    assert not ok and why == "skew_unavailable"


def test_missing_or_stale_evidence_blocks_promotion():
    row = WatchlistName.model_validate(MINIMAL_ROW)
    blocked, why = evidence_blocks_promotion(row, today=date(2026, 11, 6))
    assert blocked and why == "missing_sources"
    ok, reasons = can_promote_to_active(row, today=date(2026, 11, 6), skew_side="put_rich")
    assert not ok
    assert "missing_sources" in reasons
    assert "skew_unavailable" not in reasons
    assert "missing_will_approval" in reasons


def test_lint_rejects_non_spy_without_sources_and_active_without_will(tmp_path):
    doc = {
        "names": [
            {
                "ticker": "FOO",
                "direction": "bearish",
                "status": "active",
                "thesis": "nope",
                "sources": [],
                "added_by": "bot",
                "added_on": "2026-11-06",
            }
        ]
    }
    path = tmp_path / "wl.yaml"
    path.write_text(yaml.safe_dump(doc))
    wl = load_watchlist(path)
    errors = lint_watchlist(wl)
    joined = " ".join(errors)
    assert "FOO: non-SPY entry requires sources" in joined
    assert "approved_by: will" in joined
    assert validate_main([str(path)]) == 1


def test_lint_rejects_string_falsifier(tmp_path):
    doc = {
        "names": [
            {
                **MINIMAL_ROW,
                "ticker": "ZZZ",
                "sources": ["https://example.com"],
                "falsifier": "just a string",
                "forecast_horizon": "12 weeks",
                "registered_at": "2026-11-01",
            }
        ]
    }
    path = tmp_path / "wl.yaml"
    path.write_text(yaml.safe_dump(doc))
    errors = lint_watchlist(load_watchlist(path))
    assert any("structured" in e for e in errors)


def test_lint_caps_record_only_theme_and_count(tmp_path):
    def row(ticker, theme):
        return {
            "ticker": ticker,
            "direction": "bearish",
            "status": "record_only",
            "theme": theme,
            "thesis": "t",
            "sources": ["https://example.com"],
            "falsifier": {
                "metric": "x", "threshold": 1, "source": "ref", "expires": "2026-12-01",
            },
            "forecast_horizon": "12 weeks",
            "registered_at": "2026-11-01",
            "added_by": "test",
            "added_on": "2026-11-01",
        }

    names = [row("A", "t1"), row("B", "t1"), row("C", "t1"), row("D", "t1")]
    path = tmp_path / "wl.yaml"
    path.write_text(yaml.safe_dump({"names": names}))
    errors = lint_watchlist(load_watchlist(path))
    assert any("at most 3 record_only" in e for e in errors)

    names = [row("A", "t1"), row("B", "t2")]
    path.write_text(yaml.safe_dump({"names": names}))
    errors = lint_watchlist(load_watchlist(path))
    assert any("at most 1 theme" in e for e in errors)
