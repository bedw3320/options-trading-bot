"""Thin deterministic entry signals for the defined-risk risk reversal.

Inputs: one MarketSnapshot (+ own rr25 history). No I/O, no clock reads.
Convention: rr25 = IV(25d call) - IV(25d put); equities are usually negative.
25-delta IVs (rr25, put/call IV ratio) are linearly interpolated in |delta|
between the strikes that bracket 0.25; nearest listed strike if not bracketable.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime

from schemas.cycle import MarketSnapshot, OptionRow, SignalValue
from schemas.strategy import DeterministicRules
from utils.time_et import ET


def snapshot_date(snapshot: MarketSnapshot) -> date:
    return datetime.fromisoformat(snapshot.as_of).astimezone(ET).date()


def dte(expiry: str, today: date) -> int:
    exp = date(int(expiry[:4]), int(expiry[4:6]), int(expiry[6:8]))
    return (exp - today).days


def usable(row: OptionRow) -> bool:
    return row.delta is not None and row.iv is not None and row.iv > 0 and row.mid is not None


def nearest_delta(rows: list[OptionRow], right: str, abs_delta: float) -> OptionRow | None:
    cands = [r for r in rows if r.right == right and usable(r)]
    if not cands:
        return None
    return min(cands, key=lambda r: (abs(abs(r.delta) - abs_delta), r.strike))


@dataclass
class DeltaIV:
    """IV at a target |delta|, plus the listed strikes/weights used to get it."""

    iv: float
    method: str  # interpolated | exact | nearest
    rows: tuple[OptionRow, ...]
    weights: tuple[float, ...]

    def describe(self) -> str:
        parts = [
            f"{r.occ} d={r.delta:.4f} iv={r.iv:.4f} w={w:.3f}"
            for r, w in zip(self.rows, self.weights)
        ]
        return f"{self.method} iv={self.iv:.4f} ({'; '.join(parts)})"


def iv_at_abs_delta(rows: list[OptionRow], right: str, abs_delta: float) -> DeltaIV | None:
    """IV at |delta| = abs_delta: linear in |delta| on the bracketing strikes.

    Bracket = closest usable strike with |delta| <= target and closest with
    |delta| >= target. If either side is missing, fall back to nearest_delta.
    """
    cands = [r for r in rows if r.right == right and usable(r)]
    if not cands:
        return None
    below = [r for r in cands if abs(r.delta) <= abs_delta]
    above = [r for r in cands if abs(r.delta) >= abs_delta]
    if below and above:
        lo = min(below, key=lambda r: (abs_delta - abs(r.delta), r.strike))
        hi = min(above, key=lambda r: (abs(r.delta) - abs_delta, r.strike))
        span = abs(hi.delta) - abs(lo.delta)
        if span <= 1e-15:
            return DeltaIV(iv=lo.iv, method="exact", rows=(lo,), weights=(1.0,))
        w_hi = (abs_delta - abs(lo.delta)) / span
        iv = lo.iv * (1.0 - w_hi) + hi.iv * w_hi
        return DeltaIV(iv=iv, method="interpolated", rows=(lo, hi), weights=(1.0 - w_hi, w_hi))
    near = nearest_delta(cands, right, abs_delta)
    if near is None:
        return None
    return DeltaIV(iv=near.iv, method="nearest", rows=(near,), weights=(1.0,))


def realized_vol(closes: list[float], lookback: int) -> float | None:
    """Annualized close-to-close stdev of log returns over the last `lookback` returns."""
    if len(closes) < lookback + 1:
        return None
    window = closes[-(lookback + 1):]
    if any(c <= 0 for c in window):
        return None
    rets = [math.log(b / a) for a, b in zip(window, window[1:])]
    mean = sum(rets) / len(rets)
    var = sum((r - mean) ** 2 for r in rets) / (len(rets) - 1)
    return math.sqrt(var) * math.sqrt(252.0)


def skew_percentile(current: float, history: list[float]) -> float:
    """Percent of history with skew no richer than now (more negative rr25 = richer)."""
    if not history:
        return float("nan")
    richer_or_equal = sum(1 for h in history if h >= current)
    return 100.0 * richer_or_equal / len(history)


def compute_signals(
    snapshot: MarketSnapshot,
    rules: DeterministicRules,
    *,
    rr25_history: list[float] | None = None,
) -> list[SignalValue]:
    sig = rules.signals
    rows = [r for r in snapshot.options if r.expiry == snapshot.expiry]
    out: list[SignalValue] = []

    put25 = iv_at_abs_delta(rows, "P", sig.target_abs_delta)
    call25 = iv_at_abs_delta(rows, "C", sig.target_abs_delta)
    rr25: float | None = None
    if put25 and call25:
        rr25 = call25.iv - put25.iv
        out.append(SignalValue(
            name="rr25", value=round(rr25, 6), threshold=sig.max_rr25, passed=rr25 <= sig.max_rr25,
            note=f"call {call25.describe()}; put {put25.describe()}",
        ))
        ratio = put25.iv / call25.iv
        out.append(SignalValue(
            name="put_call_iv_ratio", value=round(ratio, 6), threshold=sig.min_put_call_iv_ratio,
            passed=ratio >= sig.min_put_call_iv_ratio,
            note=f"put_iv={put25.iv:.6f} / call_iv={call25.iv:.6f}",
        ))
    else:
        out.append(SignalValue(name="rr25", value=None, threshold=sig.max_rr25, passed=False,
                               note="no usable 25d call/put (delta/iv/bid-ask missing)"))
        out.append(SignalValue(name="put_call_iv_ratio", value=None,
                               threshold=sig.min_put_call_iv_ratio, passed=False, note="no 25d legs"))

    atm_c = nearest_delta(rows, "C", 0.5)
    atm_p = nearest_delta(rows, "P", 0.5)
    rv = realized_vol(snapshot.daily_closes, sig.rv_lookback_days)
    atm_iv = (atm_c.iv + atm_p.iv) / 2.0 if atm_c and atm_p else None
    if atm_iv is not None and rv is not None:
        out.append(SignalValue(
            name="atm_iv_minus_rv", value=round(atm_iv - rv, 6), threshold=0.0,
            passed=(atm_iv > rv) if sig.require_iv_over_rv else True, required=sig.require_iv_over_rv,
            note=f"atm_iv={atm_iv:.4f} rv{sig.rv_lookback_days}={rv:.4f}",
        ))
    else:
        out.append(SignalValue(
            name="atm_iv_minus_rv", value=None, threshold=0.0,
            passed=False if sig.require_iv_over_rv else None, required=sig.require_iv_over_rv,
            note="missing ATM IV or not enough daily closes",
        ))

    hist = rr25_history or []
    if rr25 is not None and len(hist) >= sig.skew_percentile_min_history:
        pct = skew_percentile(rr25, hist)
        out.append(SignalValue(
            name="rr25_percentile", value=round(pct, 2), threshold=sig.skew_percentile_min,
            passed=pct >= sig.skew_percentile_min, required=sig.skew_percentile_required,
            note=f"n={len(hist)} days",
        ))
    else:
        out.append(SignalValue(
            name="rr25_percentile", value=None, threshold=sig.skew_percentile_min,
            passed=False if sig.skew_percentile_required else None,
            required=sig.skew_percentile_required,
            note=f"insufficient history n={len(hist)} < {sig.skew_percentile_min_history}",
        ))

    today = snapshot_date(snapshot)
    blocking = [
        d for d in rules.events.dates
        if 0 <= (date.fromisoformat(d) - today).days <= rules.events.block_days_before
    ]
    out.append(SignalValue(
        name="event_blackout", value=float(len(blocking)), threshold=0.0, passed=not blocking,
        note=("blocked by " + ",".join(blocking)) if blocking else None,
    ))
    return out


def failing_required(signals: list[SignalValue]) -> list[SignalValue]:
    return [s for s in signals if s.required and s.passed is not True]
