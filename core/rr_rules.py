"""Deterministic construction for the in-force standard risk reversal.

Structure (one expiry, 1 combo): SELL listed ~25-delta put, BUY listed ~25-delta
call. Same expiry, 30-45 DTE, 1 lot. No protective put, no defined max loss,
no $20 wing, no net-debit cap.

Pure functions of (snapshot, rules, position). No I/O.
Closes are not evaluated here — product close is manual flatten.
"""

from __future__ import annotations

from typing import Any

from core.signals import dte, snapshot_date, usable
from schemas.cycle import ComboIntent, ComboLeg, MarketSnapshot, OptionRow
from schemas.strategy import DeterministicRules


def spread_pct(row: OptionRow) -> float | None:
    mid = row.mid
    if mid is None or mid <= 0 or row.bid is None or row.ask is None:
        return None
    return (row.ask - row.bid) / mid * 100.0


def liquidity_problem(row: OptionRow, rules: DeterministicRules) -> str | None:
    s = rules.structure
    pct = spread_pct(row)
    if pct is None:
        return f"{row.occ}: no bid/ask"
    if pct > s.max_spread_pct_of_mid:
        return f"{row.occ}: spread {pct:.1f}% > {s.max_spread_pct_of_mid}% of mid"
    if row.open_interest is None:
        return f"{row.occ}: open interest unavailable"
    if row.open_interest < s.min_open_interest:
        return f"{row.occ}: OI {row.open_interest:.0f} < {s.min_open_interest}"
    return None


def _leg(row: OptionRow, action: str) -> ComboLeg:
    return ComboLeg(
        occ=row.occ, con_id=row.con_id, right=row.right, strike=row.strike, expiry=row.expiry,
        action=action, bid=row.bid, ask=row.ask, delta=row.delta,
    )


def _expiry_rows(snapshot: MarketSnapshot, rules: DeterministicRules) -> tuple[list[OptionRow], int] | tuple[None, list[str]]:
    s = rules.structure
    if snapshot.expiry is None:
        return None, ["no expiry in DTE window"]
    days = dte(snapshot.expiry, snapshot_date(snapshot))
    if not (s.dte_min <= days <= s.dte_max):
        return None, [f"expiry {snapshot.expiry} DTE {days} outside [{s.dte_min},{s.dte_max}]"]
    rows = [r for r in snapshot.options if r.expiry == snapshot.expiry and usable(r)]
    return rows, days


def pick_25d_put(rows: list[OptionRow], rules: DeterministicRules) -> tuple[OptionRow | None, list[str]]:
    s = rules.structure
    puts = [r for r in rows if r.right == "P"]
    shorts = [p for p in puts if s.short_put_delta_min <= abs(p.delta) <= s.short_put_delta_max]
    shorts_ok = [p for p in shorts if liquidity_problem(p, rules) is None]
    if not shorts_ok:
        why = [liquidity_problem(p, rules) for p in shorts if liquidity_problem(p, rules)]
        return None, (
            [f"no liquid short put with |delta| in [{s.short_put_delta_min},{s.short_put_delta_max}]"]
            + why[:3]
        )
    short_put = min(shorts_ok, key=lambda p: (abs(abs(p.delta) - s.short_put_delta_target), -p.strike))
    return short_put, []


def pick_25d_call(rows: list[OptionRow], rules: DeterministicRules) -> tuple[OptionRow | None, list[str]]:
    s = rules.structure
    calls = [r for r in rows if r.right == "C"]
    cands = [
        c for c in calls
        if s.long_call_delta_min <= c.delta <= s.long_call_delta_max and liquidity_problem(c, rules) is None
    ]
    if not cands:
        return None, [f"no liquid call with delta in [{s.long_call_delta_min},{s.long_call_delta_max}]"]
    call = min(cands, key=lambda c: (abs(c.delta - s.long_call_delta_target), c.strike))
    return call, []


def build_entry(
    snapshot: MarketSnapshot,
    rules: DeterministicRules,
    *,
    strategy_name: str,
    idempotency_key: str,
) -> tuple[ComboIntent | None, list[str]]:
    """Return (intent, reasons). intent is None => abstain with reasons.

    2-leg standard RR: SELL 25d put + BUY 25d call, 1 lot, same expiry.
    """
    got = _expiry_rows(snapshot, rules)
    if got[0] is None:
        return None, got[1]  # type: ignore[return-value]
    rows, days = got  # type: ignore[misc]
    short_put, why = pick_25d_put(rows, rules)
    if short_put is None:
        return None, why
    call, why = pick_25d_call(rows, rules)
    if call is None:
        return None, why

    net = round(call.mid - short_put.mid, 2)
    qty = rules.sizing.contracts
    intent = ComboIntent(
        strategy=strategy_name,
        underlying=snapshot.underlying,
        purpose="open",
        legs=[_leg(short_put, "SELL"), _leg(call, "BUY")],
        quantity=qty,
        action="BUY",
        limit_price=net,
        max_loss_usd=None,
        idempotency_key=idempotency_key,
    )
    reasons = [
        f"enter: SELL {short_put.occ} (d={short_put.delta:.3f}) BUY {call.occ}"
        f" (d={call.delta:.3f}) net {net:+.2f}/sh, DTE {days}"
    ]
    return intent, reasons


def combo_mark(position: dict[str, Any], marks: dict[str, float]) -> float | None:
    """Per-share value of the combo as held (what SELLing it back would bring at mid)."""
    total = 0.0
    for leg in position["legs"]:
        mid = marks.get(leg["occ"])
        if mid is None:
            return None
        total += mid if leg["action"] == "BUY" else -mid
    return round(total, 4)


def evaluate_exit(
    position: dict[str, Any],
    snapshot: MarketSnapshot,
    rules: DeterministicRules,
) -> tuple[str | None, float | None, list[str]]:
    """Return (trigger, mark, reasons). trigger None => hold.

    In-force: no automated exits. Cycle uses flatten for product close.
    """
    del rules
    mark = combo_mark(position, snapshot.held_marks)
    expiry = (position.get("legs") or [{}])[0].get("expiry")
    days = None if not expiry else dte(expiry, snapshot_date(snapshot))
    dte_bit = f"DTE {days}" if days is not None else "DTE n/a"
    pnl = None if mark is None else (mark - position["entry_price"]) * 100.0 * position["quantity"]
    pnl_bit = "marks unavailable" if pnl is None else f"unrealized ${pnl:.0f}"
    return None, mark, [f"hold: no automated exits ({dte_bit}, {pnl_bit}); close is manual flatten"]


def build_exit(
    position: dict[str, Any], mark: float | None, rules: DeterministicRules, *,
    strategy_name: str, idempotency_key: str,
) -> ComboIntent | None:
    if mark is None:
        return None
    underlying = position.get("underlying") or rules.underlying or ""
    if not underlying:
        legs = position.get("legs") or []
        if legs:
            occ = str(legs[0].get("occ") or "")
            underlying = occ[:-15] if len(occ) > 15 else occ
    return ComboIntent(
        strategy=strategy_name,
        underlying=underlying,
        purpose="close",
        legs=[ComboLeg(**leg) for leg in position["legs"]],
        quantity=position["quantity"],
        action="SELL",
        limit_price=round(mark, 2),
        position_id=position["position_id"],
        idempotency_key=idempotency_key,
    )
