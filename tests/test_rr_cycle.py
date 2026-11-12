"""Deterministic standard-RR cycle: schema, signals, construction, lineage,
market-state fail-closed, reconcile, kill switch, paper enforcement. No Gateway."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
import yaml
from pydantic import ValidationError

from core.brokers import IBExecution, SimBroker
from core.cli import explain, main as cli_main
from core.cycle import run_cycle
from core.entry_window import DRY_RUN_NOW, in_entry_slot
from core.guarded_broker import GuardedBroker, GuardedReject
from core.identity import IdentityError
from core.market_state import DictMarketState, FixtureMarketState, IBMarketState
from core.reconcile import expected_option_positions
from core.rr_rules import build_entry, evaluate_exit
from core.send_gate import paper_send_reason
from core.signals import compute_signals, failing_required, iv_at_abs_delta, realized_vol, skew_percentile
from core.strategy_loader import load
from core.universe import name_key, occ_root, resolve_universe, vendor_symbol
from schemas.cycle import MarketSnapshot, OptionRow
from schemas.strategy import IN_FORCE_ENGINE, StrategyConfig
from utils.lineage import Lineage

ROOT = Path(__file__).resolve().parents[1]
STRAT = ROOT / "strategies/active/us-large-cap-rr.yaml"
HISTORICAL = ROOT / "strategies/active/spy-defined-risk-rr.yaml"
FIX = ROOT / "tests/fixtures"
ENTRY = FIX / "spy_snapshot_entry.json"
FLAT = FIX / "spy_snapshot_flat_skew.json"
UNAVAIL = FIX / "spy_snapshot_unavailable.json"
NAME = "us-large-cap-rr"
# Monday 2026-10-19 10:00 America/Toronto (EDT) = 14:00 UTC.
SLOT_NOW = lambda: DRY_RUN_NOW  # noqa: E731
# 2026-11-12 10:00 EST = 15:00 UTC (the live CBOE as_of bug day).
NOV12_SLOT = lambda: datetime(2026, 11, 12, 15, 0, tzinfo=timezone.utc)  # noqa: E731


@pytest.fixture
def rules():
    return load(STRAT).rules


@pytest.fixture
def lin(tmp_path):
    return Lineage(str(tmp_path / "state.db"))


def snap(path=ENTRY, **over) -> MarketSnapshot:
    raw = json.loads(Path(path).read_text())
    raw.update(over)
    return MarketSnapshot.model_validate(raw)


def dry(lin, path=ENTRY, broker=None, now=SLOT_NOW, **over):
    seeded = expected_option_positions(lin.open_positions(NAME, "dry_run"))
    return run_cycle(
        STRAT, mode="dry_run", provider=FixtureMarketState(path, overrides=over),
        broker=broker or SimBroker(seeded), lineage=lin, allow_trading=True, now=now,
    )


def clone_entry(ticker: str, *, put_iv_boost: float = 0.0, **over) -> dict:
    raw = json.loads(ENTRY.read_text())
    raw["underlying"] = ticker
    raw["source"] = f"fixture:{ticker}"
    for o in raw["options"]:
        rest = o["occ"][len("SPY"):]
        o["occ"] = ticker + rest
        if put_iv_boost and o.get("right") == "P" and o.get("iv") is not None:
            o["iv"] = float(o["iv"]) + put_iv_boost
    raw.update(over)
    return raw


# --- strategy schema ---------------------------------------------------------

def _raw():
    return yaml.safe_load(STRAT.read_text())


def test_active_strategy_validates(rules):
    assert rules.engine == IN_FORCE_ENGINE
    assert rules.underlying is None
    assert rules.universe is not None and rules.universe.source == "sp500"
    assert rules.sizing.contracts == 1
    assert rules.sizing.max_new_opens_per_run == 5
    assert rules.sizing.max_new_opens_per_day == 10
    assert rules.sizing.max_open_positions is None
    assert rules.sizing.max_loss_usd is None
    assert rules.structure.wing_width is None
    assert rules.structure.max_net_debit is None
    assert rules.exits.automated is False
    assert rules.kill_switch.daily_loss_limit_usd is None
    assert rules.signals.require_iv_over_rv is False
    assert rules.signals.require_put_call_iv_ratio is False
    assert rules.execution.paper_only is True and rules.execution.required_account_prefix == "DU"
    assert rules.structure.dte_min == 30 and rules.structure.dte_max == 45
    assert tuple(rules.execution.entry_slots_et) == ("10:00", "15:00")
    assert rules.execution.entry_timezone == "America/Toronto"


def test_historical_defined_risk_yaml_still_parses_but_is_not_loaded(tmp_path):
    hist = load(HISTORICAL)
    assert hist.name == "spy-defined-risk-rr"
    assert hist.rules.engine == "defined_risk_risk_reversal_v0"
    assert hist.rules.structure.wing_width == 20
    with pytest.raises(ValueError, match="superseded"):
        run_cycle(
            HISTORICAL, mode="dry_run", provider=FixtureMarketState(ENTRY),
            broker=SimBroker(), lineage=Lineage(str(tmp_path / "h.db")),
            allow_trading=True, now=SLOT_NOW,
        )


@pytest.mark.parametrize("path,value", [
    (("execution", "paper_only"), False),
    (("sizing", "contracts"), 2),
    (("execution", "required_account_prefix"), "U"),
    (("structure", "wing_width"), 20),
    (("structure", "max_net_debit"), 0.5),
    (("exits", "automated"), True),
    (("sizing", "max_loss_usd"), 2500),
])
def test_schema_rejects_unsafe_values(path, value):
    raw = _raw()
    raw["rules"][path[0]][path[1]] = value
    with pytest.raises(ValidationError):
        StrategyConfig.model_validate(raw)


def test_examples_still_load_without_rules():
    for p in (ROOT / "strategies/examples").glob("*.yaml"):
        assert load(p).rules is None


def test_universe_never_reads_watchlist(rules):
    listed = resolve_universe(rules, FixtureMarketState(ENTRY))
    assert listed == ["SPY"]
    src = (ROOT / "core/universe.py").read_text() + (ROOT / "core/cycle.py").read_text()
    assert "load_watchlist" not in src
    assert "strategies/watchlist.yaml" not in (ROOT / "core/cycle.py").read_text()


def test_vendor_symbol_and_name_key():
    assert vendor_symbol("BRK.B", vendor="ib") == "BRK B"
    assert vendor_symbol("BRK.B", vendor="cboe") == "BRKB"
    assert vendor_symbol("BRK.B", vendor="alpaca") == "BRKB"
    assert name_key("BRK.B") == name_key("BRKB") == name_key("BRK B") == "BRKB"


# --- signals ------------------------------------------------------------------

def test_signals_pass_on_rich_skew(rules):
    sigs = compute_signals(snap(), rules)
    by = {s.name: s for s in sigs}
    assert by["rr25"].value <= -0.05 and by["rr25"].passed
    assert by["rr25"].required is True
    assert by["put_call_iv_ratio"].required is False
    assert by["atm_iv_minus_rv"].required is False
    assert by["rr25_percentile"].passed is None and not by["rr25_percentile"].required
    assert failing_required(sigs) == []


def test_signals_fail_on_flat_skew(rules):
    names = {s.name for s in failing_required(compute_signals(snap(FLAT), rules))}
    assert names == {"rr25"}


def test_pcr_and_iv_rv_are_not_binding(rules):
    s = snap()
    tight_rv = s.model_copy(update={"daily_closes": [100.0] * 25})
    sigs = compute_signals(tight_rv, rules)
    by = {x.name: x for x in sigs}
    assert by["rr25"].passed
    assert failing_required(sigs) == []
    assert by["put_call_iv_ratio"].required is False
    assert by["atm_iv_minus_rv"].required is False


def test_event_blackout_is_not_binding(rules):
    sigs = compute_signals(snap(as_of="2026-10-26T15:00:00+00:00"), rules)
    assert failing_required(sigs) == []
    by = {s.name: s for s in sigs}
    assert by["event_blackout"].required is False


def test_missing_greeks_fail_closed(rules):
    s = snap()
    for o in s.options:
        o.delta = None
    assert {x.name for x in failing_required(compute_signals(s, rules))} == {"rr25"}


def test_realized_vol_and_percentile():
    assert realized_vol([100.0] * 10, 20) is None
    rv = realized_vol([100 * (1.01 if i % 2 else 1.0) for i in range(22)], 20)
    assert rv == pytest.approx(0.01 * 252 ** 0.5 * (20 / 19) ** 0.5 * 1.0, rel=0.05)
    assert skew_percentile(-0.08, [-0.02, -0.04, -0.06, -0.09]) == 75.0


def _opt(right, strike, delta, iv, expiry="20261120"):
    occ = f"SPY{expiry}{right}{int(strike * 1000):08d}"
    return OptionRow(occ=occ, expiry=expiry, right=right, strike=strike,
                     bid=1.0, ask=1.1, delta=delta, iv=iv, open_interest=5000)


def test_iv_at_abs_delta_oct22_shadow_brackets():
    put_lo = _opt("P", 740, -0.2328, 0.1709)
    put_hi = _opt("P", 745, -0.2640, 0.1646)
    got = iv_at_abs_delta([put_lo, put_hi], "P", 0.25)
    assert got is not None and got.method == "interpolated"
    w_hi = (0.25 - 0.2328) / (0.2640 - 0.2328)
    assert got.iv == pytest.approx(0.1709 * (1 - w_hi) + 0.1646 * w_hi)
    assert got.rows[0].strike == 740 and got.rows[1].strike == 745
    assert got.weights[1] == pytest.approx(w_hi)


def test_rr25_interpolates_oct22_example_and_logs_weights(rules):
    call = _opt("C", 780, 0.25, 0.1183)
    put_lo = _opt("P", 740, -0.2328, 0.1709)
    put_hi = _opt("P", 745, -0.2640, 0.1646)
    s = snap()
    s.options = [call, put_lo, put_hi]
    s.expiry = "20261120"
    by = {x.name: x for x in compute_signals(s, rules)}
    w_hi = (0.25 - 0.2328) / (0.2640 - 0.2328)
    put_iv = 0.1709 * (1 - w_hi) + 0.1646 * w_hi
    assert by["rr25"].value == pytest.approx(0.1183 - put_iv, abs=1e-6)
    assert "interpolated" in by["rr25"].note and "740" in by["rr25"].note and "745" in by["rr25"].note
    assert "w=" in by["rr25"].note
    assert by["put_call_iv_ratio"].value == pytest.approx(put_iv / 0.1183, abs=1e-6)


def test_iv_at_abs_delta_exact_and_nearest_fallback():
    exact = _opt("P", 740, -0.25, 0.17)
    assert iv_at_abs_delta([exact], "P", 0.25).method == "exact"
    only_rich = [_opt("P", 745, -0.30, 0.16), _opt("P", 750, -0.35, 0.15)]
    fb = iv_at_abs_delta(only_rich, "P", 0.25)
    assert fb.method == "nearest" and fb.rows[0].strike == 745
    assert iv_at_abs_delta([], "P", 0.25) is None


# --- construction / exits ---------------------------------------------------------

def test_build_entry_standard_rr_two_legs(rules):
    intent, why = build_entry(snap(), rules, strategy_name="x", idempotency_key="k")
    assert intent is not None, why
    assert len(intent.legs) == 2
    sp, call = intent.legs
    assert (sp.action, sp.right, call.action, call.right) == ("SELL", "P", "BUY", "C")
    assert sp.expiry == call.expiry == "20261120"
    assert 0.15 <= abs(sp.delta) <= 0.35
    assert 0.15 <= call.delta <= 0.35
    assert intent.quantity == 1
    assert intent.max_loss_usd is None
    assert occ_root(sp.occ) == "SPY"


def test_build_entry_abstains_on_missing_oi(rules):
    s = snap()
    for o in s.options:
        o.open_interest = None
    intent, why = build_entry(s, rules, strategy_name="x", idempotency_key="k")
    assert intent is None and "open interest unavailable" in " ".join(why)


def _position(intent, entry):
    return {"position_id": "p1", "legs": [l.model_dump() for l in intent.legs], "entry_price": entry, "quantity": 1}


def test_evaluate_exit_never_auto_closes(rules):
    intent, _ = build_entry(snap(), rules, strategy_name="x", idempotency_key="k")
    pos = _position(intent, intent.limit_price)
    marks = {l.occ: (l.bid + l.ask) / 2 for l in intent.legs}
    assert evaluate_exit(pos, snap(held_marks=marks), rules)[0] is None
    assert evaluate_exit(pos, snap(held_marks=marks, as_of="2026-10-30T15:00:00+00:00"), rules)[0] is None
    assert evaluate_exit(pos, snap(held_marks=marks, underlying_price=700.0), rules)[0] is None
    assert evaluate_exit({**pos, "entry_price": intent.limit_price + 13}, snap(held_marks=marks), rules)[0] is None
    assert evaluate_exit({**pos, "entry_price": intent.limit_price - 11}, snap(held_marks=marks), rules)[0] is None
    trig, _, why = evaluate_exit(pos, snap(held_marks={}), rules)
    assert trig is None and "manual flatten" in why[0]


def _seed_rr25(lin: Lineage, cycle_id: str, value: float, started_at: str, mode: str = "dry_run"):
    lin.start_cycle(strategy=NAME, strategy_version="1.0.0", strategy_sha256="x",
                    mode=mode, cycle_id=cycle_id, started_at=started_at)
    lin.record(cycle_id, "signals", {"signals": [{"name": "rr25", "value": value}]})
    lin.end_cycle(cycle_id, "abstained", ["seed"])


def test_signal_history_one_rr25_per_et_day(lin):
    _seed_rr25(lin, "c-d1a", -0.040, "2026-10-19T14:15:00+00:00")
    _seed_rr25(lin, "c-d1b", -0.041, "2026-10-19T14:30:00+00:00")
    _seed_rr25(lin, "c-d1f", -0.060, "2026-10-19T19:00:00+00:00")
    _seed_rr25(lin, "c-d2a", -0.050, "2026-10-20T14:15:00+00:00")
    _seed_rr25(lin, "c-d2b", -0.055, "2026-10-20T19:00:00+00:00")
    assert lin.signal_history(NAME, "dry_run", "rr25") == [-0.060, -0.055]


# --- entry window (wall clock, not quote as_of) --------------------------------

def test_entry_window_uses_toronto_wall_clock_not_as_of(rules):
    assert in_entry_slot(DRY_RUN_NOW, rules)
    # Live bug 2026-11-12: 10:00 ET cycle, CBOE as_of 9:44 ET.
    clock = datetime(2026, 11, 12, 15, 0, tzinfo=timezone.utc)
    assert in_entry_slot(clock, rules)
    toronto = clock.astimezone(ZoneInfo("America/Toronto"))
    assert toronto.hour == 10 and toronto.minute == 0
    assert not in_entry_slot(datetime(2026, 10, 19, 15, 0, tzinfo=timezone.utc), rules)  # 11:00 ET
    assert not in_entry_slot(datetime(2026, 11, 12, 14, 59, tzinfo=timezone.utc), rules)


def test_cycle_enters_when_clock_in_slot_even_if_as_of_before_open(lin):
    # Quote as_of 9:44 ET; wall clock 10:00 ET. DTE still computed from 2026-10-19.
    r = dry(lin, as_of="2026-10-19T13:44:00+00:00", now=SLOT_NOW)
    assert r.outcome == "entered", r.reasons
    assert not any("outside entry window" in x for x in r.reasons)


def test_cycle_abstains_outside_slots_even_if_as_of_looks_in_window(lin):
    # 11:00 ET wall clock, as_of 10:00 ET.
    r = dry(lin, as_of="2026-10-19T14:00:00+00:00",
            now=lambda: datetime(2026, 10, 19, 15, 0, tzinfo=timezone.utc))
    assert r.outcome == "abstained"
    assert any("outside entry window" in x for x in r.reasons)


# --- full dry-run cycles + lineage ----------------------------------------------------

def test_dry_run_full_cycle_lineage(lin):
    r = dry(lin)
    assert r.outcome == "entered"
    cyc = lin.get_cycle(r.cycle_id)
    kinds = [a["kind"] for a in cyc["artifacts"]]
    for k in ("inputs", "reconcile", "market_snapshot", "signals", "decision", "intent", "order", "fill"):
        assert k in kinds, k
    pos = lin.open_positions(NAME, "dry_run")
    assert len(pos) == 1
    assert len(pos[0]["legs"]) == 2
    text = explain(cyc)
    assert "OUTCOME: entered" in text and "PASS rr25" in text and "SELL SPY261120P" in text
    assert "BUY SPY261120C" in text
    r2 = dry(lin)
    assert r2.outcome == "held"
    assert "no automated exits" in " ".join(r2.reasons)
    assert len(lin.open_positions(NAME, "dry_run")) == 1


def test_no_auto_exit_on_underlying_or_dte_crash(lin):
    assert dry(lin).outcome == "entered"
    r = dry(lin, underlying_price=700.0)
    assert r.outcome == "held"
    assert lin.open_positions(NAME, "dry_run")
    r2 = dry(lin, as_of="2026-10-30T14:00:00+00:00")
    assert r2.outcome == "held"
    assert lin.open_positions(NAME, "dry_run")


def test_unavailable_data_abstains_with_reason(lin):
    r = dry(lin, UNAVAIL)
    assert r.outcome == "abstained"
    assert r.reasons[0].startswith("market_data_unavailable:")
    cyc = lin.get_cycle(r.cycle_id)
    assert not any(a["kind"] in ("intent", "order") for a in cyc["artifacts"])


def test_flat_skew_abstains(lin):
    r = dry(lin, FLAT)
    assert r.outcome == "abstained" and r.reasons[0].startswith("signal rr25=")


def test_kill_switch_latches_and_rearms(lin):
    lin.latch_kill(NAME, "dry_run", "manual: test")
    r = dry(lin)
    assert r.outcome == "abstained" and r.reasons[0].startswith("kill_switch_latched")
    assert lin.rearm(NAME, "dry_run")
    assert dry(lin).outcome == "entered"


def test_reconcile_drift_latches_kill(lin):
    r = dry(lin, broker=SimBroker({"SPY261120P00700000": -3}))
    assert r.outcome == "abstained" and r.reasons[0] == "reconcile_drift"
    assert lin.kill_state(NAME, "dry_run")


def test_consecutive_errors_latch(lin):
    class Boom:
        def snapshot(self, rules, *, held_legs, underlying=None):
            raise RuntimeError("boom")

    for _ in range(3):
        r = run_cycle(STRAT, mode="dry_run", provider=Boom(), broker=SimBroker(), lineage=lin,
                      allow_trading=True, now=SLOT_NOW)
        assert r.outcome == "error"
    assert "consecutive error" in lin.kill_state(NAME, "dry_run")["reason"]


def test_unfilled_order_is_cancelled(lin):
    r = dry(lin, broker=SimBroker(fill=False))
    assert r.outcome == "abstained" and "cancelled" in r.reasons[0]
    assert lin.open_positions(NAME, "dry_run") == []
    assert lin.orders_by_status(NAME, "dry_run", ("cancelled",))


# --- universe ranking / caps --------------------------------------------------------

def test_ranks_top_five_richest_and_caps_per_run(lin, rules):
    names = ["AAPL", "MSFT", "NVDA", "AMZN", "META", "GOOGL"]
    # More negative rr25 = richer. Boost put IV on earlier names.
    snaps = {n: clone_entry(n, put_iv_boost=0.06 - i * 0.005) for i, n in enumerate(names)}
    provider = DictMarketState(snaps)
    r = run_cycle(STRAT, mode="dry_run", provider=provider, broker=SimBroker(), lineage=lin,
                  allow_trading=True, now=SLOT_NOW)
    assert r.outcome == "entered"
    roots = sorted({occ_root(p["legs"][0]["occ"]) for p in lin.open_positions(NAME, "dry_run")})
    assert len(roots) == 5
    assert "GOOGL" not in roots  # poorest of the six
    assert roots == ["AAPL", "AMZN", "META", "MSFT", "NVDA"]


def test_max_ten_opens_per_day(lin):
    names = [f"N{i:02d}" for i in range(12)]
    # N00.. not in SP500. Use real S&P names.
    names = ["AAPL", "MSFT", "NVDA", "AMZN", "META", "GOOGL", "JPM", "XOM", "JNJ", "V", "UNH", "HD"]
    snaps = {n: clone_entry(n, put_iv_boost=0.08) for n in names}
    provider = DictMarketState(snaps)
    r1 = run_cycle(STRAT, mode="dry_run", provider=provider, broker=SimBroker(), lineage=lin,
                   allow_trading=True, now=SLOT_NOW)
    assert r1.outcome == "entered"
    assert len(lin.open_positions(NAME, "dry_run")) == 5
    seeded = expected_option_positions(lin.open_positions(NAME, "dry_run"))
    r2 = run_cycle(STRAT, mode="dry_run", provider=provider, broker=SimBroker(seeded), lineage=lin,
                   allow_trading=True, now=SLOT_NOW)
    assert r2.outcome == "entered"
    assert len(lin.open_positions(NAME, "dry_run")) == 10
    seeded = expected_option_positions(lin.open_positions(NAME, "dry_run"))
    r3 = run_cycle(STRAT, mode="dry_run", provider=provider, broker=SimBroker(seeded), lineage=lin,
                   allow_trading=True, now=SLOT_NOW)
    assert r3.outcome == "held"
    assert "max_new_opens_per_day 10 reached" in " ".join(r3.reasons)
    assert len(lin.open_positions(NAME, "dry_run")) == 10


def test_no_second_risk_reversal_on_open_name(lin):
    assert dry(lin).outcome == "entered"
    r = dry(lin)
    assert r.outcome == "held"
    assert len(lin.open_positions(NAME, "dry_run")) == 1


# --- paper-mode enforcement (fake IB, no Gateway) ---------------------------------------

class FakeIB:
    def __init__(self, accounts=("DU123",)):
        self._accounts = list(accounts)

    def managedAccounts(self):
        return self._accounts

    def positions(self):
        return []

    def openTrades(self):
        return []

    def trades(self):
        return []

    def fills(self):
        return []

    def sleep(self, _):
        pass


class LiveIBFixture(FixtureMarketState):
    def snapshot(self, rules, *, held_legs, underlying=None):
        s = super().snapshot(rules, held_legs=held_legs, underlying=underlying)
        if s.status == "ok":
            return s.model_copy(update={"source": "ib"})
        return s


def paper(lin, ib, *, allow, account="DU123", now=SLOT_NOW, provider=None):
    return run_cycle(
        STRAT, mode="paper", provider=provider or FixtureMarketState(ENTRY),
        broker=IBExecution(ib, allow_trading=allow, expected_account_id=account),
        lineage=lin, allow_trading=allow, identity_check=lambda: account, now=now,
    )


def test_paper_live_account_hard_fails(lin):
    r = paper(lin, FakeIB(), allow=True, account="U9999")
    assert r.outcome == "error" and "identity_failure" in r.reasons[0]
    assert lin.kill_state(NAME, "paper")


def test_paper_fixture_data_cannot_send(lin, monkeypatch):
    monkeypatch.setenv("TRADING_MODE", "paper")
    monkeypatch.delenv("IB_GATEWAY_PORT", raising=False)
    r = paper(lin, FakeIB(), allow=True)
    assert r.outcome == "proposed_not_sent"
    assert "paper_send_blocked" in r.reasons[0] or "not live IBKR" in r.reasons[0]


def test_paper_live_ib_without_fill_cannot_send(lin, monkeypatch):
    monkeypatch.setenv("TRADING_MODE", "paper")
    monkeypatch.delenv("IB_GATEWAY_PORT", raising=False)
    r = paper(lin, FakeIB(), allow=True, provider=LiveIBFixture(ENTRY))
    assert r.outcome == "proposed_not_sent"
    assert "no reconciled paper fill" in r.reasons[0]


def test_paper_live_ib_with_fill_still_needs_allow_trading(lin, monkeypatch):
    monkeypatch.setenv("TRADING_MODE", "paper")
    monkeypatch.delenv("IB_GATEWAY_PORT", raising=False)
    lin.record_fill(exec_id="epic0", idempotency_key=None, broker_order_id="x",
                    cycle_id=None, mode="paper", payload={"exec_id": "epic0", "qty": 1, "price": 1})
    r = paper(lin, FakeIB(), allow=False, provider=LiveIBFixture(ENTRY))
    assert r.outcome == "proposed_not_sent" and "Trading disabled" in r.reasons[0]
    assert lin.orders_by_status(NAME, "paper", ("not_sent",))


def test_delayed_snapshot_cannot_send_even_in_dry_run(lin):
    delayed = FixtureMarketState(ENTRY, overrides={"source": "cboe_delayed"})
    r = run_cycle(STRAT, mode="dry_run", provider=delayed, broker=SimBroker(), lineage=lin,
                  allow_trading=True, now=SLOT_NOW)
    assert r.outcome == "proposed_not_sent"
    assert "shadow_record_only" in r.reasons[0] or "cboe" in r.reasons[0].lower()


def test_ib_delayed_and_frozen_cannot_send(lin):
    for src in ("ib_delayed", "ib_frozen"):
        r = run_cycle(
            STRAT, mode="dry_run",
            provider=FixtureMarketState(ENTRY, overrides={"source": src}),
            broker=SimBroker(), lineage=lin, allow_trading=True, now=SLOT_NOW,
        )
        assert r.outcome == "proposed_not_sent", src
        assert "shadow_record_only" in r.reasons[0] or "delayed" in r.reasons[0].lower() or src in r.reasons[0]


def test_paper_send_reason_unit(lin):
    s = snap(source="ib")
    assert paper_send_reason(mode="dry_run", data_source="ib", snapshot=s, lineage=lin) is None
    assert paper_send_reason(mode="paper", data_source="ib", snapshot=s, lineage=lin)
    lin.record_fill(exec_id="e1", idempotency_key=None, broker_order_id=None,
                    cycle_id=None, mode="paper", payload={"exec_id": "e1"})
    assert paper_send_reason(mode="paper", data_source="ib", snapshot=s, lineage=lin) is None
    delayed = snap(source="cboe_delayed")
    assert paper_send_reason(mode="paper", data_source="ib", snapshot=delayed, lineage=lin)


def test_paper_market_closed_abstains(lin):
    r = paper(lin, FakeIB(), allow=False, now=lambda: datetime(2026, 10, 18, 15, 0, tzinfo=timezone.utc))
    assert r.outcome == "abstained" and r.reasons[0].startswith("market_closed")


def test_daily_loss_does_not_latch(lin):
    lin.open_position(position_id="p-old", strategy=NAME, mode="dry_run", cycle_id="c0", legs=[],
                      entry_price=0.5, quantity=1, max_loss_usd=None)
    lin.close_position("p-old", cycle_id="c0", exit_price=-16.0, trigger="manual_flatten")
    r = dry(lin)
    assert r.outcome == "entered"
    assert lin.kill_state(NAME, "dry_run") is None


def test_guarded_combo_token_flow(rules, monkeypatch):
    monkeypatch.delenv("IB_GATEWAY_PORT", raising=False)
    intent, _ = build_entry(snap(), rules, strategy_name="x", idempotency_key="k")
    gb = GuardedBroker(FakeIB(), allow_trading=True, expected_account_id="DU123", trading_mode="paper")
    pv = gb.preview_combo(intent)
    placed = gb.confirm_combo(pv.token, intent, place_fn=lambda ib, i: {"status": "Filled"})
    assert placed["status"] == "Filled"
    with pytest.raises(GuardedReject):
        gb.confirm_combo(pv.token, intent, place_fn=lambda ib, i: {})
    tampered = intent.model_copy(update={"limit_price": intent.limit_price + 1})
    pv2 = gb.preview_combo(intent)
    with pytest.raises(GuardedReject):
        gb.confirm_combo(pv2.token, tampered, place_fn=lambda ib, i: {})
    with pytest.raises(IdentityError):
        GuardedBroker(FakeIB(["U1"]), allow_trading=True, expected_account_id="U1",
                      trading_mode="paper").preview_combo(intent)


# --- IB market state fails closed --------------------------------------------------------

def test_ib_market_state_10197_is_unavailable(rules, monkeypatch):
    import integrations.ibkr.option_quotes as oq

    quote = oq.MarketQuote(symbol="SPY", status=oq.STATUS_COMPETING_LIVE_SESSION,
                           errors=[oq.IbError(code=10197, message="competing")])
    monkeypatch.setattr(oq, "request_quote", lambda *a, **k: quote)
    ib = SimpleNamespace(qualifyContracts=lambda *c: list(c))
    s = IBMarketState(ib).snapshot(rules, held_legs=[], underlying="SPY")
    assert s.status == "unavailable" and s.reason == "ib_10197_competing_live_session"
    assert s.errors[0]["code"] == 10197


def test_ib_market_state_exception_is_unavailable(rules):
    def boom(*a):
        raise ConnectionError("gateway down")

    s = IBMarketState(SimpleNamespace(qualifyContracts=boom)).snapshot(rules, held_legs=[], underlying="SPY")
    assert s.status == "unavailable" and s.reason.startswith("ib_exception: ConnectionError")


def test_build_bag_uses_qualified_conids(rules):
    from integrations.ibkr.combo import build_bag

    intent, _ = build_entry(snap(), rules, strategy_name="x", idempotency_key="k")

    def qualify(*opts):
        for i, o in enumerate(opts):
            o.conId = 1000 + i
        return list(opts)

    bag = build_bag(SimpleNamespace(qualifyContracts=qualify), intent)
    assert [(l.conId, l.action) for l in bag.comboLegs] == [(1000, "SELL"), (1001, "BUY")]
    assert bag.secType == "BAG" and bag.symbol == "SPY"


# --- CLI ---------------------------------------------------------------------------------

def test_cli_dry_run_and_explain(tmp_path, capsys):
    db = str(tmp_path / "s.db")
    assert cli_main(["--db", db, "run", "--dry-run"]) == 0
    assert cli_main(["--db", db, "explain", "last"]) == 0
    out = capsys.readouterr().out
    assert "entered" in out and "OUTCOME: entered" in out
    assert cli_main(["--db", db, "run", "--dry-run", "--fixture", str(UNAVAIL)]) == 0
    assert cli_main(["--db", db, "list"]) == 0
    assert "market_data_unavailable" in capsys.readouterr().out


def test_cli_default_strategy_is_in_force():
    from core.cli import DEFAULT_STRATEGY
    assert DEFAULT_STRATEGY.endswith("us-large-cap-rr.yaml")


# --- kill switch blocks entries, not flatten ----------------------------------

def _kinds(lin, cid):
    return [a for a in lin.get_cycle(cid)["artifacts"] if a["kind"] == "kill_switch"]


def test_kill_latched_holds_and_blocks_entries(lin):
    assert dry(lin).outcome == "entered"
    lin.latch_kill(NAME, "dry_run", "manual: test")
    r = dry(lin)
    assert r.outcome == "held" and any(x.startswith("kill_switch_latched") for x in r.reasons)
    lin2 = Lineage(str(Path(lin.db_path).with_name("other.db")))
    lin2.latch_kill(NAME, "dry_run", "manual: test")
    r2 = dry(lin2)
    assert r2.outcome == "abstained" and r2.reasons[1] == "new entries blocked"
    assert lin2.orders_by_status(NAME, "dry_run", ("proposed", "submitted", "filled", "not_sent")) == []


def test_flatten_closes_position_even_when_latched(lin):
    assert dry(lin).outcome == "entered"
    lin.latch_kill(NAME, "dry_run", "manual: test")
    seeded = expected_option_positions(lin.open_positions(NAME, "dry_run"))
    r = run_cycle(STRAT, mode="dry_run", provider=FixtureMarketState(ENTRY), broker=SimBroker(seeded),
                  lineage=lin, allow_trading=True, flatten=True, now=SLOT_NOW)
    assert r.outcome == "exited" and r.reasons[0].startswith("manual_flatten")
    assert "exit ran while kill switch latched" in r.reasons
    assert _kinds(lin, r.cycle_id)[0]["payload"]["trigger"] == "manual_flatten"
    assert lin.open_positions(NAME, "dry_run") == []


def test_flatten_without_position_abstains(lin):
    r = run_cycle(STRAT, mode="dry_run", provider=FixtureMarketState(ENTRY), broker=SimBroker(),
                  lineage=lin, allow_trading=True, flatten=True, now=SLOT_NOW)
    assert r.outcome == "abstained" and r.reasons[0] == "flatten: no open strategy position"
    assert lin.open_positions(NAME, "dry_run") == []


def test_exit_drift_still_blocks(lin):
    assert dry(lin).outcome == "entered"
    lin.latch_kill(NAME, "dry_run", "manual: test")
    r = run_cycle(STRAT, mode="dry_run", provider=FixtureMarketState(ENTRY), broker=SimBroker({}),
                  lineage=lin, allow_trading=True, flatten=True, now=SLOT_NOW)
    assert r.outcome == "abstained" and r.reasons[0] == "reconcile_drift"
    assert len(lin.open_positions(NAME, "dry_run")) == 1


def test_non_offsetting_close_rejected_by_revalidate(lin, monkeypatch):
    import core.cycle as cyc_mod

    assert dry(lin).outcome == "entered"
    real = cyc_mod.build_exit

    def tampered(*a, **k):
        intent = real(*a, **k)
        legs = [l.model_copy(update={"action": "SELL"}) for l in intent.legs]
        return intent.model_copy(update={"legs": legs})

    monkeypatch.setattr(cyc_mod, "build_exit", tampered)
    seeded = expected_option_positions(lin.open_positions(NAME, "dry_run"))
    r = run_cycle(STRAT, mode="dry_run", provider=FixtureMarketState(ENTRY), broker=SimBroker(seeded),
                  lineage=lin, allow_trading=True, flatten=True, now=SLOT_NOW)
    assert r.outcome == "proposed_not_sent" and "not risk-reducing" in r.reasons[0]
    assert len(lin.open_positions(NAME, "dry_run")) == 1


class FakeIBHolding(FakeIB):
    def __init__(self, legs, accounts=("DU123",)):
        super().__init__(accounts)
        self._legs = legs

    def positions(self):
        out = []
        for l in self._legs:
            c = SimpleNamespace(secType="OPT", symbol="SPY", lastTradeDateOrContractMonth=l["expiry"],
                                right=l["right"], strike=l["strike"])
            out.append(SimpleNamespace(contract=c, position=1.0 if l["action"] == "BUY" else -1.0))
        return out


def _paper_position(lin):
    intent, _ = build_entry(snap(), load(STRAT).rules, strategy_name=NAME, idempotency_key="k")
    legs = [l.model_dump(mode="json") for l in intent.legs]
    lin.open_position(position_id="p-paper", strategy=NAME, mode="paper", cycle_id="c-x", legs=legs,
                      entry_price=intent.limit_price, quantity=1, max_loss_usd=intent.max_loss_usd)
    return legs


def test_paper_flatten_latched_goes_through_guard(lin, monkeypatch):
    monkeypatch.setenv("TRADING_MODE", "paper")
    monkeypatch.delenv("IB_GATEWAY_PORT", raising=False)
    legs = _paper_position(lin)
    lin.latch_kill(NAME, "paper", "manual: test")
    lin.record_fill(exec_id="epic0", idempotency_key=None, broker_order_id="x",
                    cycle_id=None, mode="paper", payload={"exec_id": "epic0"})
    ib = FakeIBHolding(legs)
    r = run_cycle(STRAT, mode="paper", provider=LiveIBFixture(ENTRY),
                  broker=IBExecution(ib, allow_trading=False, expected_account_id="DU123"), lineage=lin,
                  allow_trading=False, identity_check=lambda: "DU123", now=SLOT_NOW, flatten=True)
    assert r.outcome == "proposed_not_sent" and "Trading disabled" in r.reasons[0]
    assert "exit ran while kill switch latched" in r.reasons
    assert _kinds(lin, r.cycle_id)[0]["payload"]["action"] == "exit_allowed_while_latched"


def test_paper_flatten_live_account_refused(lin):
    legs = _paper_position(lin)
    lin.latch_kill(NAME, "paper", "manual: test")
    r = run_cycle(STRAT, mode="paper", provider=FixtureMarketState(ENTRY),
                  broker=IBExecution(FakeIBHolding(legs, ["U1"]), allow_trading=True, expected_account_id="U1"),
                  lineage=lin, allow_trading=True, identity_check=lambda: "U1", now=SLOT_NOW, flatten=True)
    assert r.outcome == "error" and "identity_failure" in r.reasons[0]
    assert len(lin.open_positions(NAME, "paper")) == 1


def test_cli_flatten_dry_run(tmp_path, capsys):
    db = str(tmp_path / "s.db")
    assert cli_main(["--db", db, "run", "--dry-run"]) == 0
    assert cli_main(["--db", db, "kill", "--mode", "dry_run", "--reason", "test"]) == 0
    assert cli_main(["--db", db, "flatten", "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "exited" in out and "manual_flatten" in out and "exit ran while kill switch latched" in out


def test_paper_reset_clears_open_snapshot_keeps_history(tmp_path, capsys):
    db = str(tmp_path / "s.db")
    assert cli_main(["--db", db, "run", "--dry-run"]) == 0
    lin = Lineage(db)
    lin.open_position(
        position_id="p-old-yaml", strategy="spy-defined-risk-rr", mode="dry_run",
        cycle_id="c-old", legs=[{"occ": "AAPL261120P00200000", "action": "SELL", "right": "P",
                                 "strike": 200, "expiry": "20261120"}],
        entry_price=1.0, quantity=1, max_loss_usd=None,
    )
    assert lin.open_positions(NAME, "dry_run")
    assert lin.open_positions("spy-defined-risk-rr", "dry_run")
    n_cycles = len(lin.list_cycles(50))
    n_fills = len(lin.fill_exec_ids("dry_run"))
    assert cli_main(["--db", db, "paper-reset-snapshot", "--mode", "dry_run"]) == 2
    assert cli_main(["--db", db, "paper-reset-snapshot", "--mode", "dry_run", "--confirm", "yes"]) == 0
    out = capsys.readouterr().out
    assert "paper_reset" in out
    assert lin.open_positions(NAME, "dry_run") == []
    assert lin.open_positions("spy-defined-risk-rr", "dry_run") == []
    assert len(lin.list_cycles(50)) == n_cycles + 1
    assert len(lin.fill_exec_ids("dry_run")) == n_fills
    assert dry(lin).outcome == "entered"
