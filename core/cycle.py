"""Deterministic run-once cycle (in-force standard RR).

reconcile -> mark-to-market -> signals -> decision -> intent -> gated order ->
fill -> debrief -> reconcile -> stop. Every artifact is written under one cycle_id.
Abstention is a successful outcome. Data problems abstain; they never guess.

Product-in-force (locked 2026-11-11): standard RR (short put + long call),
rr25-only binding entry, no automated exits, two weekday slots (10:00 and
15:00 America/Toronto wall clock). See knowledge/ops/exit-strategy.md.
"""

from __future__ import annotations

import hashlib
import os
import subprocess
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, time as dtime, timezone
from pathlib import Path
from typing import Any, Literal

from core.brokers import ExecutionBroker
from core.closeout import build_debrief, mark_to_market, persistable_fill
from core.decision_record import (
    DecisionScratch,
    commit_decision_record,
    enrich_entry_evals,
    recording_enabled,
)
from core.entry_window import in_entry_slot
from core.gates import evaluate_exit_gates
from core.guarded_broker import GuardedReject
from core.identity import IdentityError
from core.market_state import MarketStateProvider
from core.reconcile import reconcile
from core.rr_rules import build_entry, build_exit, evaluate_exit
from core.send_gate import paper_send_reason
from core.shadow import TaggedLineage, shadow_tag
from core.signals import compute_signals, failing_required
from core.strategy_loader import load as load_strategy
from core.universe import name_key, open_underlyings, position_underlying, resolve_universe, vendor_symbol
from schemas.cycle import ComboIntent, Decision, MarketSnapshot
from schemas.strategy import IN_FORCE_ENGINE, StrategyConfig
from utils.lineage import Lineage
from utils.logging import get_logger
from utils.time_et import ET

log = get_logger(__name__)

MODES = ("dry_run", "paper")


@dataclass
class CycleResult:
    cycle_id: str
    outcome: str  # entered | exited | held | abstained | proposed_not_sent | error
    reasons: list[str] = field(default_factory=list)


def _git_sha() -> str | None:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True,
                              timeout=5, cwd=Path(__file__).resolve().parents[1]).stdout.strip() or None
    except Exception:
        return None


def _et_midnight_utc_iso(now: datetime) -> str:
    et = now.astimezone(ET)
    return et.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc).isoformat(timespec="seconds")


def _rth(now: datetime) -> bool:
    t = now.astimezone(ET)
    return t.weekday() < 5 and dtime(9, 30) <= t.time() < dtime(16, 0)


def _vendor(data_source: str) -> str:
    src = (data_source or "ib").strip().lower()
    return src if src in ("cboe", "alpaca") else "ib"


def _snapshot(
    provider: MarketStateProvider, rules, ticker: str, held_legs: list[dict], *, vendor: str,
) -> MarketSnapshot:
    return provider.snapshot(
        rules, held_legs=held_legs, underlying=vendor_symbol(ticker, vendor=vendor),
    )


def run_cycle(
    strategy_path: str | Path,
    *,
    mode: str,
    provider: MarketStateProvider,
    broker: ExecutionBroker,
    lineage: Lineage,
    allow_trading: bool,
    identity_check: Callable[[], str] | None = None,
    now: Callable[[], datetime] | None = None,
    flatten: bool = False,
    data_source: str = "ib",
) -> CycleResult:
    if mode not in MODES:
        raise ValueError(f"mode must be one of {MODES}")
    clock = now or (lambda: datetime.now(timezone.utc))
    path = Path(strategy_path)
    strategy: StrategyConfig = load_strategy(path)
    if strategy.rules is None:
        raise ValueError(f"{path} has no deterministic `rules:` block")
    rules = strategy.rules
    if rules.engine != IN_FORCE_ENGINE:
        raise ValueError(
            f"{path} engine {rules.engine!r} is superseded; load strategies/active/us-large-cap-rr.yaml"
        )
    name = strategy.name
    sha = hashlib.sha256(path.read_bytes()).hexdigest()

    git_sha = _git_sha()
    cid = lineage.start_cycle(strategy=name, strategy_version=strategy.version, strategy_sha256=sha,
                              mode=mode, git_sha=git_sha)
    tag = shadow_tag(data_source)
    if tag:
        lineage = TaggedLineage(lineage, tag)
    lineage.record(cid, "inputs", {
        "strategy_path": str(path), "strategy_sha256": sha, "version": strategy.version, "mode": mode,
        "allow_trading": allow_trading, "flatten": flatten, "started_at": clock().isoformat(),
        "rules": rules.model_dump(mode="json"),
        **({"data_source": tag} if tag else {}),
    })
    tm = os.environ.get("TRADING_MODE", "paper").strip().lower()
    scratch = DecisionScratch(
        cycle_id=cid, run_mode=mode,  # type: ignore[arg-type]
        trading_mode="live" if tm == "live" else "paper",
        git_sha=git_sha, strategy_name=name, strategy_version=strategy.version,
        strategy_sha256=sha, strategy_yaml=path.read_text(), rules=rules,
        clock=clock(), flatten=flatten, allow_trading=allow_trading,
        data_source=tag or data_source,
    )
    assert recording_enabled(mode, scratch.trading_mode)

    wal_written = False

    def commit_wal(decision_outcome: Literal["trade", "abstain", "error"],
                   cycle_outcome: str | None = None) -> None:
        nonlocal wal_written
        if wal_written:
            return
        commit_decision_record(lineage, scratch, decision_outcome, cycle_outcome=cycle_outcome)
        wal_written = True

    def finish(outcome: str, reasons: list[str], decision: Decision | None = None) -> CycleResult:
        if not wal_written:
            mapped: Literal["trade", "abstain", "error"] = (
                "error" if outcome == "error"
                else "abstain" if outcome in ("abstained", "held")
                else "trade"
            )
            scratch.fallback_reasons = reasons
            if outcome == "held":
                scratch.phase = "hold"
            commit_wal(mapped, cycle_outcome=outcome)
        if decision is not None:
            lineage.record(cid, "decision", decision.model_dump(mode="json"))
        lineage.end_cycle(cid, outcome, reasons)
        if outcome == "error":
            recent = lineage.recent_outcomes(name, mode, rules.kill_switch.max_consecutive_errors)
            if len(recent) >= rules.kill_switch.max_consecutive_errors and all(o == "error" for o in recent):
                lineage.latch_kill(name, mode, f"{len(recent)} consecutive error cycles")
        return CycleResult(cid, outcome, reasons)

    def abstain(reasons: list[str]) -> CycleResult:
        scratch.fallback_reasons = reasons
        commit_wal("abstain", cycle_outcome="abstained")
        return finish("abstained", reasons, Decision(action="abstain", reasons=reasons))

    account_id: str | None = None
    try:
        kill = lineage.kill_state(name, mode)

        if mode == "paper":
            try:
                if identity_check is None:
                    raise IdentityError("no identity check configured for paper mode")
                account = identity_check()
                if not account.upper().startswith(rules.execution.required_account_prefix):
                    raise IdentityError(f"account {account} is not {rules.execution.required_account_prefix}*")
                account_id = account
                scratch.identity_ok = True
                lineage.record(cid, "inputs", {"identity": {"account": account, "trading_mode": "paper"}})
            except IdentityError as exc:
                scratch.identity_ok = False
                scratch.identity_error = str(exc)
                scratch.phase = "error"
                scratch.error = f"identity_failure: {exc}"
                lineage.latch_kill(name, mode, f"identity: {exc}")
                scratch.kill = lineage.kill_state(name, mode)
                lineage.record(cid, "kill_switch", {"latched": True, "reason": f"identity: {exc}"})
                commit_wal("error", cycle_outcome="error")
                return finish("error", [f"identity_failure: {exc}"])
            scratch.market_open = _rth(clock())
            if not scratch.market_open:
                return abstain(["market_closed (outside 09:30-16:00 ET weekdays)"])

        rec = reconcile(broker, lineage, strategy=name, mode=mode, underlying=None,
                        cycle_id=cid, account_id=account_id)
        scratch.reconcile = rec
        lineage.record(cid, "reconcile", {"phase": "pre", **rec})
        if not rec["ok"]:
            lineage.latch_kill(name, mode, "reconcile drift: " + "; ".join(rec["drift"])[:500])
            scratch.kill = lineage.kill_state(name, mode)
            return abstain(["reconcile_drift"] + rec["drift"])

        day_start = _et_midnight_utc_iso(clock())
        realized = lineage.realized_pnl_since(name, mode, day_start)
        scratch.realized_pnl = realized
        kill = lineage.kill_state(name, mode)
        scratch.kill = kill
        kill_note = f"kill_switch_latched: {kill['reason']} (since {kill['ts']})" if kill else None

        positions = lineage.open_positions(name, mode)
        scratch.positions = positions
        scratch.in_entry_window = in_entry_slot(clock(), rules)

        held_by_und: dict[str, list[dict]] = {}
        for pos in positions:
            held_by_und.setdefault(position_underlying(pos), []).append(pos)

        vendor = _vendor(data_source)
        held_snaps: dict[str, MarketSnapshot] = {}
        if positions:
            for und, group in held_by_und.items():
                legs = [leg for p in group for leg in p["legs"]]
                snap = _snapshot(provider, rules, und, legs, vendor=vendor)
                held_snaps[und] = snap
                if scratch.snapshot is None:
                    scratch.snapshot = snap
                lineage.record(cid, "market_snapshot", snap.model_dump(mode="json"))
                if snap.status != "ok":
                    extra = ["open position: marks not evaluable this cycle"]
                    return abstain([f"market_data_unavailable: {snap.reason}"] + extra + ([kill_note] if kill_note else []))

            for pos in positions:
                und = position_underlying(pos)
                snap = held_snaps[und]
                mtm = mark_to_market(pos, snap, rules, daily_realized_pnl_usd=realized)
                lineage.record(cid, "mark_to_market", mtm.model_dump(mode="json"))
                trigger, mark, why = evaluate_exit(pos, snap, rules)
                if flatten:
                    why = [f"manual flatten requested (rule trigger: {trigger})"] + why
                    trigger = "manual_flatten"
                scratch.exit_trigger = trigger
                scratch.exit_reasons = why
                scratch.exit_gates = evaluate_exit_gates(
                    pos, snap, rules, flatten=flatten, daily_pnl=realized,
                )
                lineage.record(cid, "signals", {"exit_evaluation": {"position_id": pos["position_id"],
                                                                     "trigger": trigger, "mark": mark, "reasons": why,
                                                                     "daily_loss_breach": mtm.daily_loss_breach}})

            if flatten:
                scratch.phase = "flatten"
                results: list[tuple[str, list[str]]] = []
                for pos in positions:
                    und = position_underlying(pos)
                    snap = held_snaps[und]
                    _t, mark, why = evaluate_exit(pos, snap, rules)
                    why = [f"manual flatten requested"] + why
                    intent = build_exit(pos, mark, rules, strategy_name=name,
                                        idempotency_key=f"{cid}:close:{pos['position_id']}")
                    if intent is None:
                        return abstain(["flatten requested but no leg marks to price the close"] + why)
                    if kill:
                        lineage.record(cid, "kill_switch", {
                            "latched": True, "reason": kill["reason"], "since": kill["ts"],
                            "action": "exit_allowed_while_latched", "trigger": "manual_flatten",
                        })
                        why = why + [f"{kill_note}; risk-reducing exit allowed"]
                    scratch.exit_reasons = why
                    decision = Decision(action="exit", reasons=why, exit_trigger="manual_flatten")
                    commit_wal("trade", cycle_outcome="exit")
                    lineage.record(cid, "decision", decision.model_dump(mode="json"))
                    blocked = paper_send_reason(
                        mode=mode, data_source=data_source, snapshot=snap, lineage=lineage,
                    )
                    o, r = _place(
                        cid, intent, mode, broker, lineage, rules, name,
                        trigger="manual_flatten", exit_reasons=why,
                        record_only=bool(tag) or bool(blocked),
                        shadow=tag, block_reason=blocked, account_id=account_id,
                    )
                    if kill:
                        r = r + ["exit ran while kill switch latched"]
                    results.append((o, r))
                outcome, reasons = _combine(results)
                if kill and outcome != "error":
                    lineage.annotate_reasons(cid, reasons)
                return finish(outcome, reasons)

            # Hold existing structures. New names may still open below.
            scratch.phase = "hold"

        if flatten:
            return abstain(["flatten: no open strategy position"] + ([kill_note] if kill_note else []))

        scratch.entries_today = lineage.entries_since(name, mode, day_start)
        scratch.rr25_history = lineage.signal_history(name, mode, "rr25")
        scratch.opens_this_run = 0

        def _hold(reasons: list[str]) -> CycleResult:
            scratch.phase = "hold"
            enrich_entry_evals(scratch)
            commit_wal("abstain", cycle_outcome="held")
            return finish("held", reasons, Decision(action="abstain", reasons=reasons))

        if kill:
            if positions:
                return _hold(["holding position; no automated exits", kill_note, "new entries blocked"])
            scratch.phase = "entry"
            enrich_entry_evals(scratch)
            return abstain([kill_note, "new entries blocked"])

        if not scratch.in_entry_window:
            reason = (f"outside entry window {rules.execution.entry_slots_et} "
                      f"{rules.execution.entry_timezone}")
            if positions:
                return _hold(["holding position; no automated exits", reason])
            scratch.phase = "entry"
            enrich_entry_evals(scratch)
            return abstain([reason])

        if scratch.entries_today >= rules.opens_per_day():
            reason = f"max_new_opens_per_day {rules.opens_per_day()} reached"
            if positions:
                return _hold(["holding position; no automated exits", reason])
            scratch.phase = "entry"
            enrich_entry_evals(scratch)
            return abstain([reason])

        scratch.phase = "entry"

        tickers = resolve_universe(rules, provider)
        held_names = open_underlyings(positions)
        held_keys = {name_key(n) for n in held_names}
        history = scratch.rr25_history or []
        scan: list[dict[str, Any]] = []
        passing: list[tuple[float, str, MarketSnapshot, list, ComboIntent, list[str]]] = []
        first_ok: MarketSnapshot | None = scratch.snapshot

        for ticker in tickers:
            if name_key(ticker) in held_keys:
                scan.append({"ticker": ticker, "passed": False, "reason": "already_open"})
                continue
            snap = _snapshot(provider, rules, ticker, [], vendor=vendor)
            if first_ok is None and snap.status == "ok":
                first_ok = snap
            if snap.status != "ok":
                scan.append({"ticker": ticker, "passed": False, "reason": snap.reason, "status": snap.status})
                if scratch.snapshot is None:
                    scratch.snapshot = snap
                continue
            sigs = compute_signals(snap, rules, rr25_history=history)
            rr = next((s for s in sigs if s.name == "rr25"), None)
            fail = failing_required(sigs)
            if fail:
                scan.append({
                    "ticker": ticker, "passed": False, "rr25": None if rr is None else rr.value,
                    "reason": f"signal {fail[0].name}={fail[0].value} vs {fail[0].threshold} failed",
                })
                if scratch.signals is None:
                    scratch.signals = sigs
                    scratch.snapshot = snap
                continue
            intent, why = build_entry(
                snap, rules, strategy_name=name, idempotency_key=f"{cid}:open:{ticker}",
            )
            if intent is None:
                scan.append({
                    "ticker": ticker, "passed": False, "rr25": None if rr is None else rr.value,
                    "reason": why[0] if why else "construction failed",
                })
                if scratch.snapshot is None:
                    scratch.snapshot = snap
                    scratch.signals = sigs
                    scratch.entry_reasons = why
                continue
            rr_val = float(rr.value) if rr is not None and rr.value is not None else 0.0
            passing.append((rr_val, ticker, snap, sigs, intent, why))
            scan.append({"ticker": ticker, "passed": True, "rr25": rr_val})

        lineage.record(cid, "universe_scan", {
            "tickers": tickers, "held": sorted(held_names), "n_pass": len(passing), "rows": scan,
        })
        passing.sort(key=lambda row: (row[0], row[1]))  # most negative rr25 first
        remaining_day = rules.opens_per_day() - scratch.entries_today
        take_n = max(0, min(rules.opens_per_run(), remaining_day, len(passing)))
        chosen = passing[:take_n]

        if first_ok is not None and scratch.snapshot is None:
            scratch.snapshot = first_ok
        if chosen:
            scratch.snapshot = chosen[0][2]
            scratch.signals = chosen[0][3]
            scratch.entry_reasons = (
                [f"ranked {len(passing)} names by rr25; opening {len(chosen)}"]
                + [w for row in chosen for w in row[5]]
            )
        elif passing:
            scratch.snapshot = passing[0][2]
            scratch.signals = passing[0][3]
        enrich_entry_evals(scratch)
        if scratch.snapshot is not None:
            lineage.record(cid, "market_snapshot", scratch.snapshot.model_dump(mode="json"))
        if scratch.signals is not None:
            lineage.record(cid, "signals", {
                "signals": [s.model_dump(mode="json") for s in scratch.signals],
            })

        if not chosen:
            reasons = []
            statuses = [r.get("status") for r in scan]
            only_unavail = bool(scan) and all(s == "unavailable" for s in statuses) and not passing
            if only_unavail:
                first_reason = next((r.get("reason") for r in scan if r.get("reason")), "unavailable")
                reasons = [f"market_data_unavailable: {first_reason}"]
            elif not passing:
                failed_sig = next((r for r in scan if str(r.get("reason", "")).startswith("signal rr25")), None)
                if failed_sig:
                    reasons = [failed_sig["reason"]]
                else:
                    reasons = ["no liquid names cleared rr25 and 25d/25d construction"]
            else:
                reasons = [f"max_new_opens_per_run {rules.opens_per_run()} reached"]
            if positions:
                return _hold(
                    ["holding position; no automated exits"] + reasons + ([kill_note] if kill_note else []),
                )
            return abstain(reasons + ([kill_note] if kill_note else []))

        decision = Decision(
            action="enter",
            reasons=["all required signals passed"] + scratch.entry_reasons,
        )
        commit_wal("trade", cycle_outcome="enter")
        lineage.record(cid, "decision", decision.model_dump(mode="json"))

        placed: list[tuple[str, list[str]]] = []
        for _rr, ticker, snap, _sigs, intent, why in chosen:
            blocked = paper_send_reason(
                mode=mode, data_source=data_source, snapshot=snap, lineage=lineage,
            )
            o, r = _place(
                cid, intent, mode, broker, lineage, rules, name,
                record_only=bool(tag) or bool(blocked),
                shadow=tag, block_reason=blocked, account_id=account_id,
            )
            placed.append((o, r if r else why))
            scratch.opens_this_run = (scratch.opens_this_run or 0) + 1
        outcome, reasons = _combine(placed)
        if positions and outcome in ("abstained", "proposed_not_sent"):
            reasons = ["holding existing positions"] + reasons
        return finish(outcome, reasons)

    except Exception as exc:  # never crash the scheduler; record and count
        log.exception("cycle %s failed", cid)
        scratch.phase = "error"
        scratch.error = f"{type(exc).__name__}: {exc}"
        lineage.record(cid, "error", {"type": type(exc).__name__, "message": str(exc)})
        return finish("error", [f"{type(exc).__name__}: {exc}"])


def _combine(results: list[tuple[str, list[str]]]) -> tuple[str, list[str]]:
    if not results:
        return "abstained", ["no results"]
    reasons: list[str] = []
    for _o, r in results:
        reasons.extend(r)
    outcomes = [o for o, _ in results]
    for preferred in ("error", "entered", "exited", "proposed_not_sent", "held", "abstained"):
        if preferred in outcomes:
            return preferred, reasons
    return outcomes[0], reasons


def _place(cid, intent: ComboIntent, mode, broker, lineage: Lineage, rules, name, *,
           trigger: str | None = None, exit_reasons: list[str] | None = None,
           record_only: bool = False, shadow: str | None = None,
           block_reason: str | None = None,
           account_id: str | None = None) -> tuple[str, list[str]]:
    lineage.record(cid, "intent", intent.model_dump(mode="json"))
    if record_only:
        reason = block_reason or f"shadow_record_only: data_source={shadow or 'delayed'} cannot place orders"
        lineage.record(cid, "order", {"sent": False, "reason": reason})
        return "proposed_not_sent", [reason]
    if lineage.order_exists(intent.idempotency_key):
        return "abstained", [f"duplicate idempotency key {intent.idempotency_key}"]
    lineage.insert_order(intent=intent.model_dump(mode="json"), cycle_id=cid, mode=mode, status="proposed")

    def revalidate(i: ComboIntent) -> None:
        open_now = lineage.open_positions(name, mode)
        if i.purpose == "open" and lineage.kill_state(name, mode):
            raise GuardedReject("kill switch latched: new entries blocked")
        if i.purpose == "close":
            pos = next((p for p in open_now if p["position_id"] == i.position_id), None)
            if pos is None:
                raise GuardedReject("close for a position that is not open")
            legs = sorted((l.occ, l.action, l.ratio) for l in i.legs)
            held = sorted((l["occ"], l["action"], l.get("ratio", 1)) for l in pos["legs"])
            if i.action != "SELL" or legs != held or i.quantity != pos["quantity"]:
                raise GuardedReject("close does not exactly offset the open position (not risk-reducing)")
        if i.purpose == "open":
            held_keys = {name_key(n) for n in open_underlyings(open_now)}
            if name_key(i.underlying) in held_keys:
                raise GuardedReject(f"already have an open risk reversal on {i.underlying}")
            cap = rules.sizing.max_open_positions
            if cap is not None and len(open_now) >= cap:
                raise GuardedReject("max open positions reached")
        elif not any(p["position_id"] == i.position_id for p in open_now):
            raise GuardedReject("close for a position that is not open")

    try:
        placed = broker.place(intent, revalidate=revalidate)
    except IdentityError as exc:
        lineage.update_order(intent.idempotency_key, status="rejected")
        lineage.latch_kill(name, mode, f"identity at send: {exc}")
        return "error", [f"identity_failure_at_send: {exc}"]
    except GuardedReject as exc:
        lineage.update_order(intent.idempotency_key, status="not_sent")
        lineage.record(cid, "order", {"sent": False, "reason": str(exc)})
        return "proposed_not_sent", [f"not sent: {exc}"]

    oid = placed.get("broker_order_id")
    lineage.update_order(intent.idempotency_key, status="submitted", broker_order_id=oid)
    lineage.record(cid, "order", {"sent": True, **placed})
    st = placed if placed.get("status") == "Filled" else broker.wait(oid, rules.execution.fill_wait_seconds)
    if st.get("status") != "Filled":
        st = broker.cancel(oid)
    opened_cycle_id = None
    if intent.purpose == "close" and intent.position_id:
        held = lineage.get_position(intent.position_id)
        opened_cycle_id = None if held is None else held.get("opened_cycle_id")
    persisted: list[dict] = []
    for f in st.get("fills") or []:
        rec_fill = persistable_fill(f)
        if rec_fill is None:
            continue
        if opened_cycle_id:
            rec_fill = {**rec_fill, "opened_cycle_id": opened_cycle_id}
        lineage.record_fill(exec_id=rec_fill["exec_id"], idempotency_key=intent.idempotency_key,
                            broker_order_id=oid, cycle_id=cid, mode=mode, payload=rec_fill)
        persisted.append(rec_fill)
    lineage.record(cid, "fill", {"broker_order_id": oid, **{k: v for k, v in st.items() if k != "fills"},
                                 "fills": persisted})

    if st.get("status") == "Filled":
        lineage.update_order(intent.idempotency_key, status="filled")
        price = st.get("avg_fill_price")
        price = intent.limit_price if price is None else float(price)
        if intent.purpose == "open":
            lineage.open_position(position_id=f"p-{cid}-{intent.underlying}", strategy=name, mode=mode, cycle_id=cid,
                                  legs=[l.model_dump(mode="json") for l in intent.legs], entry_price=price,
                                  quantity=intent.quantity, max_loss_usd=intent.max_loss_usd)
            outcome, reasons = "entered", [f"filled {intent.action} {intent.underlying} combo @ {price:+.2f}"]
        else:
            pnl = lineage.close_position(intent.position_id, cycle_id=cid, exit_price=price, trigger=trigger or "")
            pos = lineage.get_position(intent.position_id)
            if pos is not None:
                debrief = build_debrief(
                    closed_cycle_id=cid, position=pos,
                    entry_reason="; ".join(lineage.decision_reasons(pos["opened_cycle_id"])),
                    exit_reason=(exit_reasons[0] if exit_reasons else (trigger or "")),
                    exit_trigger=trigger,
                )
                payload = debrief.model_dump(mode="json")
                lineage.record(cid, "debrief", payload)
                lineage.record_debrief(payload)
            outcome, reasons = "exited", [f"{trigger}: closed @ {price:+.2f}, realized ${pnl:.0f}"]
    else:
        lineage.update_order(intent.idempotency_key, status="cancelled")
        outcome, reasons = "abstained", [f"order {oid} not filled at limit {intent.limit_price:+.2f}; cancelled"]

    rec = reconcile(broker, lineage, strategy=name, mode=mode, underlying=None,
                    cycle_id=cid, account_id=account_id)
    if not rec["ok"] and hasattr(broker, "settle"):
        broker.settle()
        rec = reconcile(broker, lineage, strategy=name, mode=mode, underlying=None,
                        cycle_id=cid, account_id=account_id)
    lineage.record(cid, "reconcile", {"phase": "post", **rec})
    if not rec["ok"]:
        lineage.latch_kill(name, mode, "post-trade reconcile drift: " + "; ".join(rec["drift"])[:500])
        reasons = reasons + ["post_reconcile_drift"] + rec["drift"]
    return outcome, reasons
