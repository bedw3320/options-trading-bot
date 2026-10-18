"""Deterministic construction and exit rules for the defined-risk risk reversal.

Structure (one expiry, 1 combo): SELL ~22d put, BUY wing put `wing_width` lower,
BUY call sized so the combo is ~zero-cost. Max loss = (width + net debit) x 100.
Pure functions of (snapshot, rules, position). No I/O.
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


def build_entry(
    snapshot: MarketSnapshot,
    rules: DeterministicRules,
    *,
    strategy_name: str,
    idempotency_key: str,
) -> tuple[ComboIntent | None, list[str]]:
    """Return (intent, reasons). intent is None => abstain with reasons."""
    s = rules.structure
    reasons: list[str] = []
    if snapshot.expiry is None:
        return None, ["no expiry in DTE window"]
    days = dte(snapshot.expiry, snapshot_date(snapshot))
    if not (s.dte_min <= days <= s.dte_max):
        return None, [f"expiry {snapshot.expiry} DTE {days} outside [{s.dte_min},{s.dte_max}]"]

    rows = [r for r in snapshot.options if r.expiry == snapshot.expiry and usable(r)]
    puts = [r for r in rows if r.right == "P"]
    calls = [r for r in rows if r.right == "C"]

    shorts = [p for p in puts if s.short_put_delta_min <= abs(p.delta) <= s.short_put_delta_max]
    shorts_ok = [p for p in shorts if liquidity_problem(p, rules) is None]
    if not shorts_ok:
        why = [liquidity_problem(p, rules) for p in shorts if liquidity_problem(p, rules)]
        return None, [f"no liquid short put with |delta| in [{s.short_put_delta_min},{s.short_put_delta_max}]"] + why[:3]
    short_put = min(shorts_ok, key=lambda p: (abs(abs(p.delta) - s.short_put_delta_target), -p.strike))

    wing_target = short_put.strike - s.wing_width
    wings = sorted((p for p in puts if p.strike <= wing_target + 1e-9), key=lambda p: -p.strike)
    if not wings:
        return None, [f"no wing put at or below {wing_target}"]
    wing = wings[0]
    if (problem := liquidity_problem(wing, rules)):
        return None, [f"wing put illiquid: {problem}"]

    credit = short_put.mid - wing.mid
    call_cands = [
        c for c in calls
        if s.long_call_delta_min <= c.delta <= s.long_call_delta_max and liquidity_problem(c, rules) is None
    ]
    if not call_cands:
        return None, [f"no liquid call with delta in [{s.long_call_delta_min},{s.long_call_delta_max}]"]
    affordable = [c for c in call_cands if c.mid - credit <= s.max_net_debit + 1e-9]
    if not affordable:
        cheapest = min(call_cands, key=lambda c: c.mid)
        return None, [f"zero-cost not reachable: cheapest call {cheapest.occ} mid {cheapest.mid:.2f}"
                      f" vs put-spread credit {credit:.2f} (max debit {s.max_net_debit})"]
    call = min(affordable, key=lambda c: (abs(c.mid - credit), c.strike))

    net_debit = round(call.mid + wing.mid - short_put.mid, 2)
    width = short_put.strike - wing.strike
    qty = rules.sizing.contracts
    max_loss = round((width + net_debit) * 100.0 * qty, 2)
    if max_loss > rules.sizing.max_loss_usd:
        return None, [f"max loss ${max_loss:.0f} > cap ${rules.sizing.max_loss_usd:.0f}"]

    intent = ComboIntent(
        strategy=strategy_name,
        underlying=rules.underlying,
        purpose="open",
        legs=[_leg(short_put, "SELL"), _leg(wing, "BUY"), _leg(call, "BUY")],
        quantity=qty,
        action="BUY",
        limit_price=net_debit,
        max_loss_usd=max_loss,
        idempotency_key=idempotency_key,
    )
    reasons.append(
        f"enter: SELL {short_put.occ} (d={short_put.delta:.3f}) BUY {wing.occ} BUY {call.occ}"
        f" (d={call.delta:.3f}) net {net_debit:+.2f}/sh, max loss ${max_loss:.0f}, DTE {days}"
    )
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
    """Return (trigger, mark, reasons). trigger None => hold."""
    ex = rules.exits
    legs = position["legs"]
    expiry = legs[0]["expiry"]
    days = dte(expiry, snapshot_date(snapshot))
    short_put = next(l for l in legs if l["action"] == "SELL" and l["right"] == "P")
    stop_level = short_put["strike"] * (1 - ex.underlying_stop_pct_below_short_put / 100.0)
    mark = combo_mark(position, snapshot.held_marks)
    pnl = None if mark is None else (mark - position["entry_price"]) * 100.0 * position["quantity"]

    if days <= ex.time_stop_dte:
        return "time_stop", mark, [f"DTE {days} <= {ex.time_stop_dte}"]
    if snapshot.underlying_price is not None and snapshot.underlying_price <= stop_level:
        return "underlying_stop", mark, [
            f"{rules.underlying} {snapshot.underlying_price:.2f} <= {stop_level:.2f}"
            f" (short put {short_put['strike']} - {ex.underlying_stop_pct_below_short_put}%)"]
    if pnl is None:
        return None, None, ["hold: leg marks unavailable, P&L exits not evaluable"]
    if pnl <= -ex.stop_loss_usd:
        return "stop_loss", mark, [f"unrealized ${pnl:.0f} <= -${ex.stop_loss_usd:.0f}"]
    if pnl >= ex.take_profit_usd:
        return "take_profit", mark, [f"unrealized ${pnl:.0f} >= ${ex.take_profit_usd:.0f}"]
    return None, mark, [f"hold: DTE {days}, unrealized ${pnl:.0f}, stop level {stop_level:.2f}"]


def build_exit(
    position: dict[str, Any], mark: float | None, rules: DeterministicRules, *,
    strategy_name: str, idempotency_key: str,
) -> ComboIntent | None:
    if mark is None:
        return None
    return ComboIntent(
        strategy=strategy_name,
        underlying=rules.underlying,
        purpose="close",
        legs=[ComboLeg(**leg) for leg in position["legs"]],
        quantity=position["quantity"],
        action="SELL",
        limit_price=round(mark, 2),
        position_id=position["position_id"],
        idempotency_key=idempotency_key,
    )
