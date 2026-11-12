"""Structured decision records: every cycle, every mode, not-acting is a decision.

Fakes only. No Gateway, no orders to a real broker.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.brokers import IBExecution, SimBroker
from core.cli import explain, main as cli_main
from core.cycle import run_cycle
from core.decision_record import catalog_complete, recording_enabled, replay_stored
from core.entry_window import DRY_RUN_NOW
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
STRAT = ROOT / "strategies/active/us-large-cap-rr.yaml"
FIX = ROOT / "tests/fixtures"
ENTRY = FIX / "spy_snapshot_entry.json"
FLAT = FIX / "spy_snapshot_flat_skew.json"
UNAVAIL = FIX / "spy_snapshot_unavailable.json"
NAME = "us-large-cap-rr"
SLOT_NOW = lambda: DRY_RUN_NOW  # noqa: E731


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
    return run_cycle(
        STRAT, mode="dry_run", provider=FixtureMarketState(path, overrides=over),
        broker=broker or SimBroker(seeded), lineage=lin, allow_trading=True, now=SLOT_NOW,
    )


def payload(lin: Lineage, cycle_id: str) -> dict:
    rec = lin.get_decision_record(cycle_id)
    assert rec is not None, f"no decision record for {cycle_id}"
    return rec["payload"]


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
    assert GATE_CATALOG_VERSION == "gates_v2"
    assert DECISION_SCHEMA_VERSION == "decision_v1"
    assert "No learned weights" in RANKING_DESCRIPTION
    assert "5 new opens" in RANKING_DESCRIPTION


def test_enter_writes_wal_before_order_and_replays(lin, rules):
    r = dry(lin)
    assert r.outcome == "entered"
    rec = payload(lin, r.cycle_id)
    assert rec["outcome"] == "trade"
    assert rec["run_mode"] == "dry_run"
    assert rec["trading_mode"] == "paper"
    assert rec["strategy_sha256"]
    assert "name: us-large-cap-rr" in rec["strategy_yaml"]
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
    assert len(chosen["legs"]) == 2

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
        lineage=lin, allow_trading=False, identity_check=lambda: "DU123", now=SLOT_NOW,
    )
    assert r.outcome == "proposed_not_sent"
    rec = payload(lin, r.cycle_id)
    assert rec["run_mode"] == "paper"
    assert rec["trading_mode"] == "paper"
    assert rec["outcome"] == "trade"
    assert rec["gates"]


def test_abstain_cycle_has_complete_record_and_explain(lin):
    r = dry(lin, FLAT)
    assert r.outcome == "abstained" and r.reasons[0].startswith("signal rr25=")
    rec = payload(lin, r.cycle_id)
    assert rec["outcome"] == "abstain"
    assert rec["binding_gate"] == "signal_rr25"
    assert rec["phase"] == "entry"
    assert not catalog_complete(rec, phase="entry")
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
    assert "exit_time_stop" not in text
    assert "yellow" not in text.lower()


def test_unavailable_and_kill_still_record(lin):
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


def test_hold_cycle_has_complete_record_and_explain(lin):
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
    assert set(by) == set(EXIT_GATES)
    assert by["exit_marks_available"]["result"] == "pass"
    assert by["manual_flatten"]["result"] == "skipped"
    text = explain(lin.get_cycle(r.cycle_id), record=rec)
    assert "OUTCOME: held" in text
    assert "DECISION: abstain" in text
    assert "BINDING GATE: (none" in text
    assert "exit_time_stop" not in text
    assert "manual flatten" in text.lower() or "no automated" in text.lower() or "CLOSEST CALLS:" in text
    assert "No learned weights" in text


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
    assert all(g.gate != "wing_put_open_interest" for g in report.gates)


def test_illiquid_short_put_records_all_candidates(rules):
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
    oi_fails = [g for g in report.gates if g.gate == "short_put_open_interest" and g.result == "fail"]
    assert oi_fails
    assert any(g.value == 470 and g.threshold == 500 for g in oi_fails)


def test_cli_explain_abstain_and_hold(tmp_path, capsys):
    db = str(tmp_path / "s.db")
    assert cli_main(["--db", db, "run", "--dry-run", "--fixture", str(FLAT)]) == 0
    assert cli_main(["--db", db, "explain", "last"]) == 0
    out = capsys.readouterr().out
    assert "OUTCOME: abstained" in out
    assert "DECISION: abstain" in out
    assert "BINDING GATE: signal_rr25" in out
    assert "No learned weights" in out
    assert "exit_time_stop" not in out

    db2 = str(tmp_path / "h.db")
    assert cli_main(["--db", db2, "run", "--dry-run"]) == 0
    assert cli_main(["--db", db2, "run", "--dry-run"]) == 0
    assert cli_main(["--db", db2, "explain", "last"]) == 0
    hold = capsys.readouterr().out
    assert "OUTCOME: held" in hold
    assert "DECISION: abstain" in hold
    assert "exit_time_stop" not in hold


def test_error_identity_still_writes_a_record(lin):
    r = run_cycle(
        STRAT, mode="paper", provider=FixtureMarketState(ENTRY),
        broker=SimBroker(), lineage=lin, allow_trading=True,
        identity_check=lambda: "U9999", now=SLOT_NOW,
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
