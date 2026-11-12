"""Epic 4 close-out helpers: mark-to-market, persistable fills, debrief.

Pure functions. The cycle records results; GuardedBroker is still the only send path.
Never invents a fill: no exec_id means the record is dropped.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from core.rr_rules import combo_mark
from core.signals import dte, snapshot_date
from schemas.cycle import LegMark, MarketSnapshot, MarkToMarket, TradeDebrief
from schemas.strategy import DeterministicRules
from utils.time_et import format_time_et, format_time_utc


def mark_to_market(
    position: dict[str, Any],
    snapshot: MarketSnapshot,
    rules: DeterministicRules,
    *,
    daily_realized_pnl_usd: float = 0.0,
) -> MarkToMarket:
    """Per-leg mids + net P&L vs entry. Missing marks stay None (never guessed)."""
    legs = position.get("legs") or []
    expiry = legs[0]["expiry"] if legs else None
    days = None if expiry is None else dte(expiry, snapshot_date(snapshot))
    qty = int(position["quantity"])
    entry = float(position["entry_price"])
    marks = snapshot.held_marks
    row_marks: list[LegMark] = []
    for leg in legs:
        mid = marks.get(leg["occ"])
        sign = 1.0 if leg["action"] == "BUY" else -1.0
        signed = None if mid is None else round(sign * mid, 4)
        value = None if signed is None else round(signed * 100.0 * qty, 2)
        row_marks.append(
            LegMark(
                occ=leg["occ"], action=leg["action"], right=leg["right"],
                strike=leg["strike"], expiry=leg["expiry"], mark=mid,
                signed_mark=signed, signed_value_usd=value,
            )
        )
    net = combo_mark(position, marks)
    pnl = None if net is None else round((net - entry) * 100.0 * qty, 2)
    limit = rules.kill_switch.daily_loss_limit_usd
    from core.universe import position_underlying
    und = position.get("underlying") or position_underlying(position) or snapshot.underlying
    return MarkToMarket(
        position_id=position["position_id"],
        opened_cycle_id=position.get("opened_cycle_id"),
        underlying=und,
        underlying_price=snapshot.underlying_price,
        expiry=expiry,
        dte=days,
        quantity=qty,
        entry_price=entry,
        net_mark=net,
        unrealized_pnl_usd=pnl,
        legs=row_marks,
        daily_realized_pnl_usd=daily_realized_pnl_usd,
        daily_loss_limit_usd=limit,
        daily_loss_breach=bool(limit is not None and daily_realized_pnl_usd <= -limit),
    )


def persistable_fill(raw: dict[str, Any]) -> dict[str, Any] | None:
    """Broker execution → SQLite payload. None if there is no exec_id (not a fill)."""
    exec_id = raw.get("exec_id")
    if not exec_id:
        return None
    qty = raw.get("qty")
    if qty is None:
        qty = raw.get("shares")
    if raw.get("time_utc"):
        time_utc = format_time_utc(raw["time_utc"])
        time_et = format_time_et(raw["time_utc"])
    elif raw.get("time"):
        time_utc = format_time_utc(raw["time"])
        time_et = format_time_et(raw["time"])
    else:
        time_utc = None
        time_et = raw.get("time_et")
    out: dict[str, Any] = {
        "exec_id": str(exec_id),
        "price": raw.get("price"),
        "qty": qty,
        "time_utc": time_utc,
    }
    if time_et is not None:
        out["time_et"] = time_et
    for key in ("order_id", "symbol", "side", "exchange", "shares"):
        if raw.get(key) is not None:
            out[key] = raw[key]
    return out


def holding_period_seconds(opened_at: str, closed_at: str) -> int:
    start = datetime.fromisoformat(opened_at)
    end = datetime.fromisoformat(closed_at)
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    if end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)
    return max(0, int((end - start).total_seconds()))


def build_debrief(
    *,
    closed_cycle_id: str,
    position: dict[str, Any],
    entry_reason: str,
    exit_reason: str,
    exit_trigger: str | None,
) -> TradeDebrief:
    opened_at = position["opened_at"]
    closed_at = position["closed_at"]
    return TradeDebrief(
        cycle_id=closed_cycle_id,
        opened_cycle_id=position["opened_cycle_id"],
        position_id=position["position_id"],
        entry_reason=entry_reason,
        exit_reason=exit_reason,
        exit_trigger=exit_trigger,
        realized_pnl_usd=float(position["realized_pnl_usd"]),
        holding_period_seconds=holding_period_seconds(opened_at, closed_at),
        opened_at=opened_at,
        closed_at=closed_at,
    )
