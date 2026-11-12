"""Versioned gate catalog and full (no short-circuit) evaluation.

Decision behavior stays in core/cycle.py and core/rr_rules.py. This module
only *records* every gate for every candidate so a later `explain` can show
what else would have blocked and how close passing gates were.

There are no learned weights. Ranking is richest rr25 first, then the
deterministic 25d/25d listed-strike construction (see RANKING_DESCRIPTION).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from core.rr_rules import combo_mark, spread_pct
from core.signals import dte, snapshot_date
from schemas.cycle import MarketSnapshot, OptionRow, SignalValue
from schemas.decision import GateEval
from schemas.strategy import DeterministicRules

RANKING_DESCRIPTION = (
    "No learned weights. Names that clear rr25 <= max_rr25 and 25d/25d liquidity "
    "are ranked by richest rr25 (most negative first). Construction picks the listed "
    "short put closest |delta| to 0.25 (then higher strike) and the listed long call "
    "closest delta to 0.25 (then lower strike), same expiry, 1 lot. No second risk "
    "reversal on a name that already has an open position. Up to 5 new opens per run "
    "and 10 per day; no outstanding position-count cap."
)

CYCLE_GATES: dict[str, str] = {
    "identity_ok": "bool",
    "market_open": "bool",
    "reconcile_ok": "bool",
    "market_data_ok": "bool",
    "flatten_has_position": "bool",
    "kill_switch_clear": "bool",
    "max_new_opens_per_day": "count",
    "max_new_opens_per_run": "count",
    "entry_window": "bool",
    "dte_min": "dte",
    "dte_max": "dte",
    "signal_rr25": "vol_diff",
    "signal_put_call_iv_ratio": "ratio",
    "signal_atm_iv_minus_rv": "vol_diff",
    "signal_rr25_percentile": "percentile",
    "signal_event_blackout": "count",
}

CONSTRUCTION_GATES: dict[str, str] = {
    "short_put_delta_min": "abs_delta",
    "short_put_delta_max": "abs_delta",
    "short_put_bid_ask": "bool",
    "short_put_spread_pct": "pct_of_mid",
    "short_put_open_interest": "contracts",
    "call_delta_min": "abs_delta",
    "call_delta_max": "abs_delta",
    "call_bid_ask": "bool",
    "call_spread_pct": "pct_of_mid",
    "call_open_interest": "contracts",
}

EXIT_GATES: dict[str, str] = {
    "exit_marks_available": "bool",
    "manual_flatten": "bool",
}

CATALOG_UNITS: dict[str, str] = {**CYCLE_GATES, **CONSTRUCTION_GATES, **EXIT_GATES}

SIGNAL_META: dict[str, tuple[str, str]] = {
    "rr25": ("le", "vol_diff"),
    "put_call_iv_ratio": ("ge", "ratio"),
    "atm_iv_minus_rv": ("gt", "vol_diff"),
    "rr25_percentile": ("ge", "percentile"),
    "event_blackout": ("eq", "count"),
}

ENTRY_BIND_ORDER = (
    "identity_ok",
    "market_open",
    "reconcile_ok",
    "market_data_ok",
    "flatten_has_position",
    "kill_switch_clear",
    "max_new_opens_per_day",
    "max_new_opens_per_run",
    "entry_window",
    "dte_min",
    "dte_max",
    "signal_rr25",
    "signal_put_call_iv_ratio",
    "signal_atm_iv_minus_rv",
    "signal_rr25_percentile",
    "signal_event_blackout",
)

CONSTRUCTION_BIND_ORDER = (
    "short_put_delta_min",
    "short_put_delta_max",
    "short_put_bid_ask",
    "short_put_spread_pct",
    "short_put_open_interest",
    "call_delta_min",
    "call_delta_max",
    "call_bid_ask",
    "call_spread_pct",
    "call_open_interest",
)


def signed_margin(value: float | None, operator: str | None, threshold: float | None) -> float | None:
    if value is None or operator is None or threshold is None:
        return None
    denom = abs(threshold) if threshold != 0 else 1.0
    if operator in ("le", "lt"):
        return (threshold - value) / denom
    if operator in ("ge", "gt"):
        return (value - threshold) / denom
    if operator == "eq":
        return 1.0 if value == threshold else -1.0
    return None


def _eval(
    gate: str,
    value: float | None,
    operator: str,
    threshold: float | None,
    *,
    candidate_id: str | None = None,
    skip_reason: str | None = None,
) -> GateEval:
    unit = CATALOG_UNITS[gate]
    if skip_reason is not None:
        return GateEval(
            gate=gate, candidate_id=candidate_id, value=value, operator=operator,
            threshold=threshold, unit=unit, result="skipped", skip_reason=skip_reason,
        )
    if value is None or threshold is None:
        return GateEval(
            gate=gate, candidate_id=candidate_id, value=value, operator=operator,
            threshold=threshold, unit=unit, result="skipped",
            skip_reason="value or threshold unavailable",
        )
    passed = {
        "le": value <= threshold,
        "lt": value < threshold,
        "ge": value >= threshold,
        "gt": value > threshold,
        "eq": value == threshold,
    }[operator]
    return GateEval(
        gate=gate, candidate_id=candidate_id, value=value, operator=operator,
        threshold=threshold, unit=unit, result="pass" if passed else "fail",
        margin=signed_margin(value, operator, threshold),
    )


def _skip_group(
    names: dict[str, str], reason: str, *, candidate_id: str | None = None
) -> list[GateEval]:
    return [
        GateEval(gate=g, candidate_id=candidate_id, unit=u, result="skipped", skip_reason=reason)
        for g, u in names.items()
    ]


def _bool_gate(gate: str, ok: bool | None, *, skip_reason: str | None = None,
               candidate_id: str | None = None) -> GateEval:
    if ok is None or skip_reason:
        return _eval(gate, None, "eq", 1.0, candidate_id=candidate_id,
                     skip_reason=skip_reason or "not evaluated")
    return _eval(gate, 1.0 if ok else 0.0, "eq", 1.0, candidate_id=candidate_id)


def _liquidity(row: OptionRow | None, prefix: str, rules: DeterministicRules,
               candidate_id: str, missing: str) -> list[GateEval]:
    bid_ask, spread, oi = f"{prefix}_bid_ask", f"{prefix}_spread_pct", f"{prefix}_open_interest"
    if row is None:
        return [
            _eval(bid_ask, None, "eq", 1.0, candidate_id=candidate_id, skip_reason=missing),
            _eval(spread, None, "le", rules.structure.max_spread_pct_of_mid,
                  candidate_id=candidate_id, skip_reason=missing),
            _eval(oi, None, "ge", float(rules.structure.min_open_interest),
                  candidate_id=candidate_id, skip_reason=missing),
        ]
    pct = spread_pct(row)
    has_mid = pct is not None
    out = [_eval(bid_ask, 1.0 if has_mid else 0.0, "eq", 1.0, candidate_id=candidate_id)]
    if has_mid:
        out.append(_eval(spread, pct, "le", rules.structure.max_spread_pct_of_mid,
                         candidate_id=candidate_id))
    else:
        out.append(_eval(spread, None, "le", rules.structure.max_spread_pct_of_mid,
                         candidate_id=candidate_id, skip_reason=f"{row.occ}: no bid/ask"))
    if row.open_interest is None:
        out.append(_eval(oi, None, "ge", float(rules.structure.min_open_interest),
                         candidate_id=candidate_id, skip_reason=f"{row.occ}: open interest unavailable"))
    else:
        out.append(_eval(oi, float(row.open_interest), "ge", float(rules.structure.min_open_interest),
                         candidate_id=candidate_id))
    return out


@dataclass
class CycleGateCtx:
    identity_ok: bool | None = None
    identity_skip: str | None = None
    market_open: bool | None = None
    market_open_skip: str | None = None
    reconcile_ok: bool | None = None
    reconcile_skip: str | None = None
    market_data_ok: bool | None = None
    market_data_skip: str | None = None
    flatten: bool = False
    has_position: bool = False
    kill_latched: bool | None = None
    kill_skip: str | None = None
    entries_today: int | None = None
    opens_this_run: int | None = None
    max_entries: int | None = None
    max_per_run: int | None = None
    in_entry_window: bool | None = None
    window_skip: str | None = None
    dte_days: int | None = None
    dte_skip: str | None = None
    dte_min: int | None = None
    dte_max: int | None = None
    signals: list[SignalValue] | None = None
    signals_skip: str | None = None
    phase: str = "entry"


def evaluate_cycle_gates(ctx: CycleGateCtx, rules: DeterministicRules) -> list[GateEval]:
    """Every cycle-level gate, including skipped-with-reason. No short-circuit."""
    day_cap = float(ctx.max_entries if ctx.max_entries is not None else rules.opens_per_day())
    run_cap = float(ctx.max_per_run if ctx.max_per_run is not None else rules.opens_per_run())
    out: list[GateEval] = [
        _bool_gate("identity_ok", ctx.identity_ok, skip_reason=ctx.identity_skip),
        _bool_gate("market_open", ctx.market_open, skip_reason=ctx.market_open_skip),
        _bool_gate("reconcile_ok", ctx.reconcile_ok, skip_reason=ctx.reconcile_skip),
        _bool_gate("market_data_ok", ctx.market_data_ok, skip_reason=ctx.market_data_skip),
    ]
    if ctx.flatten:
        out.append(_bool_gate("flatten_has_position", ctx.has_position))
    else:
        out.append(_bool_gate("flatten_has_position", None, skip_reason="flatten not requested"))
    if ctx.phase in ("exit", "hold") and not ctx.flatten:
        out.append(_bool_gate("kill_switch_clear", None,
                             skip_reason="kill switch does not block hold/flatten"))
    else:
        out.append(_bool_gate("kill_switch_clear", None if ctx.kill_latched is None else (not ctx.kill_latched),
                             skip_reason=ctx.kill_skip))
    if ctx.phase in ("exit", "hold") and not ctx.flatten:
        out.append(_eval("max_new_opens_per_day", None, "lt", day_cap,
                         skip_reason="open position: entry cap not used"))
        out.append(_eval("max_new_opens_per_run", None, "lt", run_cap,
                         skip_reason="open position: entry cap not used"))
        out.append(_bool_gate("entry_window", None, skip_reason="open position: entry window not used"))
    else:
        if ctx.entries_today is None:
            out.append(_eval("max_new_opens_per_day", None, "lt", day_cap,
                             skip_reason="entries_today unavailable"))
        else:
            out.append(_eval("max_new_opens_per_day", float(ctx.entries_today), "lt", day_cap))
        run_n = 0.0 if ctx.opens_this_run is None else float(ctx.opens_this_run)
        out.append(_eval("max_new_opens_per_run", run_n, "lt", run_cap))
        out.append(_bool_gate("entry_window", ctx.in_entry_window, skip_reason=ctx.window_skip))

    if ctx.dte_days is None:
        out.append(_eval("dte_min", None, "ge", float(ctx.dte_min or rules.structure.dte_min),
                         skip_reason=ctx.dte_skip or "no expiry"))
        out.append(_eval("dte_max", None, "le", float(ctx.dte_max or rules.structure.dte_max),
                         skip_reason=ctx.dte_skip or "no expiry"))
    else:
        out.append(_eval("dte_min", float(ctx.dte_days), "ge", float(rules.structure.dte_min)))
        out.append(_eval("dte_max", float(ctx.dte_days), "le", float(rules.structure.dte_max)))

    if ctx.signals is None:
        out.extend(
            GateEval(gate=f"signal_{n}", unit=u, operator=op, result="skipped",
                     skip_reason=ctx.signals_skip or "signals not evaluated",
                     threshold=_signal_threshold(n, rules))
            for n, (op, u) in SIGNAL_META.items()
        )
    else:
        by = {s.name: s for s in ctx.signals}
        for name, (op, unit) in SIGNAL_META.items():
            s = by.get(name)
            if s is None:
                out.append(GateEval(gate=f"signal_{name}", unit=unit, operator=op, result="skipped",
                                    skip_reason="signal not computed",
                                    threshold=_signal_threshold(name, rules)))
                continue
            if s.passed is None or (not s.required and not s.passed):
                out.append(GateEval(
                    gate=f"signal_{name}", value=s.value, operator=op, threshold=s.threshold,
                    unit=unit, result="skipped",
                    skip_reason=s.note or ("informational; not required" if not s.required else "not evaluated"),
                    margin=signed_margin(s.value, op, s.threshold),
                ))
            else:
                out.append(GateEval(
                    gate=f"signal_{name}", value=s.value, operator=op, threshold=s.threshold,
                    unit=unit, result="pass" if s.passed else "fail",
                    margin=signed_margin(s.value, op, s.threshold),
                ))
    return out


def _signal_threshold(name: str, rules: DeterministicRules) -> float:
    sig = rules.signals
    return {
        "rr25": sig.max_rr25,
        "put_call_iv_ratio": sig.min_put_call_iv_ratio,
        "atm_iv_minus_rv": 0.0,
        "rr25_percentile": sig.skew_percentile_min,
        "event_blackout": 0.0,
    }[name]


@dataclass
class ConstructionReport:
    candidates: list[dict[str, Any]] = field(default_factory=list)
    gates: list[GateEval] = field(default_factory=list)
    chosen_id: str | None = None
    chosen_legs: list[OptionRow] = field(default_factory=list)


def _abs_delta(row: OptionRow | None) -> float | None:
    if row is None or row.delta is None:
        return None
    return abs(row.delta)


def evaluate_construction(snapshot: MarketSnapshot, rules: DeterministicRules) -> ConstructionReport:
    """Every construction gate for every (short put, long call) in the 25d band."""
    report = ConstructionReport()
    if snapshot.status != "ok":
        report.gates = _skip_group(CONSTRUCTION_GATES, "no market snapshot")
        return report
    if snapshot.expiry is None:
        report.gates = _skip_group(CONSTRUCTION_GATES, "no expiry in DTE window")
        return report
    s = rules.structure
    rows = [r for r in snapshot.options if r.expiry == snapshot.expiry]
    puts = [r for r in rows if r.right == "P"]
    calls = [r for r in rows if r.right == "C"]
    if not puts:
        report.gates = _skip_group(CONSTRUCTION_GATES, "no puts on expiry")
        return report
    call_list: list[OptionRow | None] = list(calls) if calls else [None]

    scored: list[tuple[tuple, str, list[GateEval], list[dict[str, Any]], bool]] = []
    for short in puts:
        for call in call_list:
            cid = f"{short.occ}|{call.occ if call else 'NONE'}"
            gates: list[GateEval] = []
            ad = _abs_delta(short)
            gates.append(_eval("short_put_delta_min", ad, "ge", s.short_put_delta_min, candidate_id=cid,
                               skip_reason=None if ad is not None else f"{short.occ}: delta missing"))
            gates.append(_eval("short_put_delta_max", ad, "le", s.short_put_delta_max, candidate_id=cid,
                               skip_reason=None if ad is not None else f"{short.occ}: delta missing"))
            gates.extend(_liquidity(short, "short_put", rules, cid, f"{short.occ}: missing"))
            cad = _abs_delta(call)
            gates.append(_eval("call_delta_min", cad, "ge", s.long_call_delta_min, candidate_id=cid,
                               skip_reason=None if cad is not None else "no call on expiry"))
            gates.append(_eval("call_delta_max", cad, "le", s.long_call_delta_max, candidate_id=cid,
                               skip_reason=None if cad is not None else "no call on expiry"))
            gates.extend(_liquidity(call, "call", rules, cid, "no call on expiry"))
            passed = all(g.result == "pass" for g in gates)
            d_short = abs(ad - s.short_put_delta_target) if ad is not None else 99.0
            d_call = abs(cad - s.long_call_delta_target) if cad is not None else 99.0
            key = (d_short, -(short.strike), d_call, call.strike if call is not None else 9999.0)
            legs = [
                {"occ": short.occ, "action": "SELL", "right": "P", "strike": short.strike,
                 "delta": short.delta, "bid": short.bid, "ask": short.ask},
            ]
            if call:
                legs.append({"occ": call.occ, "action": "BUY", "right": "C", "strike": call.strike,
                             "delta": call.delta, "bid": call.bid, "ask": call.ask})
            scored.append((key, cid, gates, legs, passed))

    scored.sort(key=lambda x: x[0])
    winner = next((c for c in scored if c[4]), None)
    for rank, (_key, cid, gates, legs, passed) in enumerate(scored, start=1):
        chosen = winner is not None and cid == winner[1]
        fail = next((g.gate for g in gates if g.result == "fail"), None)
        skip = next((g.gate for g in gates if g.result == "skipped"), None)
        rejected = None if chosen else (fail or skip or "ranked_below")
        report.candidates.append({
            "candidate_id": cid, "legs": legs, "rank": rank, "chosen": chosen,
            "rejected_reason": rejected, "underlying": snapshot.underlying,
        })
        report.gates.extend(gates)
        if chosen:
            report.chosen_id = cid
    return report


def evaluate_exit_gates(
    position: dict[str, Any],
    snapshot: MarketSnapshot,
    rules: DeterministicRules,
    *,
    flatten: bool,
    daily_pnl: float,
) -> list[GateEval]:
    """In-force exit gates: marks + manual flatten. No yellow-zone distances."""
    del daily_pnl, rules
    legs = position.get("legs") or []
    if not legs:
        return _skip_group(EXIT_GATES, "position has no legs")
    mark = combo_mark(position, snapshot.held_marks)
    out = [_bool_gate("exit_marks_available", mark is not None)]
    if flatten:
        out.append(_bool_gate("manual_flatten", True))
    else:
        out.append(_bool_gate("manual_flatten", None, skip_reason="flatten not requested; no automated exits"))
    return out


def binding_gate(
    *,
    phase: str,
    cycle_gates: list[GateEval],
    construction: ConstructionReport | None,
    exit_gates: list[GateEval] | None,
    flatten: bool,
    required_signals: set[str] | None = None,
) -> str | None:
    """First failing required gate in the live short-circuit order. Recording is not this."""
    by = {g.gate: g for g in cycle_gates if g.candidate_id is None}
    req = required_signals or {"rr25"}

    def failed(name: str) -> bool:
        g = by.get(name)
        return g is not None and g.result == "fail"

    if phase == "error":
        if failed("identity_ok"):
            return "identity_ok"
        return "error"

    for name in ("identity_ok", "market_open", "reconcile_ok", "market_data_ok"):
        if failed(name):
            return name
    if flatten and failed("flatten_has_position"):
        return "flatten_has_position"
    if phase == "entry":
        for name in ("kill_switch_clear", "max_new_opens_per_day", "max_new_opens_per_run", "entry_window"):
            if failed(name):
                return name
        for name in ("signal_rr25", "signal_put_call_iv_ratio", "signal_atm_iv_minus_rv",
                     "signal_rr25_percentile", "signal_event_blackout"):
            g = by.get(name)
            if g is None or g.result != "fail":
                continue
            raw = name.removeprefix("signal_")
            if raw in req:
                return name
        for name in ("dte_min", "dte_max"):
            if failed(name):
                return name
        if construction and construction.chosen_id:
            return None
        if construction:
            return _construction_binding(construction)
        return None

    if flatten:
        if exit_gates and any(g.gate == "exit_marks_available" and g.result == "fail" for g in exit_gates):
            return "exit_marks_available"
        return "manual_flatten"
    return None  # hold: no automated exit trigger


def _construction_binding(construction: ConstructionReport) -> str | None:
    if not construction.candidates:
        return "short_put_delta_min"
    in_band: list[dict[str, Any]] = []
    for c in construction.candidates:
        gs = [g for g in construction.gates if g.candidate_id == c["candidate_id"]]
        by = {g.gate: g for g in gs}
        dmin, dmax = by.get("short_put_delta_min"), by.get("short_put_delta_max")
        if dmin and dmax and dmin.result == "pass" and dmax.result == "pass":
            in_band.append(c)
    pool = in_band or construction.candidates
    best = min(pool, key=lambda c: c["rank"] or 10**9)
    gs = [g for g in construction.gates if g.candidate_id == best["candidate_id"]]
    by = {g.gate: g for g in gs}
    for name in CONSTRUCTION_BIND_ORDER:
        g = by.get(name)
        if g is not None and g.result == "fail":
            return name
        if g is not None and g.result == "skipped" and name in (
            "short_put_bid_ask", "call_bid_ask",
        ):
            return name
    return best.get("rejected_reason")


def derive_reasons(
    binding: str | None,
    *,
    phase: str,
    cycle_gates: list[GateEval],
    construction: ConstructionReport | None,
    exit_gates: list[GateEval] | None,
    extra: dict[str, Any],
) -> list[str]:
    """Abstain/hold text from gate evaluations so it cannot drift from the record."""
    by = {g.gate: g for g in cycle_gates if g.candidate_id is None}
    if binding == "identity_ok":
        return [f"identity_failure: {extra.get('identity_error', '')}".rstrip(": ")]
    if binding == "market_open":
        return ["market_closed (outside 09:30-16:00 ET weekdays)"]
    if binding == "reconcile_ok":
        return ["reconcile_drift"] + list(extra.get("reconcile_drift") or [])
    if binding == "market_data_ok":
        reason = extra.get("snapshot_reason") or "unavailable"
        bits = [f"market_data_unavailable: {reason}"]
        if extra.get("has_position"):
            bits.append("open position: marks not evaluable this cycle")
        if extra.get("kill_note"):
            bits.append(extra["kill_note"])
        return bits
    if binding == "flatten_has_position":
        bits = ["flatten: no open strategy position"]
        if extra.get("kill_note"):
            bits.append(extra["kill_note"])
        return bits
    if binding == "kill_switch_clear":
        return [extra.get("kill_note") or "kill_switch_latched", "new entries blocked"]
    if binding == "max_new_opens_per_day":
        n = extra.get("max_entries")
        return [f"max_new_opens_per_day {n} reached"]
    if binding == "max_new_opens_per_run":
        n = extra.get("max_per_run")
        return [f"max_new_opens_per_run {n} reached"]
    if binding == "entry_window":
        slots = extra.get("entry_slots") or extra.get("entry_window")
        return [f"outside entry window {slots} {extra.get('entry_timezone') or 'America/Toronto'}"]
    if binding == "dte_min" or binding == "dte_max":
        g = by.get(binding)
        if extra.get("expiry") is None:
            return ["no expiry in DTE window"]
        return [f"expiry {extra.get('expiry')} DTE {g.value:.0f} outside "
                f"[{extra.get('dte_min')},{extra.get('dte_max')}]"] if g and g.value is not None else (
            ["no expiry in DTE window"]
        )
    if binding and binding.startswith("signal_"):
        raw = binding.removeprefix("signal_")
        g = by.get(binding)
        note = extra.get("signal_notes", {}).get(raw)
        line = f"signal {raw}={None if g is None else g.value} vs {None if g is None else g.threshold} failed"
        if note:
            line += f" ({note})"
        return [line]
    if binding == "manual_flatten":
        return extra.get("exit_reasons") or ["manual flatten requested"]
    if binding and binding.startswith("exit_"):
        if binding == "exit_marks_available":
            return ["flatten requested but no leg marks to price the close"] + list(extra.get("exit_reasons") or [])
        return list(extra.get("exit_reasons") or [binding])
    if phase == "hold":
        return list(extra.get("exit_reasons") or ["holding position; no automated exits"])
    if construction and not construction.chosen_id:
        return _construction_reasons(binding, construction, extra)
    if construction and construction.chosen_id:
        return extra.get("entry_reasons") or ["all required signals passed"]
    if phase == "error":
        return [extra.get("error") or "error"]
    return extra.get("fallback_reasons") or (["abstain"] if binding else ["ok"])


def _construction_reasons(
    binding: str | None, construction: ConstructionReport, extra: dict[str, Any]
) -> list[str]:
    smin, smax = extra.get("short_put_delta_min"), extra.get("short_put_delta_max")
    cmin, cmax = extra.get("long_call_delta_min"), extra.get("long_call_delta_max")
    if not construction.candidates or binding in ("short_put_delta_min", "short_put_delta_max"):
        return [f"no liquid short put with |delta| in [{smin},{smax}]"]
    best = min(construction.candidates, key=lambda c: c["rank"] or 10**9)
    gs = {g.gate: g for g in construction.gates if g.candidate_id == best["candidate_id"]}
    if binding in ("short_put_bid_ask", "short_put_spread_pct", "short_put_open_interest"):
        why = _liq_text(gs, "short_put", extra.get("min_oi"), extra.get("max_spread"))
        return [f"no liquid short put with |delta| in [{smin},{smax}]"] + why[:3]
    if binding in ("call_delta_min", "call_delta_max", "call_bid_ask", "call_spread_pct", "call_open_interest"):
        return [f"no liquid call with delta in [{cmin},{cmax}]"]
    return [binding or "construction failed"]


def _liq_text(by: dict[str, GateEval], prefix: str, min_oi: Any, max_spread: Any) -> list[str]:
    bid = by.get(f"{prefix}_bid_ask")
    if bid and bid.result == "fail":
        return [f"{_occ_from_cid(bid.candidate_id, prefix)}: no bid/ask"]
    sp = by.get(f"{prefix}_spread_pct")
    if sp and sp.result == "fail" and sp.value is not None:
        return [f"{_occ_from_cid(sp.candidate_id, prefix)}: spread {sp.value:.1f}% > {max_spread}% of mid"]
    oi = by.get(f"{prefix}_open_interest")
    if oi and oi.result == "skipped":
        return [f"{_occ_from_cid(oi.candidate_id, prefix)}: open interest unavailable"]
    if oi and oi.result == "fail" and oi.value is not None:
        return [f"{_occ_from_cid(oi.candidate_id, prefix)}: OI {oi.value:.0f} < {min_oi}"]
    return []


def _occ_from_cid(cid: str | None, prefix: str) -> str:
    if not cid:
        return "?"
    parts = (cid.split("|") + ["NONE", "NONE"])[:2]
    short, call = parts[0], parts[1]
    return {"short_put": short, "call": call}.get(prefix, short)


def closest_margins(
    gates: list[GateEval], n: int = 3, *, names: set[str] | None = None
) -> list[GateEval]:
    scored = [g for g in gates if g.result != "skipped" and g.margin is not None and g.unit != "bool"]
    if names is not None:
        scored = [g for g in scored if g.gate in names]
    scored.sort(key=lambda g: g.margin)
    seen: set[str] = set()
    out: list[GateEval] = []
    for g in scored:
        if g.gate in seen:
            continue
        seen.add(g.gate)
        out.append(g)
        if len(out) >= n:
            break
    return out


def source_class(source: str | None) -> Literal["live", "delayed", "fixture"]:
    s = (source or "").lower()
    if "fixture" in s:
        return "fixture"
    if any(tok in s for tok in ("cboe", "delayed", "indicative", "frozen")):
        return "delayed"
    return "live"


def data_trust_flag(*, source: str | None, age_seconds: float | None) -> str:
    cls = source_class(source)
    stale = cls in ("live", "delayed") and age_seconds is not None and age_seconds > 15 * 60
    if cls == "delayed" and stale:
        return "delayed+stale"
    if cls == "delayed":
        return "delayed"
    if stale:
        return "stale"
    return "ok"


def replay_fingerprint(record: dict[str, Any]) -> dict[str, Any]:
    """Comparable slice: outcome, binding gate, chosen candidate, every gate result."""
    return {
        "outcome": record.get("outcome"),
        "binding_gate": record.get("binding_gate"),
        "chosen": next((c["candidate_id"] for c in record.get("candidates") or [] if c.get("chosen")), None),
        "gates": [
            (g.get("gate"), g.get("candidate_id"), g.get("result"),
             _r(g.get("value")), _r(g.get("margin")))
            for g in sorted(record.get("gates") or [],
                            key=lambda x: (x.get("gate") or "", x.get("candidate_id") or ""))
        ],
    }


def _r(v: Any) -> Any:
    if isinstance(v, float):
        return round(v, 6)
    return v
