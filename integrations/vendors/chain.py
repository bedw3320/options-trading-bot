"""Vendor-neutral chain -> MarketSnapshot assembly, so each adapter only maps its JSON.

An adapter supplies: underlying price, daily closes, a contract list (with OI) and
per-OCC quotes (bid/ask/delta/iv). This module picks the expiry and strike grid the
same way IBMarketState does and returns a schemas.cycle.MarketSnapshot.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from schemas.cycle import MarketSnapshot, OptionRow
from schemas.strategy import DeterministicRules


@dataclass
class Contract:
    occ: str          # SPY261120P00580000
    expiry: str       # YYYYMMDD
    right: str        # "C" | "P"
    strike: float
    open_interest: float | None = None


@dataclass
class Quote:
    bid: float | None = None
    ask: float | None = None
    delta: float | None = None
    iv: float | None = None
    gamma: float | None = None
    vega: float | None = None
    theta: float | None = None

    @property
    def mid(self) -> float | None:
        if self.bid is None or self.ask is None or self.bid <= 0 or self.ask <= 0:
            return None
        return (self.bid + self.ask) / 2.0


def occ_symbol(underlying: str, expiry: str, right: str, strike: float) -> str:
    return f"{underlying}{expiry[2:]}{right}{int(round(strike * 1000)):08d}"


def parse_occ(sym: str) -> tuple[str, str, str, float]:
    """'SPY261120P00580000' -> ('SPY', '20261120', 'P', 580.0)."""
    tail = sym[-15:]
    return sym[:-15], "20" + tail[:6], tail[6], int(tail[7:]) / 1000.0


def window(rules: DeterministicRules, price: float, today: date) -> dict:
    s = rules.structure
    return {
        "exp_gte": today + timedelta(days=s.dte_min), "exp_lte": today + timedelta(days=s.dte_max),
        "strike_gte": round(price * 0.75, 2), "strike_lte": round(price * 1.12, 2),
    }


def pick_expiry(contracts: list[Contract], rules: DeterministicRules, today: date) -> str | None:
    target = today + timedelta(days=rules.structure.dte_target)
    exps = sorted({c.expiry for c in contracts},
                  key=lambda e: abs((datetime.strptime(e, "%Y%m%d").date() - target).days))
    return exps[0] if exps else None


def grid(contracts: list[Contract], expiry: str, price: float, step: float) -> list[Contract]:
    def on(k: float) -> bool:
        return abs(k / step - round(k / step)) < 1e-9
    return sorted((c for c in contracts if c.expiry == expiry and on(c.strike)
                   and ((c.right == "P" and c.strike <= price) or (c.right == "C" and c.strike >= price))),
                  key=lambda c: (c.right, c.strike))


def assemble(*, rules: DeterministicRules, source: str, price: float, closes: list[float], expiry: str,
             chain: list[Contract], quotes: dict[str, Quote], held_quotes: dict[str, Quote] | None = None,
             as_of: str | None = None) -> MarketSnapshot:
    options = []
    for c in chain:
        q = quotes.get(c.occ)
        options.append(OptionRow(
            occ=c.occ, expiry=c.expiry, right=c.right, strike=c.strike,
            bid=q.bid if q else None, ask=q.ask if q else None,
            delta=q.delta if q else None, iv=q.iv if q else None,
            gamma=q.gamma if q else None, vega=q.vega if q else None, theta=q.theta if q else None,
            open_interest=c.open_interest, status="ok" if q else "no_quote",
        ))
    held = {k: v.mid for k, v in (held_quotes or {}).items() if v.mid is not None}
    return MarketSnapshot(
        as_of=as_of or datetime.now(timezone.utc).isoformat(timespec="seconds"), source=source,
        underlying=rules.underlying, status="ok", underlying_price=float(price), daily_closes=closes,
        expiry=expiry, options=options, held_marks=held,
    )
