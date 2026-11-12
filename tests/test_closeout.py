"""Epic 4: flatten, reconcile mismatch, proposed_not_sent, fills, debrief.

Fakes only. No Gateway, no network.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from core.brokers import IBExecution, SimBroker
from core.cli import main as cli_main
from core.closeout import persistable_fill
from core.cycle import run_cycle
from core.entry_window import DRY_RUN_NOW
from core.market_state import FixtureMarketState
from core.reconcile import expected_option_positions, reconcile
from core.rr_rules import build_entry, evaluate_exit
from core.strategy_loader import load
from schemas.cycle import MarketSnapshot
from utils.lineage import Lineage

ROOT = Path(__file__).resolve().parents[1]
STRAT = ROOT / "strategies/active/us-large-cap-rr.yaml"
ENTRY = ROOT / "tests/fixtures/spy_snapshot_entry.json"
NAME = "us-large-cap-rr"
SLOT_NOW = lambda: DRY_RUN_NOW  # noqa: E731


@pytest.fixture
def rules():
    return load(STRAT).rules


@pytest.fixture
def lin(tmp_path):
    return Lineage(str(tmp_path / "state.db"))


def snap(**over) -> MarketSnapshot:
    raw = __import__("json").loads(ENTRY.read_text())
    raw.update(over)
    return MarketSnapshot.model_validate(raw)


def dry(lin, broker=None, **over):
    seeded = expected_option_positions(lin.open_positions(NAME, "dry_run"))
    return run_cycle(
        STRAT, mode="dry_run", provider=FixtureMarketState(ENTRY, overrides=over),
        broker=broker or SimBroker(seeded), lineage=lin, allow_trading=True, now=SLOT_NOW,
    )


def _position(intent, entry):
    return {
        "position_id": "p1", "opened_cycle_id": "c-open",
        "legs": [l.model_dump() for l in intent.legs],
        "entry_price": entry, "quantity": 1,
    }


class ExplodingBroker(SimBroker):
    def place(self, intent, *, revalidate):
        raise AssertionError("must not place")


class TimedFillBroker(SimBroker):
    def place(self, intent, *, revalidate):
        rec = super().place(intent, revalidate=revalidate)
        for f in rec.get("fills") or []:
            f["exec_id"] = "00025b49.6ac58ef0.01.01"
            f["qty"] = f.get("shares")
            f["time"] = "20261006 13:35:19"
        return rec


class NoExecBroker(SimBroker):
    def place(self, intent, *, revalidate):
        rec = super().place(intent, revalidate=revalidate)
        rec["fills"] = [{"price": 1.25, "shares": 1, "qty": 1}]
        self._execs = list(rec["fills"])
        return rec


class FakeIB:
    def __init__(self, accounts=("DUT116016",)):
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


class FakeIBHolding(FakeIB):
    def __init__(self, legs, accounts=("DUT116016",), account="DUT116016"):
        super().__init__(accounts)
        self._legs = legs
        self._account = account

    def positions(self):
        out = []
        for l in self._legs:
            c = SimpleNamespace(
                secType="OPT", symbol="SPY",
                lastTradeDateOrContractMonth=l["expiry"], right=l["right"], strike=l["strike"],
            )
            out.append(SimpleNamespace(
                contract=c, position=1.0 if l["action"] == "BUY" else -1.0, account=self._account,
            ))
        return out


def test_in_force_has_no_coded_exits_or_daily_loss(rules):
    assert rules.exits.automated is False
    assert rules.exits.time_stop_dte is None
    assert rules.exits.stop_loss_usd is None
    assert rules.exits.take_profit_usd is None
    assert rules.kill_switch.daily_loss_limit_usd is None


def test_exit_rule_evaluation_always_holds(rules):
    intent, _ = build_entry(snap(), rules, strategy_name="x", idempotency_key="k")
    pos = _position(intent, intent.limit_price)
    marks = {l.occ: (l.bid + l.ask) / 2 for l in intent.legs}
    assert evaluate_exit(pos, snap(held_marks=marks), rules)[0] is None
    assert evaluate_exit(pos, snap(held_marks=marks, as_of="2026-10-30T15:00:00+00:00"), rules)[0] is None
    assert evaluate_exit(pos, snap(held_marks=marks, underlying_price=700.0), rules)[0] is None
    assert evaluate_exit({**pos, "entry_price": intent.limit_price + 13}, snap(held_marks=marks), rules)[0] is None
    assert evaluate_exit({**pos, "entry_price": intent.limit_price - 11}, snap(held_marks=marks), rules)[0] is None


def test_mark_to_market_per_leg_and_net(lin, rules):
    from core.closeout import mark_to_market

    assert dry(lin).outcome == "entered"
    pos = lin.open_positions(NAME, "dry_run")[0]
    s = FixtureMarketState(ENTRY).snapshot(rules, held_legs=pos["legs"])
    mtm = mark_to_market(pos, s, rules, daily_realized_pnl_usd=0.0)
    assert mtm.underlying == "SPY"
    assert mtm.underlying_price is not None
    assert mtm.dte is not None
    assert len(mtm.legs) == 2
    assert all(leg.mark is not None for leg in mtm.legs)
    assert mtm.net_mark == pytest.approx(sum(leg.signed_mark for leg in mtm.legs))
    assert mtm.unrealized_pnl_usd == pytest.approx((mtm.net_mark - pos["entry_price"]) * 100)
    assert mtm.daily_loss_limit_usd is None
    assert mtm.daily_loss_breach is False


def test_realized_loss_does_not_kill(lin):
    assert dry(lin).outcome == "entered"
    lin.open_position(position_id="p-old", strategy=NAME, mode="dry_run", cycle_id="c0",
                      legs=[], entry_price=0.5, quantity=1, max_loss_usd=None)
    lin.close_position("p-old", cycle_id="c0", exit_price=-16.0, trigger="manual_flatten")
    r = dry(lin)
    assert r.outcome == "held"
    mtm = next(a["payload"] for a in lin.get_cycle(r.cycle_id)["artifacts"] if a["kind"] == "mark_to_market")
    assert mtm["daily_loss_breach"] is False
    assert mtm["daily_loss_limit_usd"] is None
    assert lin.kill_state(NAME, "dry_run") is None


def test_reconcile_flags_sqlite_vs_broker_mismatch(lin, rules):
    intent, _ = build_entry(snap(), rules, strategy_name=NAME, idempotency_key="k")
    legs = [l.model_dump(mode="json") for l in intent.legs]
    lin.open_position(position_id="p-x", strategy=NAME, mode="dry_run", cycle_id="c-x",
                      legs=legs, entry_price=intent.limit_price, quantity=1, max_loss_usd=None)
    rec = reconcile(SimBroker({}), lin, strategy=NAME, mode="dry_run", underlying=None,
                    account_id="DUT116016")
    assert rec["ok"] is False
    assert rec["mismatch"] is True
    assert rec["account_id"] == "DUT116016"
    assert rec["expected"]
    assert rec["broker"] == {}
    assert any("expected" in d and "broker" in d for d in rec["drift"])


def test_ib_execution_reads_configured_account_only(monkeypatch):
    monkeypatch.setenv("TRADING_MODE", "paper")
    monkeypatch.setenv("IB_ACCOUNT_ID", "DUT116016")
    monkeypatch.delenv("IB_GATEWAY_PORT", raising=False)
    spy_put = SimpleNamespace(secType="OPT", symbol="SPY", lastTradeDateOrContractMonth="20261120",
                              right="P", strike=700.0)
    spy_call = SimpleNamespace(secType="OPT", symbol="SPY", lastTradeDateOrContractMonth="20261120",
                               right="C", strike=800.0)
    ib = FakeIB()
    ib.positions = lambda: [
        SimpleNamespace(contract=spy_put, position=-1.0, account="DUT116016"),
        SimpleNamespace(contract=spy_call, position=2.0, account="DUOTHER"),
        SimpleNamespace(contract=SimpleNamespace(secType="OPT", symbol="AAPL",
                                                 lastTradeDateOrContractMonth="20261120",
                                                 right="P", strike=200.0),
                        position=-1.0, account="DUT116016"),
    ]
    got = IBExecution(ib, allow_trading=False, expected_account_id="DUT116016").option_positions(None)
    assert got == {"SPY261120P00700000": -1.0, "AAPL261120P00200000": -1.0}
    spy_only = IBExecution(ib, allow_trading=False, expected_account_id="DUT116016").option_positions("SPY")
    assert spy_only == {"SPY261120P00700000": -1.0}


def test_cboe_shadow_flatten_is_proposed_not_sent(lin):
    assert dry(lin).outcome == "entered"
    seeded = expected_option_positions(lin.open_positions(NAME, "dry_run"))
    r = run_cycle(
        STRAT, mode="dry_run",
        provider=FixtureMarketState(ENTRY),
        broker=ExplodingBroker(seeded), lineage=lin, allow_trading=True, data_source="cboe",
        flatten=True, now=SLOT_NOW,
    )
    assert r.outcome == "proposed_not_sent"
    assert "shadow_record_only" in r.reasons[0]
    assert lin.open_positions(NAME, "dry_run")
    assert lin.fills_for_cycle(r.cycle_id) == []
    assert lin.get_debrief(r.cycle_id) is None
    kinds = [a["kind"] for a in lin.get_cycle(r.cycle_id)["artifacts"]]
    assert "mark_to_market" in kinds
    assert "fill" not in kinds
    assert next(a for a in lin.get_cycle(r.cycle_id)["artifacts"] if a["kind"] == "order")["payload"]["sent"] is False


def test_paper_flatten_without_live_ib_is_proposed_not_sent(lin, monkeypatch):
    monkeypatch.setenv("TRADING_MODE", "paper")
    monkeypatch.setenv("IB_ACCOUNT_ID", "DUT116016")
    monkeypatch.delenv("IB_GATEWAY_PORT", raising=False)
    intent, _ = build_entry(snap(), load(STRAT).rules, strategy_name=NAME, idempotency_key="k")
    legs = [l.model_dump(mode="json") for l in intent.legs]
    lin.open_position(position_id="p-paper", strategy=NAME, mode="paper", cycle_id="c-x",
                      legs=legs, entry_price=intent.limit_price, quantity=1, max_loss_usd=None)
    r = run_cycle(
        STRAT, mode="paper",
        provider=FixtureMarketState(ENTRY),
        broker=IBExecution(FakeIBHolding(legs), allow_trading=False, expected_account_id="DUT116016"),
        lineage=lin, allow_trading=False, identity_check=lambda: "DUT116016", now=SLOT_NOW,
        flatten=True,
    )
    assert r.outcome == "proposed_not_sent"
    assert "paper_send_blocked" in r.reasons[0] or "not live IBKR" in r.reasons[0]
    assert lin.open_positions(NAME, "paper")
    assert lin.fills_for_cycle(r.cycle_id) == []
    assert lin.get_debrief(r.cycle_id) is None


def test_never_synthesize_a_fill(lin):
    r = dry(lin, broker=NoExecBroker())
    assert r.outcome == "entered"
    assert lin.fills_for_cycle(r.cycle_id) == []
    fill_art = next(a["payload"] for a in lin.get_cycle(r.cycle_id)["artifacts"] if a["kind"] == "fill")
    assert fill_art["fills"] == []


def test_persist_ib_shaped_fill_with_time_utc_and_debrief(lin):
    assert dry(lin).outcome == "entered"
    opened = lin.open_positions(NAME, "dry_run")[0]
    opened_cycle = opened["opened_cycle_id"]
    seeded = expected_option_positions([opened])
    r = run_cycle(
        STRAT, mode="dry_run",
        provider=FixtureMarketState(ENTRY),
        broker=TimedFillBroker(seeded), lineage=lin, allow_trading=True,
        flatten=True, now=SLOT_NOW,
    )
    assert r.outcome == "exited"
    fills = lin.fills_for_cycle(r.cycle_id)
    assert len(fills) == 1
    payload = fills[0]["payload"]
    assert payload["exec_id"] == "00025b49.6ac58ef0.01.01"
    assert payload["price"] is not None
    assert payload["qty"] == 1
    assert payload["time_utc"] == "2026-10-06T13:35:19+00:00"
    assert payload["time_et"].startswith("2026-10-06T09:35:19")
    assert payload["opened_cycle_id"] == opened_cycle
    debrief = lin.get_debrief(r.cycle_id)
    assert debrief is not None
    assert debrief["opened_cycle_id"] == opened_cycle
    assert debrief["closed_cycle_id"] == r.cycle_id
    assert debrief["exit_trigger"] == "manual_flatten"
    assert debrief["payload"]["entry_reason"]
    assert debrief["payload"]["exit_reason"]
    assert debrief["realized_pnl_usd"] == debrief["payload"]["realized_pnl_usd"]
    assert debrief["holding_period_seconds"] >= 0
    assert lin.get_debrief(opened_cycle)["closed_cycle_id"] == r.cycle_id


def test_persistable_fill_requires_exec_id():
    assert persistable_fill({"price": 1, "qty": 1, "time": "20261006 13:35:19"}) is None
    rec = persistable_fill({"exec_id": "e1", "price": 2.5, "shares": 1, "time": "20261006 13:35:19"})
    assert rec["qty"] == 1
    assert rec["time_utc"] == "2026-10-06T13:35:19+00:00"


def test_cli_debrief_after_dry_exit(tmp_path, capsys):
    db = str(tmp_path / "s.db")
    assert cli_main(["--db", db, "run", "--dry-run"]) == 0
    assert cli_main(["--db", db, "flatten", "--dry-run"]) == 0
    assert cli_main(["--db", db, "debrief", "last"]) == 0
    out = capsys.readouterr().out
    assert "debrief cycle=" in out and "manual_flatten" in out
