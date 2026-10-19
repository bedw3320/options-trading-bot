"""Alpaca market-data adapter against recorded-shape fixtures (no network)."""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path

import httpx
import pytest

from core.brokers import SimBroker
from core.cycle import run_cycle
from core.market_state import FixtureMarketState, IBMarketState, make_provider
from core.strategy_loader import load
from integrations.vendors.alpaca import AlpacaMarketState
from integrations.vendors.chain import occ_symbol, parse_occ
from utils.lineage import Lineage

ROOT = Path(__file__).resolve().parents[1]
STRAT = ROOT / "strategies/active/spy-defined-risk-rr.yaml"
ENTRY = ROOT / "tests/fixtures/spy_snapshot_entry.json"
FX = json.loads((ROOT / "tests/fixtures/alpaca/alpaca_spy.json").read_text())
TODAY = date(2026, 10, 19)
RTH_NOW = lambda: datetime(2026, 10, 19, 15, 0, tzinfo=timezone.utc)  # noqa: E731


def transport(calls: list, *, status: int = 200, held: dict | None = None):
    def handler(req: httpx.Request) -> httpx.Response:
        calls.append(req)
        assert req.headers["APCA-API-KEY-ID"] == "kid"
        if status != 200:
            return httpx.Response(status, text='{"message":"forbidden"}')
        p = req.url.path
        if p.endswith("/trades/latest"):
            return httpx.Response(200, json=FX["latest_trade"])
        if p.endswith("/bars"):
            return httpx.Response(200, json=FX["bars"])
        if p.endswith("/v2/options/contracts"):
            page = "contracts_page2" if req.url.params.get("page_token") == "p2" else "contracts_page1"
            return httpx.Response(200, json=FX[page])
        if p.endswith("/options/snapshots/SPY"):
            return httpx.Response(200, json=FX["snapshots"])
        if p.endswith("/options/snapshots"):
            return httpx.Response(200, json={"snapshots": held or {}, "next_page_token": None})
        return httpx.Response(404)
    return httpx.MockTransport(handler)


def provider(calls, **kw):
    return AlpacaMarketState(key_id="kid", secret="sec", today=TODAY, now=RTH_NOW,
                             client=httpx.Client(transport=transport(calls, **{k: v for k, v in kw.items()})))


@pytest.fixture
def rules():
    return load(STRAT).rules


def test_snapshot_matches_recorded_fixture(rules):
    calls: list = []
    snap = provider(calls).snapshot(rules, held_legs=[])
    ref = FixtureMarketState(ENTRY).snapshot(rules, held_legs=[])
    assert snap.status == "ok", snap.reason
    assert snap.source == "alpaca:indicative"
    assert snap.expiry == ref.expiry and snap.underlying_price == ref.underlying_price
    assert snap.daily_closes == ref.daily_closes[-len(snap.daily_closes):]
    assert {o.occ for o in snap.options} == {o.occ for o in ref.options}  # Dec contract filtered out
    by = {o.occ: o for o in ref.options}
    for o in snap.options:
        assert (o.bid, o.ask, o.delta, o.iv, o.open_interest) == (
            by[o.occ].bid, by[o.occ].ask, by[o.occ].delta, by[o.occ].iv, by[o.occ].open_interest)
    feeds = {c.url.params.get("feed") for c in calls if "snapshots" in c.url.path}
    assert feeds == {"indicative"}
    assert any(c.url.params.get("page_token") == "p2" for c in calls)  # pagination followed


def test_full_cycle_on_alpaca_enters_like_fixture(rules, tmp_path):
    res = run_cycle(STRAT, mode="dry_run", provider=provider([]), broker=SimBroker(),
                    lineage=Lineage(str(tmp_path / "a.db")), allow_trading=True, now=RTH_NOW)
    ref = run_cycle(STRAT, mode="dry_run", provider=FixtureMarketState(ENTRY), broker=SimBroker(),
                    lineage=Lineage(str(tmp_path / "f.db")), allow_trading=True, now=RTH_NOW)
    assert ref.outcome == "entered" and res.outcome == ref.outcome, res.reasons


def test_held_legs_marked(rules):
    occ = "SPY261120P00700000"
    snap = provider([], held={occ: {"latestQuote": {"bp": 4.0, "ap": 4.2}}}).snapshot(
        rules, held_legs=[{"occ": occ, "expiry": "20261120", "strike": 700.0, "right": "P"}])
    assert snap.held_marks == {occ: pytest.approx(4.1)}


def test_http_error_is_unavailable_not_raise(rules):
    snap = provider([], status=403).snapshot(rules, held_legs=[])
    assert snap.status == "unavailable" and snap.reason.startswith("alpaca_error: http_403")


def test_missing_credentials_abstains(rules, monkeypatch):
    monkeypatch.delenv("ALPACA_API_KEY_ID", raising=False)
    monkeypatch.delenv("ALPACA_API_SECRET_KEY", raising=False)
    snap = AlpacaMarketState(client=httpx.Client(transport=transport([]))).snapshot(rules, held_legs=[])
    assert snap.status == "unavailable" and snap.reason == "alpaca_credentials_missing"


def test_make_provider():
    assert isinstance(make_provider("alpaca"), AlpacaMarketState)
    assert isinstance(make_provider("IB", ib=object()), IBMarketState)
    with pytest.raises(ValueError):
        make_provider("tradier")
    with pytest.raises(ValueError):
        make_provider("ib")


def test_occ_roundtrip():
    assert occ_symbol("SPY", "20261120", "P", 580.0) == "SPY261120P00580000"
    assert parse_occ("SPY261120P00580000") == ("SPY", "20261120", "P", 580.0)
