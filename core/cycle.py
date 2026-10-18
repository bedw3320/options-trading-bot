"""Deterministic run-once cycle (Epics 1-3, v0).

reconcile -> market snapshot -> signals -> decision -> intent -> guarded order ->
fill -> reconcile -> stop. Every artifact is written under one cycle_id.
Abstention is a successful outcome. Data problems abstain; they never guess.
"""

from __future__ import annotations

import hashlib
import subprocess
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, time as dtime, timezone
from pathlib import Path
from typing import Any

from core.brokers import ExecutionBroker
from core.guarded_broker import GuardedReject
from core.identity import IdentityError
from core.market_state import MarketStateProvider
from core.reconcile import reconcile
from core.rr_rules import build_entry, build_exit, evaluate_exit
from core.signals import compute_signals, failing_required
from core.strategy_loader import load as load_strategy
from schemas.cycle import ComboIntent, Decision
from schemas.strategy import StrategyConfig
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


def _in_window(as_of: str, window: tuple[str, str]) -> bool:
    t = datetime.fromisoformat(as_of).astimezone(ET)
    lo, hi = (dtime.fromisoformat(x) for x in window)
    return t.weekday() < 5 and lo <= t.time() <= hi


def _rth(now: datetime) -> bool:
    t = now.astimezone(ET)
    return t.weekday() < 5 and dtime(9, 30) <= t.time() < dtime(16, 0)


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
) -> CycleResult:
    if mode not in MODES:
        raise ValueError(f"mode must be one of {MODES}")
    clock = now or (lambda: datetime.now(timezone.utc))
    path = Path(strategy_path)
    strategy: StrategyConfig = load_strategy(path)
    if strategy.rules is None:
        raise ValueError(f"{path} has no deterministic `rules:` block")
    rules = strategy.rules
    name = strategy.name
    sha = hashlib.sha256(path.read_bytes()).hexdigest()

    cid = lineage.start_cycle(strategy=name, strategy_version=strategy.version, strategy_sha256=sha,
                              mode=mode, git_sha=_git_sha())
    lineage.record(cid, "inputs", {
        "strategy_path": str(path), "strategy_sha256": sha, "version": strategy.version, "mode": mode,
        "allow_trading": allow_trading, "flatten": flatten, "started_at": clock().isoformat(), "rules": rules.model_dump(mode="json"),
    })

    def finish(outcome: str, reasons: list[str], decision: Decision | None = None) -> CycleResult:
        if decision is not None:
            lineage.record(cid, "decision", decision.model_dump(mode="json"))
        lineage.end_cycle(cid, outcome, reasons)
        if outcome == "error":
            recent = lineage.recent_outcomes(name, mode, rules.kill_switch.max_consecutive_errors)
            if len(recent) >= rules.kill_switch.max_consecutive_errors and all(o == "error" for o in recent):
                lineage.latch_kill(name, mode, f"{len(recent)} consecutive error cycles")
        return CycleResult(cid, outcome, reasons)

    def abstain(reasons: list[str]) -> CycleResult:
        return finish("abstained", reasons, Decision(action="abstain", reasons=reasons))

    try:
        # 1. Kill switch (latched until `rearm`): blocks new entries only. Risk-reducing
        #    exits of existing strategy positions (exit rules or `flatten`) still run,
        #    through the same identity gate, reconcile and GuardedBroker path.
        kill = lineage.kill_state(name, mode)

        # 2. Paper-only enforcement. Dry-run never touches a broker account.
        if mode == "paper":
            try:
                if identity_check is None:
                    raise IdentityError("no identity check configured for paper mode")
                account = identity_check()
                if not account.upper().startswith(rules.execution.required_account_prefix):
                    raise IdentityError(f"account {account} is not {rules.execution.required_account_prefix}*")
                lineage.record(cid, "inputs", {"identity": {"account": account, "trading_mode": "paper"}})
            except IdentityError as exc:
                lineage.latch_kill(name, mode, f"identity: {exc}")
                lineage.record(cid, "kill_switch", {"latched": True, "reason": f"identity: {exc}"})
                return finish("error", [f"identity_failure: {exc}"])
            if not _rth(clock()):
                return abstain(["market_closed (outside 09:30-16:00 ET weekdays)"])

        # 3. Reconcile before deciding (IBKR is authoritative).
        rec = reconcile(broker, lineage, strategy=name, mode=mode, underlying=rules.underlying, cycle_id=cid)
        lineage.record(cid, "reconcile", {"phase": "pre", **rec})
        if not rec["ok"]:
            # Drift blocks exits too: the position we would close cannot be verified.
            lineage.latch_kill(name, mode, "reconcile drift: " + "; ".join(rec["drift"])[:500])
            return abstain(["reconcile_drift"] + rec["drift"])

        # 4. Daily loss latch.
        day_start = _et_midnight_utc_iso(clock())
        realized = lineage.realized_pnl_since(name, mode, day_start)
        if realized <= -rules.kill_switch.daily_loss_limit_usd:
            lineage.latch_kill(name, mode, f"daily realized loss ${realized:.0f}")
        kill = lineage.kill_state(name, mode)
        kill_note = f"kill_switch_latched: {kill['reason']} (since {kill['ts']})" if kill else None

        # 5. Market state.
        positions = lineage.open_positions(name, mode)
        held_legs = [leg for p in positions for leg in p["legs"]]
        snap = provider.snapshot(rules, held_legs=held_legs)
        lineage.record(cid, "market_snapshot", snap.model_dump(mode="json"))
        if snap.status != "ok":
            extra = ["open position: exits not evaluable this cycle"] if positions else []
            return abstain([f"market_data_unavailable: {snap.reason}"] + extra + ([kill_note] if kill_note else []))

        # 6a. Manage the open position (max one).
        if positions:
            pos = positions[0]
            trigger, mark, why = evaluate_exit(pos, snap, rules)
            if flatten:
                why = [f"manual flatten requested (rule trigger: {trigger})"] + why
                trigger = "manual_flatten"
            lineage.record(cid, "signals", {"exit_evaluation": {"position_id": pos["position_id"],
                                                                 "trigger": trigger, "mark": mark, "reasons": why}})
            if trigger is None:
                return finish("held", why + ([kill_note] if kill_note else []),
                              Decision(action="abstain", reasons=["holding position"] + why))
            intent = build_exit(pos, mark, rules, strategy_name=name, idempotency_key=f"{cid}:close")
            if intent is None:
                return abstain([f"exit trigger {trigger} but no leg marks to price the close"] + why)
            if kill:
                lineage.record(cid, "kill_switch", {"latched": True, "reason": kill["reason"], "since": kill["ts"],
                                                    "action": "exit_allowed_while_latched", "trigger": trigger})
                why = why + [f"{kill_note}; risk-reducing exit allowed"]
            decision = Decision(action="exit", reasons=why, exit_trigger=trigger)
            lineage.record(cid, "decision", decision.model_dump(mode="json"))
            res = _execute(cid, intent, mode, broker, lineage, rules, name, finish, trigger=trigger)
            if kill:
                res.reasons.append("exit ran while kill switch latched")
                lineage.annotate_reasons(cid, res.reasons)
            return res

        if flatten:
            return abstain(["flatten: no open strategy position"] + ([kill_note] if kill_note else []))
        if kill:
            return abstain([kill_note, "new entries blocked"])

        # 6b. Entry.
        if lineage.entries_since(name, mode, day_start) >= rules.sizing.max_entries_per_day:
            return abstain([f"max_entries_per_day {rules.sizing.max_entries_per_day} reached"])
        history = lineage.signal_history(name, mode, "rr25")
        signals = compute_signals(snap, rules, rr25_history=history)
        lineage.record(cid, "signals", {"signals": [s.model_dump(mode="json") for s in signals]})
        if not _in_window(snap.as_of, rules.execution.entry_window_et):
            return abstain([f"outside entry window {rules.execution.entry_window_et} ET"])
        failing = failing_required(signals)
        if failing:
            return abstain([f"signal {s.name}={s.value} vs {s.threshold} failed"
                            + (f" ({s.note})" if s.note else "") for s in failing])
        intent, why = build_entry(snap, rules, strategy_name=name, idempotency_key=f"{cid}:open")
        if intent is None:
            return abstain(why)
        decision = Decision(action="enter", reasons=["all required signals passed"] + why)
        lineage.record(cid, "decision", decision.model_dump(mode="json"))
        return _execute(cid, intent, mode, broker, lineage, rules, name, finish)
    except Exception as exc:  # never crash the scheduler; record and count
        log.exception("cycle %s failed", cid)
        lineage.record(cid, "error", {"type": type(exc).__name__, "message": str(exc)})
        return finish("error", [f"{type(exc).__name__}: {exc}"])


def _execute(cid, intent: ComboIntent, mode, broker, lineage: Lineage, rules, name, finish, *,
             trigger: str | None = None) -> CycleResult:
    lineage.record(cid, "intent", intent.model_dump(mode="json"))
    if lineage.order_exists(intent.idempotency_key):
        return finish("abstained", [f"duplicate idempotency key {intent.idempotency_key}"])
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
            if len(open_now) >= rules.sizing.max_open_positions:
                raise GuardedReject("max open positions reached")
            if i.max_loss_usd is None or i.max_loss_usd > rules.sizing.max_loss_usd:
                raise GuardedReject("max loss over cap")
        elif not any(p["position_id"] == i.position_id for p in open_now):
            raise GuardedReject("close for a position that is not open")

    try:
        placed = broker.place(intent, revalidate=revalidate)
    except IdentityError as exc:
        lineage.update_order(intent.idempotency_key, status="rejected")
        lineage.latch_kill(name, mode, f"identity at send: {exc}")
        return finish("error", [f"identity_failure_at_send: {exc}"])
    except GuardedReject as exc:
        lineage.update_order(intent.idempotency_key, status="not_sent")
        lineage.record(cid, "order", {"sent": False, "reason": str(exc)})
        return finish("proposed_not_sent", [f"not sent: {exc}"])

    oid = placed.get("broker_order_id")
    lineage.update_order(intent.idempotency_key, status="submitted", broker_order_id=oid)
    lineage.record(cid, "order", {"sent": True, **placed})
    st = placed if placed.get("status") == "Filled" else broker.wait(oid, rules.execution.fill_wait_seconds)
    if st.get("status") != "Filled":
        st = broker.cancel(oid)
    for f in st.get("fills") or []:
        if f.get("exec_id"):
            lineage.record_fill(exec_id=f["exec_id"], idempotency_key=intent.idempotency_key,
                                broker_order_id=oid, cycle_id=cid, mode=mode, payload=f)
    lineage.record(cid, "fill", {"broker_order_id": oid, **{k: v for k, v in st.items() if k != "fills"},
                                 "fills": st.get("fills") or []})

    if st.get("status") == "Filled":
        lineage.update_order(intent.idempotency_key, status="filled")
        price = st.get("avg_fill_price")
        price = intent.limit_price if price is None else float(price)
        if intent.purpose == "open":
            lineage.open_position(position_id=f"p-{cid}", strategy=name, mode=mode, cycle_id=cid,
                                  legs=[l.model_dump(mode="json") for l in intent.legs], entry_price=price,
                                  quantity=intent.quantity, max_loss_usd=intent.max_loss_usd)
            outcome, reasons = "entered", [f"filled {intent.action} combo @ {price:+.2f}"]
        else:
            pnl = lineage.close_position(intent.position_id, cycle_id=cid, exit_price=price, trigger=trigger or "")
            outcome, reasons = "exited", [f"{trigger}: closed @ {price:+.2f}, realized ${pnl:.0f}"]
    else:
        lineage.update_order(intent.idempotency_key, status="cancelled")
        outcome, reasons = "abstained", [f"order {oid} not filled at limit {intent.limit_price:+.2f}; cancelled"]

    rec = reconcile(broker, lineage, strategy=name, mode=mode, underlying=rules.underlying, cycle_id=cid)
    if not rec["ok"] and hasattr(broker, "settle"):
        broker.settle()  # IB position updates can lag a fill by a moment; retry once
        rec = reconcile(broker, lineage, strategy=name, mode=mode, underlying=rules.underlying, cycle_id=cid)
    lineage.record(cid, "reconcile", {"phase": "post", **rec})
    if not rec["ok"]:
        lineage.latch_kill(name, mode, "post-trade reconcile drift: " + "; ".join(rec["drift"])[:500])
        reasons = reasons + ["post_reconcile_drift"] + rec["drift"]
    return finish(outcome, reasons)
