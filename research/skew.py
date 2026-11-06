"""Derive rr25 / 25d put-call IV from a quoted chain. No IB."""

from __future__ import annotations

from datetime import date

from core.signals import iv_at_abs_delta
from research.models import QuotedChain, QuotedLeg
from schemas.cycle import OptionRow
from schemas.watchlist import DELTA_CONVENTION

SKEW_TARGETS = (30, 45)


def _dte(expiry: str, today: date) -> int:
    exp = date(int(expiry[:4]), int(expiry[4:6]), int(expiry[6:8]))
    return (exp - today).days


def to_option_row(leg: QuotedLeg) -> OptionRow:
    return OptionRow(
        occ=leg.occ,
        expiry=leg.expiry,
        right=leg.right,
        strike=leg.strike,
        bid=leg.bid,
        ask=leg.ask,
        delta=leg.delta,
        iv=leg.iv,
        open_interest=leg.open_interest,
        status=leg.status,
    )


def pick_expiries_near(
    chain: QuotedChain,
    *,
    today: date,
    targets: tuple[int, ...] = SKEW_TARGETS,
    dte_min: int = 25,
    dte_max: int = 50,
) -> list[tuple[int, str, int]]:
    """Return (target_dte, expiry, actual_dte) unique expiries nearest each target."""
    by_exp: dict[str, int] = {}
    for leg in chain.legs:
        if len(leg.expiry) != 8 or not leg.expiry.isdigit():
            continue
        days = _dte(leg.expiry, today)
        if dte_min <= days <= dte_max:
            by_exp[leg.expiry] = days
    available = sorted(by_exp.items(), key=lambda kv: kv[0])
    picked: list[tuple[int, str, int]] = []
    used: set[str] = set()
    for target in targets:
        cands = [(exp, dte) for exp, dte in available if exp not in used]
        if not cands:
            continue
        exp, dte = min(cands, key=lambda t: (abs(t[1] - target), t[0]))
        picked.append((target, exp, dte))
        used.add(exp)
    return picked


def rr25_for_expiry(
    chain: QuotedChain, expiry: str, *, target_abs_delta: float = 0.25
) -> dict[str, float | str | None]:
    rows = [to_option_row(l) for l in chain.legs if l.expiry == expiry]
    put = iv_at_abs_delta(rows, "P", target_abs_delta)
    call = iv_at_abs_delta(rows, "C", target_abs_delta)
    rr25 = None if put is None or call is None else call.iv - put.iv
    return {
        "rr25": None if rr25 is None else round(rr25, 6),
        "put_iv_25d": None if put is None else round(put.iv, 6),
        "call_iv_25d": None if call is None else round(call.iv, 6),
        "put_note": None if put is None else put.describe(),
        "call_note": None if call is None else call.describe(),
        "delta_convention": DELTA_CONVENTION,
    }


def strike_payload(chain: QuotedChain, expiry: str) -> list[dict]:
    out = []
    for l in sorted((x for x in chain.legs if x.expiry == expiry), key=lambda z: (z.right, z.strike)):
        out.append(
            {
                "occ": l.occ,
                "right": l.right,
                "strike": l.strike,
                "delta": l.delta,
                "iv": l.iv,
                "bid": l.bid,
                "ask": l.ask,
                "open_interest": l.open_interest,
                "volume": l.volume,
                "data_source": l.data_source,
                "market_data_type": l.market_data_type,
            }
        )
    return out
