"""Assemble and persist a per-cycle decision record.

Not acting is a decision. Every cycle writes a full record — trade, abstain,
hold, proposed_not_sent, no candidates, blackout, kill switch, or error.

Recording applies to every mode. Paper is the primary case; dry_run and live
use the same schema. Recording is never gated on mode.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

from core.gates import (
    CONSTRUCTION_GATES,
    CYCLE_GATES,
    EXIT_GATES,
    RANKING_DESCRIPTION,
    ConstructionReport,
    CycleGateCtx,
    binding_gate,
    closest_margins,
    data_trust_flag,
    derive_reasons,
    evaluate_construction,
    evaluate_cycle_gates,
    evaluate_exit_gates,
    replay_fingerprint,
    source_class,
)
from core.signals import SignalValue, compute_signals, dte, snapshot_date
from schemas.cycle import MarketSnapshot
from schemas.decision import (
    DECISION_SCHEMA_VERSION,
    GATE_CATALOG_VERSION,
    CandidateRecord,
    DecisionRecord,
    GateEval,
    InputPoint,
)
from schemas.strategy import DeterministicRules
from utils.lineage import Lineage, utc_now_iso

# Paper is the primary case. This hook exists so tests can prove recording
# is not filtered by run_mode or trading_mode.
_ALWAYS_RECORD = True


def recording_enabled(run_mode: str | None = None, trading_mode: str | None = None) -> bool:
    """Decision records apply to every mode. Never skip a write because of mode."""
    del run_mode, trading_mode
    return _ALWAYS_RECORD


@dataclass
class DecisionScratch:
    """Inputs gathered along the cycle. Missing pieces become skipped gates."""

    cycle_id: str
    run_mode: Literal["dry_run", "paper"]
    trading_mode: Literal["paper", "live"]
    git_sha: str | None
    strategy_name: str
    strategy_version: str
    strategy_sha256: str
    strategy_yaml: str
    rules: DeterministicRules
    clock: datetime
    flatten: bool = False
    allow_trading: bool = False
    data_source: str = "ib"
    identity_ok: bool | None = None
    identity_error: str | None = None
    market_open: bool | None = None
    reconcile: dict[str, Any] | None = None
    kill: dict[str, Any] | None = None
    realized_pnl: float | None = None
    entries_today: int | None = None
    opens_this_run: int | None = None
    positions: list[dict[str, Any]] = field(default_factory=list)
    snapshot: MarketSnapshot | None = None
    signals: list[SignalValue] | None = None
    rr25_history: list[float] | None = None
    in_entry_window: bool | None = None
    construction: ConstructionReport | None = None
    exit_gates: list[GateEval] | None = None
    exit_trigger: str | None = None
    exit_reasons: list[str] = field(default_factory=list)
    phase: str = "entry"
    error: str | None = None
    entry_reasons: list[str] = field(default_factory=list)
    fallback_reasons: list[str] = field(default_factory=list)


def _required_signal_names(signals: list[SignalValue] | None) -> set[str]:
    if not signals:
        return {"rr25"}
    return {s.name for s in signals if s.required}


def _cycle_ctx(scratch: DecisionScratch) -> CycleGateCtx:
    rules = scratch.rules
    snap = scratch.snapshot
    days = None
    dte_skip = None
    if snap is None:
        dte_skip = "no market snapshot"
    elif snap.status != "ok":
        dte_skip = f"snapshot {snap.status}"
    elif snap.expiry is None:
        dte_skip = "no expiry in DTE window"
    else:
        days = dte(snap.expiry, snapshot_date(snap))
    identity_skip = None
    if scratch.run_mode == "dry_run" and scratch.identity_ok is None:
        identity_skip = "not applicable: dry_run does not check identity"
    market_skip = None
    if scratch.run_mode == "dry_run" and scratch.market_open is None:
        market_skip = "not applicable: dry_run does not check RTH"
    rec_ok = None if scratch.reconcile is None else bool(scratch.reconcile.get("ok"))
    rec_skip = None if scratch.reconcile is not None else "reconcile not run"
    data_ok = None if snap is None else snap.status == "ok"
    data_skip = None if snap is not None else "no market snapshot"
    kill_latched = None if scratch.kill is None else True
    if scratch.kill is None:
        # Distinguishes "checked, clear" from "not checked".
        kill_latched = False if scratch.phase != "error" or scratch.reconcile is not None else None
    kill_skip = None if kill_latched is not None else "kill switch not read"
    window_skip = None if scratch.in_entry_window is not None else (
        "entry window not evaluated" if snap is None else None
    )
    sig_skip = None if scratch.signals is not None else (
        "open position: entry signals not used" if scratch.phase in ("exit", "hold")
        else "signals not evaluated"
    )
    return CycleGateCtx(
        identity_ok=scratch.identity_ok, identity_skip=identity_skip,
        market_open=scratch.market_open, market_open_skip=market_skip,
        reconcile_ok=rec_ok, reconcile_skip=rec_skip,
        market_data_ok=data_ok, market_data_skip=data_skip,
        flatten=scratch.flatten, has_position=bool(scratch.positions),
        kill_latched=kill_latched, kill_skip=kill_skip,
        entries_today=scratch.entries_today, max_entries=rules.opens_per_day(),
        max_per_run=rules.opens_per_run(),
        opens_this_run=scratch.opens_this_run,
        in_entry_window=scratch.in_entry_window, window_skip=window_skip,
        dte_days=days, dte_skip=dte_skip, phase=scratch.phase,
        signals=scratch.signals, signals_skip=sig_skip,
    )


def _input_points(scratch: DecisionScratch) -> list[dict[str, Any]]:
    snap = scratch.snapshot
    if snap is None:
        return []
    src = source_class(snap.source)
    age = _age_seconds(scratch.clock, snap.as_of, src)
    points: list[InputPoint] = [
        InputPoint(name="underlying_price", value=snap.underlying_price, unit="usd",
                   source=src, age_seconds=age),
    ]
    for row in snap.options:
        if snap.expiry and row.expiry != snap.expiry:
            continue
        for field, unit, val in (
            ("bid", "usd", row.bid),
            ("ask", "usd", row.ask),
            ("iv", "vol", row.iv),
            ("delta", "delta", row.delta),
            ("open_interest", "contracts", row.open_interest),
        ):
            points.append(InputPoint(
                name=f"{row.occ}.{field}", value=val, unit=unit, source=src, age_seconds=age,
            ))
    if scratch.signals:
        for s in scratch.signals:
            unit = {"rr25": "vol_diff", "put_call_iv_ratio": "ratio",
                    "atm_iv_minus_rv": "vol_diff", "rr25_percentile": "percentile",
                    "event_blackout": "count"}.get(s.name, "1")
            points.append(InputPoint(name=s.name, value=s.value, unit=unit,
                                     source=src, age_seconds=age))
    return [p.model_dump(mode="json") for p in points]


def _age_seconds(clock: datetime, as_of: str | None, src: str) -> float:
    if src == "fixture" or not as_of:
        return 0.0
    try:
        ts = datetime.fromisoformat(as_of)
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        now = clock if clock.tzinfo else clock.replace(tzinfo=timezone.utc)
        return max(0.0, (now - ts).total_seconds())
    except ValueError:
        return 0.0


def _kill_note(scratch: DecisionScratch) -> str | None:
    k = scratch.kill
    if not k:
        return None
    return f"kill_switch_latched: {k.get('reason')} (since {k.get('ts')})"


def build_record(
    scratch: DecisionScratch,
    *,
    decision_outcome: Literal["trade", "abstain", "error"],
    cycle_outcome: str | None = None,
) -> DecisionRecord:
    rules = scratch.rules
    snap = scratch.snapshot
    if scratch.phase == "entry" and snap is not None and snap.status == "ok" and scratch.construction is None:
        scratch.construction = evaluate_construction(snap, rules)
    if scratch.phase in ("exit", "hold", "flatten") and scratch.positions and snap is not None and scratch.exit_gates is None:
        scratch.exit_gates = evaluate_exit_gates(
            scratch.positions[0], snap, rules, flatten=scratch.flatten,
            daily_pnl=scratch.realized_pnl or 0.0,
        )

    ctx = _cycle_ctx(scratch)
    cycle_gates = evaluate_cycle_gates(ctx, rules)
    construction = scratch.construction
    if construction is None:
        reason = {
            "exit": "open position: entry construction not used",
            "hold": "open position: entry construction not used",
            "flatten": "flatten: entry construction not used",
            "error": "error: construction not evaluated",
        }.get(scratch.phase, "construction not evaluated")
        construction = ConstructionReport(
            gates=[GateEval(gate=g, unit=u, result="skipped", skip_reason=reason)
                   for g, u in CONSTRUCTION_GATES.items()],
        )
    exit_gates = scratch.exit_gates
    if exit_gates is None:
        reason = "entry cycle: exit gates not used" if scratch.phase == "entry" else "exit gates not evaluated"
        exit_gates = [GateEval(gate=g, unit=u, result="skipped", skip_reason=reason)
                      for g, u in EXIT_GATES.items()]

    req = _required_signal_names(scratch.signals)
    bind = binding_gate(
        phase=scratch.phase, cycle_gates=cycle_gates, construction=construction,
        exit_gates=exit_gates, flatten=scratch.flatten, required_signals=req,
    )
    extra = {
        "identity_error": scratch.identity_error,
        "reconcile_drift": (scratch.reconcile or {}).get("drift") or [],
        "snapshot_reason": None if snap is None else snap.reason,
        "has_position": bool(scratch.positions),
        "kill_note": _kill_note(scratch),
        "max_entries": rules.opens_per_day(),
        "max_per_run": rules.opens_per_run(),
        "entry_window": rules.execution.entry_slots_et or rules.execution.entry_window_et,
        "entry_slots": rules.execution.entry_slots_et,
        "entry_timezone": rules.execution.entry_timezone,
        "expiry": None if snap is None else snap.expiry,
        "dte_min": rules.structure.dte_min,
        "dte_max": rules.structure.dte_max,
        "signal_notes": {s.name: s.note for s in (scratch.signals or []) if s.note},
        "exit_reasons": scratch.exit_reasons,
        "exit_trigger": scratch.exit_trigger,
        "entry_reasons": scratch.entry_reasons,
        "short_put_delta_min": rules.structure.short_put_delta_min,
        "short_put_delta_max": rules.structure.short_put_delta_max,
        "long_call_delta_min": rules.structure.long_call_delta_min,
        "long_call_delta_max": rules.structure.long_call_delta_max,
        "min_oi": rules.structure.min_open_interest,
        "max_spread": rules.structure.max_spread_pct_of_mid,
        "error": scratch.error,
        "fallback_reasons": scratch.fallback_reasons,
    }
    reasons = derive_reasons(
        bind, phase=scratch.phase, cycle_gates=cycle_gates,
        construction=construction, exit_gates=exit_gates, extra=extra,
    )
    gates = list(cycle_gates) + list(construction.gates) + list(exit_gates)
    age = _age_seconds(scratch.clock, None if snap is None else snap.as_of,
                       source_class(None if snap is None else snap.source))
    src = None if snap is None else snap.source
    opened = None
    if scratch.positions:
        opened = scratch.positions[0].get("opened_cycle_id")

    inputs = {
        "as_of": None if snap is None else snap.as_of,
        "source": src,
        "source_class": None if src is None else source_class(src),
        "age_seconds": age,
        "quotes": _input_points(scratch),
        "market": None if snap is None else snap.model_dump(mode="json"),
        "cycle_state": {
            "flatten": scratch.flatten,
            "allow_trading": scratch.allow_trading,
            "data_source": scratch.data_source,
            "identity_ok": scratch.identity_ok,
            "market_open": scratch.market_open,
            "reconcile_ok": None if scratch.reconcile is None else bool(scratch.reconcile.get("ok")),
            "reconcile_drift": (scratch.reconcile or {}).get("drift") or [],
            "kill_latched": bool(scratch.kill),
            "kill_reason": None if not scratch.kill else scratch.kill.get("reason"),
            "realized_pnl": scratch.realized_pnl,
            "entries_today": scratch.entries_today,
            "opens_this_run": scratch.opens_this_run,
            "has_position": bool(scratch.positions),
            "position": scratch.positions[0] if scratch.positions else None,
            "rr25_history": scratch.rr25_history or [],
            "in_entry_window": scratch.in_entry_window,
            "clock": scratch.clock.isoformat(),
            "phase": scratch.phase,
            "exit_trigger": scratch.exit_trigger,
        },
    }
    return DecisionRecord(
        schema_version=DECISION_SCHEMA_VERSION,
        gate_catalog_version=GATE_CATALOG_VERSION,
        cycle_id=scratch.cycle_id,
        recorded_at=utc_now_iso(),
        run_mode=scratch.run_mode,
        trading_mode=scratch.trading_mode,
        git_sha=scratch.git_sha,
        strategy_name=scratch.strategy_name,
        strategy_version=scratch.strategy_version,
        strategy_sha256=scratch.strategy_sha256,
        strategy_yaml=scratch.strategy_yaml,
        outcome=decision_outcome,
        cycle_outcome=cycle_outcome,
        binding_gate=bind,
        phase=scratch.phase,
        ranking=RANKING_DESCRIPTION,
        data_trust=data_trust_flag(source=src, age_seconds=age),
        derived_reasons=reasons,
        inputs=inputs,
        candidates=[CandidateRecord.model_validate(c) for c in construction.candidates],
        gates=gates,
        opened_cycle_id=opened,
    )


def persist_decision_record(lineage: Lineage, record: DecisionRecord) -> None:
    """Write-ahead: table row + append-only artifact. First write wins."""
    payload = record.model_dump(mode="json")
    lineage.insert_decision_record(payload)
    lineage.record(record.cycle_id, "decision_record", {
        k: payload[k] for k in payload if k != "strategy_yaml"
    } | {"strategy_yaml_sha256": record.strategy_sha256,
         "strategy_yaml_chars": len(record.strategy_yaml)})


def commit_decision_record(
    lineage: Lineage,
    scratch: DecisionScratch,
    decision_outcome: Literal["trade", "abstain", "error"],
    *,
    cycle_outcome: str | None = None,
) -> DecisionRecord:
    # Assert, do not branch: recording is not gated on mode.
    assert recording_enabled(scratch.run_mode, scratch.trading_mode), (
        "decision records apply to every mode"
    )
    record = build_record(scratch, decision_outcome=decision_outcome, cycle_outcome=cycle_outcome)
    persist_decision_record(lineage, record)
    return record


def enrich_entry_evals(scratch: DecisionScratch) -> None:
    """Pure evaluation for the record. Does not change what the cycle decides."""
    snap = scratch.snapshot
    if snap is None or snap.status != "ok":
        return
    if scratch.signals is None and scratch.phase == "entry":
        hist = scratch.rr25_history or []
        scratch.signals = compute_signals(snap, scratch.rules, rr25_history=hist)
    if scratch.construction is None and scratch.phase == "entry":
        scratch.construction = evaluate_construction(snap, scratch.rules)


def replay_stored(record: dict[str, Any]) -> dict[str, Any]:
    """Re-run current decision code on the stored snapshot + cycle_state."""
    import yaml

    from schemas.strategy import StrategyConfig

    yaml_text = record["strategy_yaml"]
    strategy = StrategyConfig.model_validate(yaml.safe_load(yaml_text))
    if strategy.rules is None:
        raise ValueError("stored strategy has no rules")
    state = record["inputs"]["cycle_state"]
    market = record["inputs"].get("market")
    snap = None if market is None else MarketSnapshot.model_validate(market)
    clock = datetime.fromisoformat(state["clock"])
    scratch = DecisionScratch(
        cycle_id=record["cycle_id"],
        run_mode=record["run_mode"],
        trading_mode=record["trading_mode"],
        git_sha=record.get("git_sha"),
        strategy_name=record["strategy_name"],
        strategy_version=record["strategy_version"],
        strategy_sha256=record["strategy_sha256"],
        strategy_yaml=yaml_text,
        rules=strategy.rules,
        clock=clock,
        flatten=bool(state.get("flatten")),
        allow_trading=bool(state.get("allow_trading")),
        data_source=state.get("data_source") or "ib",
        identity_ok=state.get("identity_ok"),
        market_open=state.get("market_open"),
        reconcile={"ok": state.get("reconcile_ok"), "drift": state.get("reconcile_drift") or []}
        if state.get("reconcile_ok") is not None else None,
        kill={"reason": state.get("kill_reason"), "ts": ""} if state.get("kill_latched") else None,
        realized_pnl=state.get("realized_pnl"),
        entries_today=state.get("entries_today"),
        opens_this_run=state.get("opens_this_run"),
        positions=[state["position"]] if state.get("position") else [],
        snapshot=snap,
        rr25_history=list(state.get("rr25_history") or []),
        in_entry_window=state.get("in_entry_window"),
        phase=state.get("phase") or record.get("phase") or "entry",
        exit_trigger=state.get("exit_trigger"),
    )
    if scratch.phase == "entry":
        enrich_entry_evals(scratch)
    rebuilt = build_record(scratch, decision_outcome=record["outcome"],
                           cycle_outcome=record.get("cycle_outcome"))
    return replay_fingerprint(rebuilt.model_dump(mode="json"))


def format_decision_explain(record: dict[str, Any]) -> str:
    """Plain-text decision summary: outcome, binding gate, closest calls, trust, ranking."""
    parsed = [GateEval.model_validate(g) for g in record.get("gates") or []]
    phase = record.get("phase")
    if phase in ("hold", "exit", "flatten"):
        focus = set(EXIT_GATES)
    else:
        chosen_id = next((c.get("candidate_id") for c in record.get("candidates") or [] if c.get("chosen")), None)
        parsed = [g for g in parsed if g.candidate_id is None or g.candidate_id == chosen_id]
        focus = set(CYCLE_GATES) | (set(CONSTRUCTION_GATES) if chosen_id else set())
    closest = closest_margins(parsed, names=focus)
    bind = record.get("binding_gate") or "(none — all required gates passed)"
    lines = [
        f"  DECISION: {record.get('outcome')}  phase={record.get('phase')}  "
        f"run_mode={record.get('run_mode')} trading_mode={record.get('trading_mode')}",
        f"  BINDING GATE: {bind}",
        "  CLOSEST CALLS:",
    ]
    if not closest:
        lines.append("    (no numeric margins)")
    for i, g in enumerate(closest, 1):
        cid = f" [{g.candidate_id}]" if g.candidate_id else ""
        lines.append(
            f"    {i}. {g.gate}{cid}  value={g.value} {g.operator} {g.threshold}  "
            f"{g.unit}  {g.result}  margin={None if g.margin is None else round(g.margin, 4)}"
        )
    lines += [
        f"  DATA TRUST: {record.get('data_trust')}",
        f"  STRATEGY YAML: {record.get('strategy_name')} v{record.get('strategy_version')}  "
        f"sha256={record.get('strategy_sha256')}  catalog={record.get('gate_catalog_version')}  "
        f"schema={record.get('schema_version')}",
        f"  RANKING: {record.get('ranking')}",
    ]
    for r in record.get("derived_reasons") or []:
        lines.append(f"  derived: {r}")
    return "\n".join(lines)


def catalog_complete(record: dict[str, Any], *, phase: str) -> list[str]:
    """Missing catalog names (cycle always; construction per candidate; exit on hold/exit)."""
    missing: list[str] = []
    cycle_names = {g["gate"] for g in record.get("gates") or [] if not g.get("candidate_id")}
    for name in CYCLE_GATES:
        if name not in cycle_names:
            missing.append(f"cycle:{name}")
    exit_needed = phase in ("exit", "hold", "flatten")
    if exit_needed:
        for name in EXIT_GATES:
            if name not in cycle_names and name not in {g["gate"] for g in record.get("gates") or []}:
                missing.append(f"exit:{name}")
        # EXIT_GATES have no candidate_id
        have = {g["gate"] for g in record.get("gates") or [] if g["gate"] in EXIT_GATES}
        for name in EXIT_GATES:
            if name not in have:
                missing.append(f"exit:{name}")
    cands = record.get("candidates") or []
    if cands:
        for c in cands:
            have = {g["gate"] for g in record.get("gates") or []
                    if g.get("candidate_id") == c["candidate_id"]}
            for name in CONSTRUCTION_GATES:
                if name not in have:
                    missing.append(f"{c['candidate_id']}:{name}")
    else:
        have = {g["gate"] for g in record.get("gates") or [] if g["gate"] in CONSTRUCTION_GATES}
        for name in CONSTRUCTION_GATES:
            if name not in have:
                missing.append(f"construction:{name}")
    return missing
