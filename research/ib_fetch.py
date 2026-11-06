"""IB Gateway fetch for research screens/snapshots. Readonly, paper port only.

Imported only from live CLI paths so tests never connect.
"""

from __future__ import annotations

import os
from datetime import date, datetime, timedelta, timezone
from typing import Any

from research.config import ScreenThresholds
from research.models import QuotedChain, QuotedLeg
from utils.time_et import ET

QUOTE_BATCH = 40
LIVE_PORT_REFUSED = 4001


def refuse_live_port(port: int) -> None:
    if int(port) == LIVE_PORT_REFUSED:
        raise SystemExit("REFUSED: live Gateway port 4001; research jobs are paper-only (4002)")
    mode = os.environ.get("TRADING_MODE", "paper").strip().lower()
    if mode != "paper":
        raise SystemExit("REFUSED: TRADING_MODE is not paper; research jobs are paper-only")


def connect_paper_readonly(*, host: str, port: int, client_id: int):
    refuse_live_port(port)
    os.environ["IB_GATEWAY_HOST"] = str(host)
    os.environ["IB_GATEWAY_PORT"] = str(port)
    from integrations.ibkr.client import create_ib_client

    return create_ib_client("paper", client_id=client_id, readonly=True)


def _as_of() -> datetime:
    return datetime.now(timezone.utc)


def fetch_quoted_chain(
    ib: Any,
    ticker: str,
    thresholds: ScreenThresholds,
    *,
    today: date | None = None,
    quote_timeout: float = 12.0,
    n_strikes: int = 80,
) -> QuotedChain:
    """Quote a 30-45 DTE grid with model Greeks. Labels data_source from IB mdt."""
    from ib_insync import Stock

    from integrations.ibkr.occ import make_option
    from integrations.ibkr.option_quotes import (
        is_non_live_market_data,
        market_data_source_label,
        request_quote,
        request_quotes,
    )
    from integrations.ibkr.options_data import get_option_contracts

    day = today or datetime.now(ET).date()
    as_of = _as_of()
    stock = Stock(ticker, "SMART", "USD")
    ib.qualifyContracts(stock)
    uq = request_quote(ib, stock, timeout=quote_timeout, require_bid_ask=False)
    price = uq.last or uq.mid or uq.close
    mdt = uq.market_data_type
    source = market_data_source_label(mdt)
    diagnostic = is_non_live_market_data(mdt)
    skip_reason = None
    if diagnostic:
        skip_reason = f"non_live_market_data mdt={mdt} source={source}"
    if price is None:
        return QuotedChain(
            ticker=ticker, as_of=as_of, underlying_price=None, data_source=source,
            market_data_type=mdt, diagnostic_only=True,
            skip_reason=f"no_underlying_price status={uq.status}", legs=[],
        )

    rows = get_option_contracts(
        ib, ticker,
        expiration_date_gte=str(day + timedelta(days=thresholds.dte_min)),
        expiration_date_lte=str(day + timedelta(days=thresholds.dte_max)),
        n_strikes=n_strikes, max_expiries=2, limit=400, include_quotes=False,
        underlying_price=float(price), today=day,
    )
    if not rows:
        return QuotedChain(
            ticker=ticker, as_of=as_of, underlying_price=float(price),
            data_source=source, market_data_type=mdt, diagnostic_only=True,
            skip_reason="no_option_contracts_in_window", legs=[],
        )

    contracts = [
        make_option(
            ticker,
            r["expiration_date"].replace("-", ""),
            float(r["strike_price"]),
            r["type"],
            trading_class=r.get("trading_class"),
        )
        for r in rows
    ]
    if contracts:
        ib.qualifyContracts(*contracts)
    quotes = []
    for i in range(0, len(contracts), QUOTE_BATCH):
        quotes += request_quotes(
            ib, contracts[i:i + QUOTE_BATCH],
            timeout=quote_timeout, require_greeks=True,
        )
    if any(is_non_live_market_data(q.market_data_type) for q in quotes):
        diagnostic = True
        qmdt = next(q.market_data_type for q in quotes if is_non_live_market_data(q.market_data_type))
        source = market_data_source_label(qmdt)
        skip_reason = skip_reason or f"non_live_market_data mdt={qmdt} source={source}"
        mdt = qmdt

    legs: list[QuotedLeg] = []
    for c, q in zip(contracts, quotes):
        g = q.model_greeks
        exp = (c.lastTradeDateOrContractMonth or "").replace("-", "")
        right = (c.right or "").upper()
        if right not in ("C", "P"):
            continue
        legs.append(
            QuotedLeg(
                occ=q.symbol,
                expiry=exp,
                right=right,  # type: ignore[arg-type]
                strike=float(c.strike),
                bid=q.bid,
                ask=q.ask,
                delta=g.delta if g else None,
                iv=(g.implied_vol if g else None) or q.implied_vol,
                open_interest=q.open_interest,
                volume=q.volume,
                quote_time=q.quote_time,
                market_data_type=q.market_data_type,
                data_source=market_data_source_label(q.market_data_type) if q.market_data_type is not None else source,
                status=q.status,
            )
        )
    return QuotedChain(
        ticker=ticker,
        as_of=as_of,
        underlying_price=float(price),
        data_source=source,
        market_data_type=mdt,
        diagnostic_only=diagnostic,
        skip_reason=skip_reason,
        legs=legs,
    )
