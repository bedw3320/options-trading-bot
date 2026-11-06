"""Skew snapshot job: fixtures only, no Gateway."""

from __future__ import annotations

import json
from pathlib import Path

from research.db import list_snapshots
from research.models import QuotedChain
from research.skew import pick_expiries_near, rr25_for_expiry
from research.skew_snapshot import snapshot_chain
from schemas.watchlist import DELTA_CONVENTION
from utils.time_et import ET

FIX = Path("tests/fixtures/research")


def _chain(name: str) -> QuotedChain:
    return QuotedChain.model_validate(json.loads((FIX / name).read_text()))


def test_pick_30_and_45_distinct_expiries():
    chain = _chain("skew_two_expiries.json")
    today = chain.as_of.astimezone(ET).date()
    picked = pick_expiries_near(chain, today=today)
    by_target = {t: (exp, dte) for t, exp, dte in picked}
    assert by_target[30][0] == "20261204"  # 28 DTE
    assert by_target[45][0] == "20261218"  # 42 DTE


def test_rr25_put_rich():
    chain = _chain("skew_two_expiries.json")
    stats = rr25_for_expiry(chain, "20261218")
    assert stats["put_iv_25d"] == 0.18
    assert stats["call_iv_25d"] == 0.13
    assert stats["rr25"] == round(0.13 - 0.18, 6)
    assert stats["delta_convention"] == DELTA_CONVENTION


def test_snapshot_writes_ok_rows(tmp_path):
    db = str(tmp_path / "research.db")
    rows = snapshot_chain(_chain("skew_two_expiries.json"), db_path=db, max_quote_age_seconds=60)
    ok = [r for r in rows if r["status"] == "ok"]
    assert {r["target_dte"] for r in ok} == {30, 45}
    assert all(r["data_source"] == "ib_live" for r in ok)
    assert all(r["delta_convention"] == DELTA_CONVENTION for r in ok)
    stored = list_snapshots(db, ticker="SPY")
    assert len(stored) >= 2
    again = snapshot_chain(_chain("skew_two_expiries.json"), db_path=db, max_quote_age_seconds=60)
    assert all(r["skip_reason"] == "already_snapshotted" for r in again if r["target_dte"] in (30, 45))


def test_delayed_is_skipped_with_reason(tmp_path):
    db = str(tmp_path / "research.db")
    rows = snapshot_chain(_chain("delayed_chain.json"), db_path=db, max_quote_age_seconds=60)
    assert rows and rows[0]["status"] == "skipped"
    assert "delayed" in (rows[0]["skip_reason"] or "") or "non_live" in (rows[0]["skip_reason"] or "")
    assert rows[0]["data_source"] == "ib_delayed"


def test_stale_quotes_skipped(tmp_path):
    db = str(tmp_path / "research.db")
    rows = snapshot_chain(_chain("crossed_stale.json"), db_path=db, max_quote_age_seconds=60)
    assert rows[0]["status"] == "skipped"
    assert rows[0]["skip_reason"].startswith("stale_quotes")


def test_missing_greeks_skips_rr25(tmp_path):
    db = str(tmp_path / "research.db")
    rows = snapshot_chain(_chain("missing_greeks.json"), db_path=db, max_quote_age_seconds=60)
    reasons = {r["skip_reason"] for r in rows}
    assert any("missing_greeks" in (x or "") or "no_expiry" in (x or "") for x in reasons)
