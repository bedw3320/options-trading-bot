"""Structured decision records: every cycle, every mode, not-acting is a decision.

Fakes only. No Gateway, no orders to a real broker.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from core.brokers import IBExecution, SimBroker
from core.cli import explain, main as cli_main
from core.cycle import run_cycle
from core.decision_record import catalog_complete, recording_enabled, replay_stored
from core.gates import (
    CONSTRUCTION_GATES,
    CYCLE_GATES,
    EXIT_GATES,
    RANKING_DESCRIPTION,
    evaluate_construction,
    replay_fingerprint,
)
from core.market_state import FixtureMarketState
from core.reconcile import expected_option_positions
from core.rr_rules import build_entry
from core.strategy_loader import load
from schemas.cycle import MarketSnapshot
from schemas.decision import DECISION_SCHEMA_VERSION, GATE_CATALOG_VERSION
from utils.lineage import Lineage

ROOT = Path(__file__).resolve().parents[1]
STRAT = ROOT / "strategies/active/spy-defined-risk-rr.yaml"
FIX = ROOT / "tests/fixtures"
ENTRY = FIX / "spy_snapshot_entry.json"
FLAT = FIX / "spy_snapshot_flat_skew.json"
UNAVAIL = FIX / "spy_snapshot_unavailable.json"
NAME = "spy-defined-risk-rr"
RTH_NOW = lambda: datetime(2026, 10, 19, 15, 0, tzinfo=timezone.utc)  # noqa: E731


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
    seeded = expected_option_positions(lin.open_positions(NAME, "dry_run"))
    return run_cycle(STRAT, mode="dry_run", provider=FixtureMarketState(path, overrides=over),
                     broker=broker or SimBroker(seeded), lineage=lin, allow_trading=True)


def payload(lin: Lineage, cycle_id: str) -> dict:
    rec = lin.get_decision_record(cycle_id)
    assert rec is not None, f"no decision record for {cycle_id}"
    return rec["payload"]


# --- recording is not gated on mode ------------------------------------------------

@pytest.mark.parametrize("run_mode,trading_mode", [
    ("dry_run", "paper"),
    ("paper", "paper"),
    ("paper", "live"),
    ("dry_run", "live"),
])
def test_recording_enabled_for_every_mode(run_mode, trading_mode):
    assert recording_enabled(run_mode, trading_mode) is True
    assert recording_enabled() is True


def test_gate_catalog_is_versioned():
    assert GATE_CATALOG_VERSION == "gates_v1"
    assert DECISION_SCHEMA_VERSION == "decision_v1"
    assert "No learned weights" in RANKING_DESCRIPTION


# --- enter / WAL / replay ----------------------------------------------------------

def test_enter_writes_wal_before_order_and_replays(lin, rules):
    r = dry(lin)
    assert r.outcome == "entered"
    rec = payload(lin, r.cycle_id)
    assert rec["outcome"] == "trade"
    assert rec["run_mode"] == "dry_run"
    assert rec["trading_mode"] == "paper"
    assert rec["strategy_sha256"]
    assert "name: spy-defined-risk-rr" in rec["strategy_yaml"]
    assert rec["gate_catalog_version"] == GATE_CATALOG_VERSION
    assert rec["binding_gate"] is None
    assert rec["data_trust"] == "ok"
    assert "No learned weights" in rec["ranking"]
    kinds = [a["kind"] for a in lin.get_cycle(r.cycle_id)["artifacts"]]
    assert kinds.index("decision_record") < kinds.index("order")
    assert kinds.index("decision_record") < kinds.index("intent")
    assert not catalog_complete(rec, phase="entry")
    chosen = next(c for c in rec["candidates"] if c["chosen"])
    intent, _ = build_entry(snap(), rules, strategy_name="x", idempotency_key="k")
    assert intent is not None
    assert {l["occ"] for l in chosen["legs"]} == {l.occ for l in intent.legs}

    stored = lin.get_decision_record(r.cycle_id)["payload"]
    replayed = replay_stored(stored)
    assert replayed == replay_fingerprint(stored)


def test_paper_mode_also_writes_a_record(lin, monkeypatch):
    monkeypatch.setenv("TRADING_MODE", "paper")
    monkeypatch.delenv("IB_GATEWAY_PORT", raising=False)

    class FakeIB:
        def managedAccounts(self):
            return ["DU123"]

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

    r = run_cycle(
        STRAT, mode="paper", provider=FixtureMarketState(ENTRY),
        broker=IBExecution(FakeIB(), allow_trading=False, expected_account_id="DU123"),
        lineage=lin, allow_trading=False, identity_check=lambda: "DU123", now=RTH_NOW,
    )
    assert r.outcome == "proposed_not_sent"
    rec = payload(lin, r.cycle_id)
    assert rec["run_mode"] == "paper"
    assert rec["trading_mode"] == "paper"
    assert rec["outcome"] == "trade"
    assert rec["gates"]


# --- abstain is a decision ---------------------------------------------------------

def test_abstain_cycle_has_complete_record_and_explain(lin):
    r = dry(lin, FLAT)
    assert r.outcome == "abstained" and r.reasons[0].startswith("signal rr25=")
    rec = payload(lin, r.cycle_id)
    assert rec["outcome"] == "abstain"
    assert rec["binding_gate"] == "signal_rr25"
    assert rec["phase"] == "entry"
    assert not catalog_complete(rec, phase="entry")
    # No short-circuit in the record: construction gates are still there.
    assert any(g["gate"] in CONSTRUCTION_GATES and g["result"] != "skipped"
               for g in rec["gates"] if g.get("candidate_id"))
    rr = next(g for g in rec["gates"] if g["gate"] == "signal_rr25")
    assert rr["result"] == "fail" and rr["unit"] == "vol_diff" and rr["operator"] == "le"
    assert rr["margin"] is not None
    text = explain(lin.get_cycle(r.cycle_id), record=rec)
    assert "OUTCOME: abstained" in text
    assert "DECISION: abstain" in text
    assert "BINDING GATE: signal_rr25" in text
    assert "CLOSEST CALLS:" in text
    assert "signal_rr25" in text.split("CLOSEST CALLS:")[1].split("DATA TRUST")[0]
    assert "DATA TRUST:" in text
    assert "No learned weights" in text
    assert rec["strategy_sha256"][:8] in text or "sha256=" in text


def test_unavailable_and_kill_and_blackout_still_record(lin):
    r = dry(lin, UNAVAIL)
    rec = payload(lin, r.cycle_id)
    assert rec["outcome"] == "abstain"
    assert rec["binding_gate"] == "market_data_ok"
    assert {g["gate"] for g in rec["gates"] if not g.get("candidate_id")} >= set(CYCLE_GATES)

    lin2 = Lineage(str(Path(lin.db_path).with_name("kill.db")))
    lin2.latch_kill(NAME, "dry_run", "manual: test")
    r2 = dry(lin2)
    rec2 = payload(lin2, r2.cycle_id)
    assert rec2["binding_gate"] == "kill_switch_clear"
    assert rec2["outcome"] == "abstain"
    # Other gates still evaluated (signals / construction), not omitted.
    assert any(g["gate"] == "signal_rr25" and g["result"] != "skipped" for g in rec2["gates"])

    r3 = dry(lin, as_of="2026-10-26T15:00:00+00:00")
    rec3 = payload(lin, r3.cycle_id)
    assert rec3["binding_gate"] == "signal_event_blackout"
    assert rec3["outcome"] == "abstain"


# --- hold is a decision ------------------------------------------------------------

def test_hold_cycle_has_complete_record_and_explain(lin, rules):
    assert dry(lin).outcome == "entered"
    r = dry(lin)
    assert r.outcome == "held"
    rec = payload(lin, r.cycle_id)
    assert rec["outcome"] == "abstain"
    assert rec["phase"] == "hold"
    assert rec["binding_gate"] is None
    assert rec["opened_cycle_id"]
    missing = catalog_complete(rec, phase="hold")
    assert not missing, missing
    by = {g["gate"]: g for g in rec["gates"] if g["gate"] in EXIT_GATES}
    assert by["exit_time_stop"]["result"] == "pass"
    assert by["exit_time_stop"]["unit"] == "dte"
    assert by["exit_time_stop"]["value"] > rules.exits.time_stop_dte
    assert by["exit_time_stop"]["margin"] is not None
    assert by["exit_stop_loss"]["result"] == "pass"
    assert by["exit_take_profit"]["result"] == "pass"
    assert by["exit_underlying_stop"]["result"] == "pass"
    text = explain(lin.get_cycle(r.cycle_id), record=rec)
    assert "OUTCOME: held" in text
    assert "DECISION: abstain" in text
    assert "BINDING GATE: (none" in text
    assert "exit_time_stop" in text
    assert "exit_stop_loss" in text or "exit_take_profit" in text or "exit_underlying_stop" in text
    assert "CLOSEST CALLS:" in text
    assert "No learned weights" in text


def test_hold_margins_show_distance_to_stops(lin, rules):
    assert dry(lin).outcome == "entered"
    r = dry(lin)
    rec = payload(lin, r.cycle_id)
    dte_gate = next(g for g in rec["gates"] if g["gate"] == "exit_time_stop")
    # 2026-10-19 vs 2026-11-20 = 32 DTE; stop is 21. Positive margin = room left.
    assert dte_gate["value"] == 32
    assert dte_gate["threshold"] == 21
    assert dte_gate["margin"] == pytest.approx((32 - 21) / 21)


# --- construction: every gate, every candidate -------------------------------------

def test_construction_evaluates_every_gate_for_every_candidate(rules):
    report = evaluate_construction(snap(), rules)
    assert report.candidates
    assert report.chosen_id
    for c in report.candidates:
        have = {g.gate for g in report.gates if g.candidate_id == c["candidate_id"]}
        assert have == set(CONSTRUCTION_GATES)
    intent, _ = build_entry(snap(), rules, strategy_name="x", idempotency_key="k")
    chosen = next(c for c in report.candidates if c["chosen"])
    assert {l["occ"] for l in chosen["legs"]} == {l.occ for l in intent.legs}


def test_illiquid_wing_abstain_records_all_candidates(rules):
    s = snap()
    intent, _ = build_entry(s, rules, strategy_name="x", idempotency_key="k")
    assert intent is not None
    for o in s.options:
        if o.right == "P":
            o.open_interest = 470
    intent2, why = build_entry(s, rules, strategy_name="x", idempotency_key="k")
    assert intent2 is None
    assert "open interest" in " ".join(why).lower() or "OI 470" in " ".join(why)
    report = evaluate_construction(s, rules)
    assert report.chosen_id is None
    oi_fails = [g for g in report.gates if g.gate == "wing_put_open_interest" and g.result == "fail"]
    assert oi_fails
    assert any(g.value == 470 and g.threshold == 500 for g in oi_fails)


# --- CLI ---------------------------------------------------------------------------

def test_cli_explain_abstain_and_hold(tmp_path, capsys):
    db = str(tmp_path / "s.db")
    assert cli_main(["--db", db, "run", "--dry-run", "--fixture", str(FLAT)]) == 0
    assert cli_main(["--db", db, "explain", "last"]) == 0
    out = capsys.readouterr().out
    assert "OUTCOME: abstained" in out
    assert "DECISION: abstain" in out
    assert "BINDING GATE: signal_rr25" in out
    assert "No learned weights" in out

    db2 = str(tmp_path / "h.db")
    assert cli_main(["--db", db2, "run", "--dry-run"]) == 0
    assert cli_main(["--db", db2, "run", "--dry-run"]) == 0
    assert cli_main(["--db", db2, "explain", "last"]) == 0
    hold = capsys.readouterr().out
    assert "OUTCOME: held" in hold
    assert "DECISION: abstain" in hold
    assert "exit_time_stop" in hold


def test_error_identity_still_writes_a_record(lin):
    r = run_cycle(
        STRAT, mode="paper", provider=FixtureMarketState(ENTRY),
        broker=SimBroker(), lineage=lin, allow_trading=True,
        identity_check=lambda: "U9999", now=RTH_NOW,
    )
    assert r.outcome == "error"
    rec = payload(lin, r.cycle_id)
    assert rec["outcome"] == "error"
    assert rec["binding_gate"] == "identity_ok"
    assert rec["run_mode"] == "paper"
    id_gate = next(g for g in rec["gates"] if g["gate"] == "identity_ok")
    assert id_gate["result"] == "fail"
    later = [g for g in rec["gates"] if g["gate"] == "signal_rr25"]
    assert later and later[0]["result"] == "skipped"
