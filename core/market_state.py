"""Market-state interface: IB implementation + fixture implementation.

Contract: `snapshot()` never raises for data problems. IB failures (10197 competing
live session, 162 historical conflict, not subscribed, timeouts, exceptions) come
back as status="unavailable" with a reason; the cycle then abstains.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Protocol

from schemas.cycle import MarketSnapshot, OptionRow
from schemas.strategy import DeterministicRules
from utils.logging import get_logger
from utils.time_et import ET

log = get_logger(__name__)

# Quote statuses from integrations/ibkr/option_quotes.py that mean "no data at all".
FATAL_QUOTE_STATUSES = {
    "competing_live_session": "ib_10197_competing_live_session",
    "historical_session_conflict": "ib_162_session_connected_from_different_ip",
    "not_subscribed": "ib_market_data_not_subscribed",
}
QUOTE_BATCH = 40


class MarketStateProvider(Protocol):
    def snapshot(self, rules: DeterministicRules, *, held_legs: list[dict[str, Any]]) -> MarketSnapshot: ...


def unavailable(underlying: str, source: str, reason: str, errors: list[dict] | None = None,
                as_of: str | None = None) -> MarketSnapshot:
    return MarketSnapshot(
        as_of=as_of or datetime.now(timezone.utc).isoformat(timespec="seconds"),
        source=source, underlying=underlying, status="unavailable", reason=reason, errors=errors or [],
    )


class FixtureMarketState:
    """Reads a recorded/synthetic snapshot JSON (schemas.cycle.MarketSnapshot)."""

    def __init__(self, path: str | Path, *, overrides: dict[str, Any] | None = None) -> None:
        self.path = Path(path)
        self.overrides = overrides or {}

    def snapshot(self, rules: DeterministicRules, *, held_legs: list[dict[str, Any]]) -> MarketSnapshot:
        try:
            raw = json.loads(self.path.read_text())
            raw.update(self.overrides)
            raw["source"] = f"fixture:{self.path.name}"
            snap = MarketSnapshot.model_validate(raw)
        except Exception as exc:  # fixture errors are data errors too
            return unavailable(rules.underlying, f"fixture:{self.path.name}", f"fixture_error: {exc}")
        if snap.status == "ok" and held_legs and not snap.held_marks:
            by_occ = {o.occ: o.mid for o in snap.options if o.mid is not None}
            snap.held_marks = {l["occ"]: by_occ[l["occ"]] for l in held_legs if l["occ"] in by_occ}
        return snap


class IBMarketState:
    """Live IB snapshot: SPY quote, daily closes, one expiry's strike grid with model Greeks."""

    def __init__(self, ib: Any, *, quote_timeout: float = 12.0) -> None:
        self.ib = ib
        self.quote_timeout = quote_timeout

    def snapshot(self, rules: DeterministicRules, *, held_legs: list[dict[str, Any]]) -> MarketSnapshot:
        und = rules.underlying
        try:
            return self._snapshot(rules, held_legs)
        except Exception as exc:
            log.warning("IB snapshot failed: %s", exc)
            return unavailable(und, "ib", f"ib_exception: {type(exc).__name__}: {exc}")

    def _snapshot(self, rules: DeterministicRules, held_legs: list[dict[str, Any]]) -> MarketSnapshot:
        from ib_insync import Stock

        from integrations.ibkr.market_data import get_stock_bars
        from integrations.ibkr.occ import make_option
        from integrations.ibkr.option_quotes import request_quote, request_quotes
        from integrations.ibkr.options_data import get_option_contracts

        ib = self.ib
        und = rules.underlying
        s = rules.structure
        as_of = datetime.now(timezone.utc).isoformat(timespec="seconds")

        stock = Stock(und, "SMART", "USD")
        ib.qualifyContracts(stock)
        q = request_quote(ib, stock, timeout=self.quote_timeout, require_bid_ask=False)
        if q.status in FATAL_QUOTE_STATUSES:
            return unavailable(und, "ib", FATAL_QUOTE_STATUSES[q.status],
                               [e.model_dump() for e in q.errors], as_of)
        price = q.last or q.mid or q.close
        if price is None:
            return unavailable(und, "ib", f"no_underlying_price status={q.status}",
                               [e.model_dump() for e in q.errors], as_of)

        bars = get_stock_bars(ib, und, "1D", rules.signals.rv_lookback_days + 5)
        closes = [float(x) for x in bars["close"].tolist()] if not bars.empty else []
        if len(closes) < rules.signals.rv_lookback_days + 1:
            return unavailable(und, "ib", f"historical_bars_unavailable n={len(closes)}", [], as_of)

        today = datetime.now(ET).date()
        lo = price * 0.75
        hi = price * 1.12
        rows = get_option_contracts(
            ib, und,
            expiration_date_gte=str(today + timedelta(days=s.dte_min)),
            expiration_date_lte=str(today + timedelta(days=s.dte_max)),
            strike_price_gte=lo, strike_price_lte=hi,
            n_strikes=400, max_expiries=1, limit=2000, include_quotes=False,
            underlying_price=price, today=today,
        )
        if not rows:
            return unavailable(und, "ib", "no_option_contracts_in_window", [], as_of)
        target = today + timedelta(days=s.dte_target)
        expiries = sorted({r["expiration_date"].replace("-", "") for r in rows},
                          key=lambda e: abs((datetime.strptime(e, "%Y%m%d").date() - target).days))
        expiry = expiries[0]
        grid = [r for r in rows if r["expiration_date"].replace("-", "") == expiry
                and abs(float(r["strike_price"]) / s.strike_step - round(float(r["strike_price"]) / s.strike_step)) < 1e-9
                and ((r["type"] == "put" and float(r["strike_price"]) <= price)
                     or (r["type"] == "call" and float(r["strike_price"]) >= price))]

        contracts = [make_option(und, expiry, float(r["strike_price"]), r["type"], trading_class=r.get("trading_class"))
                     for r in grid]
        held_contracts = []
        for leg in held_legs:
            held_contracts.append(make_option(und, leg["expiry"], leg["strike"], leg["right"]))
        all_contracts = contracts + held_contracts
        if all_contracts:
            ib.qualifyContracts(*all_contracts)
        quotes = []
        for i in range(0, len(all_contracts), QUOTE_BATCH):
            quotes += request_quotes(ib, all_contracts[i:i + QUOTE_BATCH], timeout=self.quote_timeout,
                                     require_greeks=True)
        fatal = [qq for qq in quotes if qq.status in FATAL_QUOTE_STATUSES]
        if fatal:
            return unavailable(und, "ib", FATAL_QUOTE_STATUSES[fatal[0].status],
                               [e.model_dump() for e in fatal[0].errors], as_of)

        options: list[OptionRow] = []
        for c, qq in zip(contracts, quotes[: len(contracts)]):
            g = qq.model_greeks
            options.append(OptionRow(
                occ=qq.symbol, con_id=getattr(c, "conId", None) or None, expiry=expiry,
                right=c.right, strike=float(c.strike), bid=qq.bid, ask=qq.ask,
                delta=g.delta if g else None, iv=(g.implied_vol if g else None) or qq.implied_vol,
                open_interest=qq.open_interest, status=qq.status,
            ))
        held_marks = {qq.symbol: qq.mid for qq in quotes[len(contracts):] if qq.mid is not None}
        if not any(o.delta is not None and o.mid is not None for o in options):
            return unavailable(und, "ib", "no_option_greeks_or_bid_ask", [], as_of)
        return MarketSnapshot(
            as_of=as_of, source="ib", underlying=und, status="ok", underlying_price=float(price),
            daily_closes=closes, expiry=expiry, options=options, held_marks=held_marks,
        )
