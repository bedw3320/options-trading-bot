"""CBOE delayed-quotes adapter + shadow (record-only) semantics. No network."""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path

import httpx
import pytest

from core.brokers import SimBroker
from core.cli import main as cli_main
from core.cycle import run_cycle
from core.market_state import FixtureMarketState, make_provider
from core.report import render, summarize
from core.shadow import shadow_refusal, shadow_tag
from core.strategy_loader import load
from integrations.vendors.cboe import CboeMarketState, iv_decimal, parse_cboe_ts, probe_line
from utils.lineage import Lineage

ROOT = Path(__file__).resolve().parents[1]
STRAT = ROOT / "strategies/active/spy-defined-risk-rr.yaml"
ENTRY = ROOT / "tests/fixtures/spy_snapshot_entry.json"
FX = json.loads((ROOT / "tests/fixtures/cboe/cboe_spy.json").read_text())
TODAY = date(2026, 10, 19)
RTH_NOW = lambda: datetime(2026, 10, 19, 15, 0, tzinfo=timezone.utc)  # noqa: E731


def transport(calls: list, *, status: int = 200, options=None, bars=None, stale: bool = False):
    body = options if options is not None else FX["options"]
    if stale:
        body = json.loads(json.dumps(body))
        body["data"]["last_trade_time"] = "2026-10-19T09:00:00"
        body["timestamp"] = "2026-10-19T09:00:00"
    csv = bars if bars is not None else FX["bars_csv"]

    def handler(req: httpx.Request) -> httpx.Response:
        calls.append(req)
        if status != 200:
            return httpx.Response(status, text="nope")
        host = req.url.host or ""
        if "/charts/historical/" in req.url.path:
            return httpx.Response(200, text=csv)
        if "cboe.com" in host or req.url.path.endswith(".json"):
            return httpx.Response(200, json=body)
        if "stooq.com" in host or req.url.path.endswith("/l/"):
            return httpx.Response(200, text=csv)
        return httpx.Response(404)

    return httpx.MockTransport(handler)


def provider(calls, **kw):
    extras = {k: kw[k] for k in ("status", "options", "bars", "stale") if k in kw}
    return CboeMarketState(
        today=TODAY, now=RTH_NOW,
        client=httpx.Client(transport=transport(calls, **extras)),
    )


@pytest.fixture
def rules():
    return load(STRAT).rules


def test_iv_decimal_does_not_invent():
    assert iv_decimal(None) is None
    assert iv_decimal(0) is None
    assert iv_decimal(-1) is None
    assert iv_decimal("") is None
    assert iv_decimal(0.185) == pytest.approx(0.185)
    assert iv_decimal(18.5) == pytest.approx(0.185)


def test_parse_cboe_ts_naive_is_et():
    dt = parse_cboe_ts("2026-10-19T11:00:00")
    assert dt is not None and dt.hour == 15  # 11:00 ET = 15:00 UTC (EDT)


def test_snapshot_matches_recorded_fixture(rules):
    calls: list = []
    snap = provider(calls).snapshot(rules, held_legs=[])
    ref = FixtureMarketState(ENTRY).snapshot(rules, held_legs=[])
    assert snap.status == "ok", snap.reason
    assert snap.source == "cboe_delayed"
    assert snap.expiry == ref.expiry and snap.underlying_price == ref.underlying_price
    assert snap.daily_closes == ref.daily_closes[-len(snap.daily_closes):]
    assert {o.occ for o in snap.options} == {o.occ for o in ref.options}
    by = {o.occ: o for o in ref.options}
    for o in snap.options:
        r = by[o.occ]
        assert (o.bid, o.ask, o.delta, o.open_interest) == (r.bid, r.ask, r.delta, r.open_interest)
        assert o.iv == pytest.approx(r.iv)
        assert o.gamma == pytest.approx(0.01)
    assert any("cboe.com" in (c.url.host or "") or c.url.path.endswith(".json") for c in calls)
    assert probe_line(snap).startswith("source=cboe_delayed status=ok")


def test_stale_quotes_unavailable(rules):
    snap = provider([], stale=True).snapshot(rules, held_legs=[])
    assert snap.status == "unavailable" and snap.reason.startswith("cboe_stale_quotes")


def test_missing_iv_is_not_filled_in(rules):
    body = json.loads(json.dumps(FX["options"]))
    for o in body["data"]["options"]:
        o.pop("iv", None)
        o["delta"] = None
    snap = provider([], options=body).snapshot(rules, held_legs=[])
    assert snap.status == "unavailable" and snap.reason == "no_option_greeks_or_bid_ask"


def test_http_error_is_unavailable(rules):
    snap = provider([], status=403).snapshot(rules, held_legs=[])
    assert snap.status == "unavailable" and snap.reason.startswith("cboe_error: http_403")


def test_missing_timestamp_unavailable(rules):
    body = json.loads(json.dumps(FX["options"]))
    body.pop("timestamp", None)
    body["data"].pop("last_trade_time", None)
    snap = provider([], options=body).snapshot(rules, held_legs=[])
    assert snap.status == "unavailable" and snap.reason == "cboe_timestamp_missing"


def test_short_bars_unavailable(rules):
    snap = provider([], bars="Date,Open,High,Low,Close,Volume\n2026-10-01,1,1,1,1,1\n").snapshot(
        rules, held_legs=[])
    assert snap.status == "unavailable" and snap.reason.startswith("historical_bars_unavailable")


def test_held_legs_marked(rules):
    occ = "SPY261120P00700000"
    snap = provider([]).snapshot(
        rules, held_legs=[{"occ": occ, "expiry": "20261120", "strike": 700.0, "right": "P"}])
    assert occ in snap.held_marks and snap.held_marks[occ] > 0


def test_make_provider_cboe():
    assert isinstance(make_provider("cboe"), CboeMarketState)
    assert shadow_tag("cboe") == "cboe_delayed"
    assert shadow_tag("ib") is None


class ExplodingBroker(SimBroker):
    def place(self, intent, *, revalidate):
        raise AssertionError("cboe shadow must never call broker.place")


def test_cboe_source_cannot_place_even_with_allow_trading(rules, tmp_path):
    lin = Lineage(str(tmp_path / "s.db"))
    res = run_cycle(
        STRAT, mode="dry_run", provider=provider([]), broker=ExplodingBroker(),
        lineage=lin, allow_trading=True, now=RTH_NOW, data_source="cboe",
    )
    assert res.outcome == "proposed_not_sent"
    assert res.reasons[0] == shadow_refusal("cboe_delayed")
    cyc = lin.get_cycle(res.cycle_id)
    assert cyc["artifacts"][0]["payload"]["data_source"] == "cboe_delayed"
    dec = next(a for a in cyc["artifacts"] if a["kind"] == "decision")
    assert dec["payload"]["data_source"] == "cboe_delayed"
    assert dec["payload"]["action"] == "enter"
    assert not any(a["kind"] == "fill" for a in cyc["artifacts"])
    order = next(a for a in cyc["artifacts"] if a["kind"] == "order")
    assert order["payload"]["sent"] is False
    assert lin.open_positions("spy-defined-risk-rr", "dry_run") == []


def test_cboe_shadow_does_not_consume_daily_entry_slot(tmp_path):
    """Every cycle can still evaluate; shadow proposes are not real entries."""
    lin = Lineage(str(tmp_path / "s.db"))
    r1 = run_cycle(STRAT, mode="dry_run", provider=provider([]), broker=ExplodingBroker(),
                   lineage=lin, allow_trading=True, now=RTH_NOW, data_source="cboe")
    r2 = run_cycle(STRAT, mode="dry_run", provider=provider([]), broker=ExplodingBroker(),
                   lineage=lin, allow_trading=True, now=RTH_NOW, data_source="cboe")
    assert r1.outcome == r2.outcome == "proposed_not_sent"


def test_ib_path_still_places_on_same_fixture(tmp_path):
    lin = Lineage(str(tmp_path / "s.db"))
    res = run_cycle(STRAT, mode="dry_run", provider=FixtureMarketState(ENTRY),
                    broker=SimBroker(), lineage=lin, allow_trading=True, now=RTH_NOW)
    assert res.outcome == "entered"
    dec = next(a for a in lin.get_cycle(res.cycle_id)["artifacts"] if a["kind"] == "decision")
    assert "data_source" not in dec["payload"]


def test_cli_refuses_allow_trading_on_cboe(tmp_path, capsys):
    rc = cli_main(["--db", str(tmp_path / "s.db"), "run", "--allow-trading", "--data-source", "cboe"])
    assert rc == 2
    err = capsys.readouterr().err
    assert "REFUSED" in err and "cboe" in err


def test_cli_dry_run_cboe_is_record_only(tmp_path, capsys):
    db = str(tmp_path / "s.db")
    assert cli_main(["--db", db, "run", "--dry-run", "--data-source", "cboe"]) == 0
    out = capsys.readouterr().out
    assert "proposed_not_sent" in out
    assert "shadow_record_only" in out
    assert cli_main(["--db", db, "report", "--limit", "1"]) == 0
    report = capsys.readouterr().out
    assert "data_source=cboe_delayed" in report
    assert "SELL" in report


def test_report_summarizes_intent_and_greeks(tmp_path):
    lin = Lineage(str(tmp_path / "s.db"))
    res = run_cycle(STRAT, mode="dry_run", provider=provider([]), broker=ExplodingBroker(),
                    lineage=lin, allow_trading=True, now=RTH_NOW, data_source="cboe")
    text = summarize(lin.get_cycle(res.cycle_id))
    assert "data_source=cboe_delayed" in text and "decision: enter" in text
    assert "SELL SPY" in text and "d=" in text
    blob = render([lin.get_cycle(res.cycle_id)], as_json=True)
    assert json.loads(blob)[0]["data_source"] == "cboe_delayed"


def test_daily_closes_from_cboe_history_json(rules):
    rows = [ln.split(",") for ln in FX["bars_csv"].splitlines()[1:] if ln.strip()]
    hist = json.dumps({"data": [{"date": r[0], "close": float(r[4])} for r in reversed(rows)]})
    calls: list = []
    snap = provider(calls, bars=hist).snapshot(rules, held_legs=[])
    csv_snap = provider([]).snapshot(rules, held_legs=[])
    assert snap.status == "ok", snap.reason
    assert snap.daily_closes == csv_snap.daily_closes
    assert any("/charts/historical/SPY.json" in c.url.path for c in calls)
