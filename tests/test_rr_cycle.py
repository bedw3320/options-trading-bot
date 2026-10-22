"""Deterministic SPY risk-reversal cycle: schema, signals, construction, lineage,
market-state fail-closed, reconcile, kill switch, paper enforcement. No Gateway."""

from __future__ import annotations

import copy
import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml
from pydantic import ValidationError

from core.brokers import IBExecution, SimBroker
from core.cli import explain, main as cli_main
from core.cycle import run_cycle
from core.guarded_broker import GuardedBroker, GuardedReject
from core.identity import IdentityError
from core.market_state import FixtureMarketState, IBMarketState
from core.reconcile import expected_option_positions
from core.rr_rules import build_entry, evaluate_exit, underlying_stop_level
from core.signals import compute_signals, failing_required, iv_at_abs_delta, realized_vol, skew_percentile
from core.strategy_loader import load
from schemas.cycle import MarketSnapshot, OptionRow
from schemas.strategy import StrategyConfig
from utils.lineage import Lineage

ROOT = Path(__file__).resolve().parents[1]
STRAT = ROOT / "strategies/active/spy-defined-risk-rr.yaml"
FIX = ROOT / "tests/fixtures"
ENTRY = FIX / "spy_snapshot_entry.json"
FLAT = FIX / "spy_snapshot_flat_skew.json"
UNAVAIL = FIX / "spy_snapshot_unavailable.json"
RTH_NOW = lambda: datetime(2026, 10, 19, 15, 0, tzinfo=timezone.utc)  # 11:00 ET Monday  # noqa: E731


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


def dry(lin, path=ENTRY, broker=None, **over):
    seeded = expected_option_positions(lin.open_positions("spy-defined-risk-rr", "dry_run"))
    return run_cycle(STRAT, mode="dry_run", provider=FixtureMarketState(path, overrides=over),
                     broker=broker or SimBroker(seeded), lineage=lin, allow_trading=True)


# --- strategy schema ---------------------------------------------------------

def _raw():
    return yaml.safe_load(STRAT.read_text())


def test_active_strategy_validates(rules):
    assert rules.underlying == "SPY"
    assert rules.sizing.contracts == 1 and rules.sizing.max_open_positions == 1
    assert rules.execution.paper_only is True and rules.execution.required_account_prefix == "DU"
    assert rules.structure.dte_min == 30 and rules.structure.dte_max == 45


@pytest.mark.parametrize("path,value", [
    (("execution", "paper_only"), False),
    (("sizing", "contracts"), 2),
    (("sizing", "max_loss_usd"), 10000),
    (("sizing", "max_open_positions"), 2),
    (("structure", "dte_target"), 60),
    (("execution", "required_account_prefix"), "U"),
])
def test_schema_rejects_unsafe_values(path, value):
    raw = _raw()
    raw["rules"][path[0]][path[1]] = value
    with pytest.raises(ValidationError):
        StrategyConfig.model_validate(raw)


def test_examples_still_load_without_rules():
    for p in (ROOT / "strategies/examples").glob("*.yaml"):
        assert load(p).rules is None


# --- signals ------------------------------------------------------------------

def test_signals_pass_on_rich_skew(rules):
    sigs = compute_signals(snap(), rules)
    by = {s.name: s for s in sigs}
    assert by["rr25"].value <= -0.05 and by["rr25"].passed
    assert by["put_call_iv_ratio"].passed and by["atm_iv_minus_rv"].passed
    assert by["rr25_percentile"].passed is None and not by["rr25_percentile"].required
    assert failing_required(sigs) == []


def test_signals_fail_on_flat_skew(rules):
    names = {s.name for s in failing_required(compute_signals(snap(FLAT), rules))}
    assert "rr25" in names


def test_event_blackout(rules):
    sigs = compute_signals(snap(as_of="2026-10-26T15:00:00+00:00"), rules)  # 2 days before FOMC 10-28
    assert {s.name for s in failing_required(sigs)} == {"event_blackout"}


def test_missing_greeks_fail_closed(rules):
    s = snap()
    for o in s.options:
        o.delta = None
    assert {"rr25", "atm_iv_minus_rv"} <= {x.name for x in failing_required(compute_signals(s, rules))}


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
    """Oct 22 2026 shadow cycle c-20261022T141504Z-c71a41: nearest 745P fails, 740P would pass."""
    put_lo = _opt("P", 740, -0.2328, 0.1709)
    put_hi = _opt("P", 745, -0.2640, 0.1646)
    got = iv_at_abs_delta([put_lo, put_hi], "P", 0.25)
    assert got is not None and got.method == "interpolated"
    w_hi = (0.25 - 0.2328) / (0.2640 - 0.2328)
    assert got.iv == pytest.approx(0.1709 * (1 - w_hi) + 0.1646 * w_hi)
    assert got.rows[0].strike == 740 and got.rows[1].strike == 745
    assert got.weights[1] == pytest.approx(w_hi)


def test_rr25_interpolates_oct22_example_and_logs_weights(rules):
    # Nearest listed put is 745P (rr25 = -0.0463, fail). 740P would be -0.0526.
    # Interpolated put IV sits between them; lineage note records both strikes/weights.
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
    assert f"{put_iv:.6f}" in (by["put_call_iv_ratio"].note or "")


def test_iv_at_abs_delta_exact_and_nearest_fallback():
    exact = _opt("P", 740, -0.25, 0.17)
    assert iv_at_abs_delta([exact], "P", 0.25).method == "exact"
    only_rich = [_opt("P", 745, -0.30, 0.16), _opt("P", 750, -0.35, 0.15)]
    fb = iv_at_abs_delta(only_rich, "P", 0.25)
    assert fb.method == "nearest" and fb.rows[0].strike == 745
    assert iv_at_abs_delta([], "P", 0.25) is None


# --- construction / exits ---------------------------------------------------------

def test_build_entry_defined_risk(rules):
    intent, why = build_entry(snap(), rules, strategy_name="x", idempotency_key="k")
    assert intent is not None, why
    sp, wing, call = intent.legs
    assert (sp.action, sp.right, wing.action, wing.right, call.action, call.right) == (
        "SELL", "P", "BUY", "P", "BUY", "C")
    assert sp.strike - wing.strike == 20
    assert 0.20 <= abs(sp.delta) <= 0.25 and 0.10 <= call.delta <= 0.30
    assert intent.limit_price <= rules.structure.max_net_debit
    assert intent.max_loss_usd == pytest.approx((20 + intent.limit_price) * 100)
    assert intent.max_loss_usd <= rules.sizing.max_loss_usd and intent.quantity == 1


def test_build_entry_abstains_on_missing_oi_and_cap(rules):
    s = snap()
    for o in s.options:
        o.open_interest = None
    intent, why = build_entry(s, rules, strategy_name="x", idempotency_key="k")
    assert intent is None and "open interest unavailable" in " ".join(why)
    tight = rules.model_copy(update={"sizing": rules.sizing.model_copy(update={"max_loss_usd": 1000})})
    intent, why = build_entry(snap(), tight, strategy_name="x", idempotency_key="k")
    assert intent is None and "max loss" in why[0]


def _position(intent, entry):
    return {"position_id": "p1", "legs": [l.model_dump() for l in intent.legs], "entry_price": entry, "quantity": 1}


def test_exit_triggers(rules):
    intent, _ = build_entry(snap(), rules, strategy_name="x", idempotency_key="k")
    pos = _position(intent, intent.limit_price)
    marks = {l.occ: (l.bid + l.ask) / 2 for l in intent.legs}
    assert evaluate_exit(pos, snap(held_marks=marks), rules)[0] is None
    assert evaluate_exit(pos, snap(held_marks=marks, as_of="2026-10-30T15:00:00+00:00"), rules)[0] == "time_stop"
    assert evaluate_exit(pos, snap(held_marks=marks, underlying_price=700.0), rules)[0] == "underlying_stop"
    assert evaluate_exit({**pos, "entry_price": intent.limit_price + 13}, snap(held_marks=marks), rules)[0] == "stop_loss"
    assert evaluate_exit({**pos, "entry_price": intent.limit_price - 11}, snap(held_marks=marks), rules)[0] == "take_profit"
    trig, _, why = evaluate_exit(pos, snap(held_marks={}), rules)
    assert trig is None and "not evaluable" in why[0]


def test_underlying_stop_stays_above_long_put(rules):
    # Typical $20 wing: 3% of the short strike sits below the long put.
    assert 735 * 0.97 < 715
    level = underlying_stop_level(735.0, 715.0, 3.0)
    assert level == pytest.approx(720.0)  # 715 + 0.25 * 20
    assert level > 715.0
    # Wide wing: 3% of spot still applies and remains above the long put.
    wide = underlying_stop_level(735.0, 635.0, 3.0)
    assert wide == pytest.approx(735.0 * 0.97)
    assert wide > 635.0

    intent, why = build_entry(snap(), rules, strategy_name="x", idempotency_key="k")
    assert intent is not None, why
    short = next(l for l in intent.legs if l.action == "SELL" and l.right == "P")
    wing = next(l for l in intent.legs if l.action == "BUY" and l.right == "P")
    pos = _position(intent, intent.limit_price)
    marks = {l.occ: (l.bid + l.ask) / 2 for l in intent.legs}
    stop = underlying_stop_level(short.strike, wing.strike, rules.exits.underlying_stop_pct_below_short_put)
    assert stop > wing.strike
    assert short.strike - wing.strike == 20
    assert evaluate_exit(pos, snap(held_marks=marks, underlying_price=stop - 0.01), rules)[0] == "underlying_stop"
    assert evaluate_exit(pos, snap(held_marks=marks, underlying_price=stop + 0.01), rules)[0] is None
    # Dollar and time stops unchanged (see test_exit_triggers).


def _seed_rr25(lin: Lineage, cycle_id: str, value: float, started_at: str, mode: str = "dry_run"):
    lin.start_cycle(strategy=NAME, strategy_version="0.1.0", strategy_sha256="x",
                    mode=mode, cycle_id=cycle_id, started_at=started_at)
    lin.record(cycle_id, "signals", {"signals": [{"name": "rr25", "value": value}]})
    lin.end_cycle(cycle_id, "abstained", ["seed"])


def test_signal_history_one_rr25_per_et_day(lin):
    # Six same-morning cycles would have filled n=6 under per-cycle history.
    _seed_rr25(lin, "c-d1a", -0.040, "2026-10-19T14:15:00+00:00")  # 10:15 ET
    _seed_rr25(lin, "c-d1b", -0.041, "2026-10-19T14:30:00+00:00")
    _seed_rr25(lin, "c-d1c", -0.042, "2026-10-19T15:00:00+00:00")
    _seed_rr25(lin, "c-d1d", -0.043, "2026-10-19T15:15:00+00:00")
    _seed_rr25(lin, "c-d1e", -0.044, "2026-10-19T15:30:00+00:00")
    _seed_rr25(lin, "c-d1f", -0.060, "2026-10-19T16:00:00+00:00")  # latest Oct 19
    _seed_rr25(lin, "c-d2a", -0.050, "2026-10-20T14:15:00+00:00")
    _seed_rr25(lin, "c-d2b", -0.055, "2026-10-20T19:00:00+00:00")  # latest Oct 20
    assert lin.signal_history(NAME, "dry_run", "rr25") == [-0.060, -0.055]


# --- full dry-run cycles + lineage ----------------------------------------------------

def test_dry_run_full_cycle_lineage(lin):
    r = dry(lin)
    assert r.outcome == "entered"
    cyc = lin.get_cycle(r.cycle_id)
    kinds = [a["kind"] for a in cyc["artifacts"]]
    for k in ("inputs", "reconcile", "market_snapshot", "signals", "decision", "intent", "order", "fill"):
        assert k in kinds, k
    assert len(lin.open_positions("spy-defined-risk-rr", "dry_run")) == 1
    text = explain(cyc)
    assert "OUTCOME: entered" in text and "PASS rr25" in text and "SELL SPY261120P" in text
    # second cycle: max one position -> manage, not re-enter
    r2 = dry(lin)
    assert r2.outcome == "held"
    assert len(lin.open_positions("spy-defined-risk-rr", "dry_run")) == 1


def test_dry_run_exit_closes_position(lin):
    assert dry(lin).outcome == "entered"
    r = dry(lin, underlying_price=700.0)
    assert r.outcome == "exited" and "underlying_stop" in r.reasons[0]
    assert lin.open_positions("spy-defined-risk-rr", "dry_run") == []
    assert dry(lin).outcome == "abstained"  # max_entries_per_day = 1


def test_unavailable_data_abstains_with_reason(lin):
    r = dry(lin, UNAVAIL)
    assert r.outcome == "abstained"
    assert r.reasons[0] == "market_data_unavailable: ib_10197_competing_live_session"
    cyc = lin.get_cycle(r.cycle_id)
    assert not any(a["kind"] in ("intent", "order") for a in cyc["artifacts"])


def test_flat_skew_abstains(lin):
    r = dry(lin, FLAT)
    assert r.outcome == "abstained" and r.reasons[0].startswith("signal rr25=")


def test_kill_switch_latches_and_rearms(lin):
    lin.latch_kill("spy-defined-risk-rr", "dry_run", "manual: test")
    r = dry(lin)
    assert r.outcome == "abstained" and r.reasons[0].startswith("kill_switch_latched")
    assert lin.rearm("spy-defined-risk-rr", "dry_run")
    assert dry(lin).outcome == "entered"


def test_reconcile_drift_latches_kill(lin):
    r = dry(lin, broker=SimBroker({"SPY261120P00700000": -3}))
    assert r.outcome == "abstained" and r.reasons[0] == "reconcile_drift"
    assert lin.kill_state("spy-defined-risk-rr", "dry_run")


def test_consecutive_errors_latch(lin):
    class Boom:
        def snapshot(self, rules, *, held_legs):
            raise RuntimeError("boom")

    for _ in range(3):
        r = run_cycle(STRAT, mode="dry_run", provider=Boom(), broker=SimBroker(), lineage=lin, allow_trading=True)
        assert r.outcome == "error"
    assert "consecutive error" in lin.kill_state("spy-defined-risk-rr", "dry_run")["reason"]


def test_unfilled_order_is_cancelled(lin):
    r = dry(lin, broker=SimBroker(fill=False))
    assert r.outcome == "abstained" and "cancelled" in r.reasons[0]
    assert lin.open_positions("spy-defined-risk-rr", "dry_run") == []
    assert lin.orders_by_status("spy-defined-risk-rr", "dry_run", ("cancelled",))


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


def paper(lin, ib, *, allow, account="DU123", now=RTH_NOW):
    return run_cycle(STRAT, mode="paper", provider=FixtureMarketState(ENTRY),
                     broker=IBExecution(ib, allow_trading=allow, expected_account_id=account),
                     lineage=lin, allow_trading=allow, identity_check=lambda: account, now=now)


def test_paper_live_account_hard_fails(lin):
    r = paper(lin, FakeIB(), allow=True, account="U9999")
    assert r.outcome == "error" and "identity_failure" in r.reasons[0]
    assert lin.kill_state("spy-defined-risk-rr", "paper")


def test_paper_without_allow_trading_journals_only(lin, monkeypatch):
    monkeypatch.setenv("TRADING_MODE", "paper")
    monkeypatch.delenv("IB_GATEWAY_PORT", raising=False)
    r = paper(lin, FakeIB(), allow=False)
    assert r.outcome == "proposed_not_sent" and "Trading disabled" in r.reasons[0]
    assert lin.orders_by_status("spy-defined-risk-rr", "paper", ("not_sent",))


def test_paper_market_closed_abstains(lin):
    r = paper(lin, FakeIB(), allow=False, now=lambda: datetime(2026, 10, 18, 15, 0, tzinfo=timezone.utc))
    assert r.outcome == "abstained" and r.reasons[0].startswith("market_closed")


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
    s = IBMarketState(ib).snapshot(rules, held_legs=[])
    assert s.status == "unavailable" and s.reason == "ib_10197_competing_live_session"
    assert s.errors[0]["code"] == 10197


def test_ib_market_state_exception_is_unavailable(rules):
    def boom(*a):
        raise ConnectionError("gateway down")

    s = IBMarketState(SimpleNamespace(qualifyContracts=boom)).snapshot(rules, held_legs=[])
    assert s.status == "unavailable" and s.reason.startswith("ib_exception: ConnectionError")


def test_build_bag_uses_qualified_conids(rules):
    from integrations.ibkr.combo import build_bag

    intent, _ = build_entry(snap(), rules, strategy_name="x", idempotency_key="k")

    def qualify(*opts):
        for i, o in enumerate(opts):
            o.conId = 1000 + i
        return list(opts)

    bag = build_bag(SimpleNamespace(qualifyContracts=qualify), intent)
    assert [(l.conId, l.action) for l in bag.comboLegs] == [(1000, "SELL"), (1001, "BUY"), (1002, "BUY")]
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


# --- kill switch blocks entries, not risk-reducing exits ----------------------------------

NAME = "spy-defined-risk-rr"


def _kinds(lin, cid):
    return [a for a in lin.get_cycle(cid)["artifacts"] if a["kind"] == "kill_switch"]


def test_kill_latched_still_runs_rule_exit(lin):
    assert dry(lin).outcome == "entered"
    lin.latch_kill(NAME, "dry_run", "manual: test")
    r = dry(lin, underlying_price=700.0)
    assert r.outcome == "exited" and "underlying_stop" in r.reasons[0]
    assert "exit ran while kill switch latched" in r.reasons
    cyc = lin.get_cycle(r.cycle_id)
    assert "exit ran while kill switch latched" in cyc["reasons"]
    ks = _kinds(lin, r.cycle_id)
    assert ks and ks[0]["payload"]["action"] == "exit_allowed_while_latched"
    assert ks[0]["payload"]["trigger"] == "underlying_stop"
    assert lin.open_positions(NAME, "dry_run") == []
    assert lin.kill_state(NAME, "dry_run")  # still latched until rearm


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


def test_daily_loss_latch_blocks_entry(lin):
    lin.open_position(position_id="p-old", strategy=NAME, mode="dry_run", cycle_id="c0", legs=[],
                      entry_price=0.5, quantity=1, max_loss_usd=2000)
    lin.close_position("p-old", cycle_id="c0", exit_price=-16.0, trigger="stop_loss")  # -$1,650
    r = dry(lin)
    assert r.outcome == "abstained" and "new entries blocked" in r.reasons
    assert "daily realized loss" in lin.kill_state(NAME, "dry_run")["reason"]


def test_flatten_closes_position_even_when_latched(lin):
    assert dry(lin).outcome == "entered"
    lin.latch_kill(NAME, "dry_run", "manual: test")
    seeded = expected_option_positions(lin.open_positions(NAME, "dry_run"))
    r = run_cycle(STRAT, mode="dry_run", provider=FixtureMarketState(ENTRY), broker=SimBroker(seeded),
                  lineage=lin, allow_trading=True, flatten=True)
    assert r.outcome == "exited" and r.reasons[0].startswith("manual_flatten")
    assert "exit ran while kill switch latched" in r.reasons
    assert _kinds(lin, r.cycle_id)[0]["payload"]["trigger"] == "manual_flatten"
    assert lin.open_positions(NAME, "dry_run") == []


def test_flatten_without_position_abstains(lin):
    r = run_cycle(STRAT, mode="dry_run", provider=FixtureMarketState(ENTRY), broker=SimBroker(),
                  lineage=lin, allow_trading=True, flatten=True)
    assert r.outcome == "abstained" and r.reasons[0] == "flatten: no open strategy position"
    assert lin.open_positions(NAME, "dry_run") == []


def test_exit_drift_still_blocks(lin):
    assert dry(lin).outcome == "entered"
    lin.latch_kill(NAME, "dry_run", "manual: test")
    r = run_cycle(STRAT, mode="dry_run", provider=FixtureMarketState(ENTRY), broker=SimBroker({}),
                  lineage=lin, allow_trading=True, flatten=True)
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
                  lineage=lin, allow_trading=True, flatten=True)
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
    ib = FakeIBHolding(legs)
    r = run_cycle(STRAT, mode="paper", provider=FixtureMarketState(ENTRY),
                  broker=IBExecution(ib, allow_trading=False, expected_account_id="DU123"), lineage=lin,
                  allow_trading=False, identity_check=lambda: "DU123", now=RTH_NOW, flatten=True)
    # Exit was attempted while latched, but the GuardedBroker refused to send (trading disabled).
    assert r.outcome == "proposed_not_sent" and "Trading disabled" in r.reasons[0]
    assert "exit ran while kill switch latched" in r.reasons
    assert _kinds(lin, r.cycle_id)[0]["payload"]["action"] == "exit_allowed_while_latched"


def test_paper_flatten_live_account_refused(lin):
    legs = _paper_position(lin)
    lin.latch_kill(NAME, "paper", "manual: test")
    r = run_cycle(STRAT, mode="paper", provider=FixtureMarketState(ENTRY),
                  broker=IBExecution(FakeIBHolding(legs, ["U1"]), allow_trading=True, expected_account_id="U1"),
                  lineage=lin, allow_trading=True, identity_check=lambda: "U1", now=RTH_NOW, flatten=True)
    assert r.outcome == "error" and "identity_failure" in r.reasons[0]
    assert len(lin.open_positions(NAME, "paper")) == 1


def test_cli_flatten_dry_run(tmp_path, capsys):
    db = str(tmp_path / "s.db")
    assert cli_main(["--db", db, "run", "--dry-run"]) == 0
    assert cli_main(["--db", db, "kill", "--mode", "dry_run", "--reason", "test"]) == 0
    assert cli_main(["--db", db, "flatten", "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "exited" in out and "manual_flatten" in out and "exit ran while kill switch latched" in out
