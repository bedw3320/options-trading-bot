"""Pure liquidity screen: pick 25-delta put/call + wings, pass/fail vs thresholds.

No IB, no clock I/O except the `now` argument. Golden-fixture tests call this.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Iterable

from research.config import ScreenThresholds
from research.models import LegReport, LegRole, QuotedChain, QuotedLeg, TickerScreen
from utils.time_et import ET

ROLES: tuple[LegRole, ...] = ("put_25d", "call_25d", "put_wing", "call_wing")


def _dte(expiry: str, today: date) -> int:
    exp = date(int(expiry[:4]), int(expiry[4:6]), int(expiry[6:8]))
    return (exp - today).days


def _today(as_of: datetime) -> date:
    if as_of.tzinfo is None:
        as_of = as_of.replace(tzinfo=timezone.utc)
    return as_of.astimezone(ET).date()


def pick_expiry(
    legs: Iterable[QuotedLeg],
    *,
    today: date,
    dte_min: int,
    dte_max: int,
    dte_target: int,
) -> str | None:
    expiries = sorted({leg.expiry for leg in legs})
    in_window: list[tuple[int, str]] = []
    for exp in expiries:
        if len(exp) != 8 or not exp.isdigit():
            continue
        days = _dte(exp, today)
        if dte_min <= days <= dte_max:
            in_window.append((days, exp))
    if not in_window:
        return None
    in_window.sort(key=lambda t: (abs(t[0] - dte_target), t[1]))
    return in_window[0][1]


def nearest_abs_delta(
    legs: Iterable[QuotedLeg], right: str, target: float
) -> QuotedLeg | None:
    cands = [l for l in legs if l.right == right and l.delta is not None]
    if not cands:
        return None
    return min(cands, key=lambda l: (abs(abs(l.delta) - target), l.strike))


def put_wing(legs: Iterable[QuotedLeg], short_put_strike: float, wing_width: float) -> QuotedLeg | None:
    target = short_put_strike - wing_width
    puts = [l for l in legs if l.right == "P" and l.strike <= target + 1e-9]
    if not puts:
        return None
    return max(puts, key=lambda l: l.strike)


def call_wing(legs: Iterable[QuotedLeg], short_call_strike: float, wing_width: float) -> QuotedLeg | None:
    target = short_call_strike + wing_width
    calls = [l for l in legs if l.right == "C" and l.strike >= target - 1e-9]
    if not calls:
        return None
    return min(calls, key=lambda l: l.strike)


def quote_age_seconds(leg: QuotedLeg, now: datetime) -> float | None:
    if leg.quote_time is None:
        return None
    qt = leg.quote_time
    if qt.tzinfo is None:
        qt = qt.replace(tzinfo=timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    return (now - qt.astimezone(now.tzinfo)).total_seconds()


def spread_abs(leg: QuotedLeg) -> float | None:
    if leg.bid is None or leg.ask is None:
        return None
    return float(leg.ask) - float(leg.bid)


def spread_pct(leg: QuotedLeg) -> float | None:
    mid = leg.mid
    sp = spread_abs(leg)
    if mid is None or mid <= 0 or sp is None:
        return None
    return sp / mid * 100.0


def _missing(role: LegRole, reason: str) -> LegReport:
    return LegReport(role=role, found=False, passed=False, reasons=[reason])


def evaluate_leg(
    role: LegRole,
    leg: QuotedLeg | None,
    thresholds: ScreenThresholds,
    *,
    now: datetime,
    missing_reason: str,
) -> LegReport:
    if leg is None:
        return _missing(role, missing_reason)
    reasons: list[str] = []
    sp = spread_abs(leg)
    pct = spread_pct(leg)
    age = quote_age_seconds(leg, now)
    if leg.bid is not None and leg.ask is not None and leg.bid > leg.ask:
        reasons.append("crossed_quote")
    if pct is None:
        reasons.append("no_bid_ask")
    elif pct > thresholds.max_spread_pct_of_mid:
        reasons.append(
            f"spread {pct:.1f}% > {thresholds.max_spread_pct_of_mid}% of mid"
        )
    if leg.open_interest is None:
        reasons.append("open_interest_unavailable")
    elif leg.open_interest < thresholds.min_open_interest:
        reasons.append(
            f"OI {leg.open_interest:.0f} < {thresholds.min_open_interest}"
        )
    if age is None:
        reasons.append("quote_time_unavailable")
    elif age > thresholds.max_quote_age_seconds:
        reasons.append(f"stale_quote age={age:.0f}s > {thresholds.max_quote_age_seconds:.0f}s")
    if role in ("put_25d", "call_25d") and leg.delta is None:
        reasons.append("missing_greeks")
    return LegReport(
        role=role,
        found=True,
        occ=leg.occ,
        expiry=leg.expiry,
        strike=leg.strike,
        right=leg.right,
        delta=leg.delta,
        iv=leg.iv,
        bid=leg.bid,
        ask=leg.ask,
        mid=leg.mid,
        spread_abs=sp,
        spread_pct=round(pct, 4) if pct is not None else None,
        open_interest=leg.open_interest,
        volume=leg.volume,
        quote_age_seconds=round(age, 3) if age is not None else None,
        quote_time=leg.quote_time,
        data_source=leg.data_source,
        market_data_type=leg.market_data_type,
        passed=not reasons,
        reasons=reasons,
    )


def screen_chain(chain: QuotedChain, thresholds: ScreenThresholds) -> TickerScreen:
    now = chain.as_of
    today = _today(now)
    reasons: list[str] = []
    diagnostic = bool(chain.diagnostic_only)
    if chain.skip_reason:
        reasons.append(chain.skip_reason)
        diagnostic = True
    expiry = pick_expiry(
        chain.legs,
        today=today,
        dte_min=thresholds.dte_min,
        dte_max=thresholds.dte_max,
        dte_target=thresholds.dte_target,
    )
    dte = _dte(expiry, today) if expiry else None
    window = [l for l in chain.legs if l.expiry == expiry] if expiry else []
    put25 = nearest_abs_delta(window, "P", thresholds.target_abs_delta)
    call25 = nearest_abs_delta(window, "C", thresholds.target_abs_delta)
    p_wing = put_wing(window, put25.strike, thresholds.wing_width) if put25 else None
    c_wing = call_wing(window, call25.strike, thresholds.wing_width) if call25 else None

    reports = [
        evaluate_leg(
            "put_25d", put25, thresholds, now=now,
            missing_reason="missing_greeks" if expiry else "no_expiry_in_dte_window",
        ),
        evaluate_leg(
            "call_25d", call25, thresholds, now=now,
            missing_reason="missing_greeks" if expiry else "no_expiry_in_dte_window",
        ),
        evaluate_leg(
            "put_wing", p_wing, thresholds, now=now,
            missing_reason="missing_wing_strike" if put25 else "missing_greeks",
        ),
        evaluate_leg(
            "call_wing", c_wing, thresholds, now=now,
            missing_reason="missing_wing_strike" if call25 else "missing_greeks",
        ),
    ]
    for r in reports:
        reasons.extend(f"{r.role}: {x}" for x in r.reasons)
        if not r.found:
            reasons.append(f"{r.role}: {r.reasons[0] if r.reasons else 'missing'}")

    if not expiry:
        result: str = "fail"
        if diagnostic:
            result = "diagnostic_only"
        return TickerScreen(
            ticker=chain.ticker, as_of=now, expiry=None, dte=None,
            underlying_price=chain.underlying_price, data_source=chain.data_source,
            diagnostic_only=diagnostic, result=result, legs=reports,  # type: ignore[arg-type]
            reasons=reasons or ["no_expiry_in_dte_window"],
            thresholds=thresholds.as_dict(),
        )

    legs_ok = all(r.found and r.passed for r in reports)
    if diagnostic:
        result = "diagnostic_only"
    elif legs_ok:
        result = "pass"
    else:
        result = "fail"
    return TickerScreen(
        ticker=chain.ticker,
        as_of=now,
        expiry=expiry,
        dte=dte,
        underlying_price=chain.underlying_price,
        data_source=chain.data_source,
        diagnostic_only=diagnostic,
        result=result,  # type: ignore[arg-type]
        legs=reports,
        reasons=reasons,
        thresholds=thresholds.as_dict(),
    )
