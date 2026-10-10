"""Options chain via real expiry/strike combos (not union cartesian)."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from ib_insync import IB, Option, Stock

from integrations.ibkr.occ import format_occ_symbol
from integrations.ibkr.option_quotes import is_finite_price, mid_price, request_quote, request_quotes
from utils.logging import get_logger

log = get_logger(__name__)

ET = ZoneInfo("America/New_York")


def select_option_chain(
    chains: list[Any],
    *,
    trading_class: str,
    exchange: str = "SMART",
) -> Any | None:
    """SMART chain whose tradingClass matches (SPY not 2SPY; SPX not SPXW)."""
    if not chains:
        return None
    wanted = trading_class.strip().upper()
    matched = [
        c for c in chains if (getattr(c, "tradingClass", "") or "").upper() == wanted
    ]
    if not matched:
        return None
    smart = [c for c in matched if (getattr(c, "exchange", "") or "").upper() == exchange.upper()]
    return smart[0] if smart else matched[0]


def expiries_in_window(
    expirations: list[str],
    *,
    expiration_date_gte: str | None = None,
    expiration_date_lte: str | None = None,
    max_expiries: int = 2,
    today: date | None = None,
) -> list[str]:
    """Keep real YYYYMMDD expiries in [gte, lte], nearest the window midpoint."""
    today = today or datetime.now(ET).date()
    gte = (expiration_date_gte or "").replace("-", "")
    lte = (expiration_date_lte or "").replace("-", "")
    kept: list[str] = []
    for raw in expirations:
        exp = str(raw).replace("-", "")
        if len(exp) != 8 or not exp.isdigit():
            continue
        if gte and exp < gte:
            continue
        if lte and exp > lte:
            continue
        kept.append(exp)
    kept = sorted(set(kept))
    if len(kept) <= max_expiries:
        return kept
    if gte and lte and len(gte) == 8 and len(lte) == 8:
        start = date(int(gte[:4]), int(gte[4:6]), int(gte[6:8]))
        end = date(int(lte[:4]), int(lte[4:6]), int(lte[6:8]))
        mid = start + (end - start) / 2
    else:
        mid = today
    kept.sort(key=lambda e: (abs(date(int(e[:4]), int(e[4:6]), int(e[6:8])) - mid), e))
    return sorted(kept[:max_expiries])


def nearest_strikes(strikes: list[float], price: float, n: int) -> list[float]:
    uniq = sorted({float(s) for s in strikes})
    if n <= 0 or not uniq:
        return []
    picked = sorted(uniq, key=lambda s: (abs(s - price), s))[:n]
    return sorted(picked)


def _contract_row(contract: Any, underlying: str) -> dict[str, Any]:
    expiry = (contract.lastTradeDateOrContractMonth or "").replace("-", "")
    right = (contract.right or "").upper()
    strike = float(contract.strike)
    occ = format_occ_symbol(underlying, expiry, right, strike)
    return {
        "symbol": occ,
        "name": f"{underlying} {expiry} {strike} {right}",
        "underlying_symbol": underlying,
        "expiration_date": f"{expiry[:4]}-{expiry[4:6]}-{expiry[6:8]}" if len(expiry) == 8 else expiry,
        "strike_price": str(strike),
        "type": "call" if right == "C" else "put",
        "status": "active",
        "tradable": True,
        "open_interest": None,
        "implied_vol": None,
        "trading_class": getattr(contract, "tradingClass", None) or underlying,
        "exchange": getattr(contract, "exchange", None) or "SMART",
        "con_id": getattr(contract, "conId", None) or None,
    }


def _underlying_price(ib: IB, symbol: str, *, timeout: float = 5.0) -> tuple[float | None, str]:
    stock = Stock(symbol, "SMART", "USD")
    qualified = ib.qualifyContracts(stock)
    contract = qualified[0] if qualified else stock
    quote = request_quote(ib, contract, timeout=timeout, require_bid_ask=False, require_greeks=False)
    if is_finite_price(quote.last):
        return float(quote.last), "last"
    if is_finite_price(quote.close):
        return float(quote.close), "close"
    mid = mid_price(quote.bid, quote.ask)
    if mid is not None:
        return mid, "mid"
    return None, "unavailable"


def get_option_contracts(
    ib: IB,
    underlying_symbol: str,
    *,
    expiration_date_gte: str | None = None,
    expiration_date_lte: str | None = None,
    strike_price_gte: float | None = None,
    strike_price_lte: float | None = None,
    option_type: str | None = None,
    limit: int = 100,
    trading_class: str | None = None,
    n_strikes: int = 5,
    max_expiries: int = 2,
    include_quotes: bool = False,
    require_greeks: bool = False,
    underlying_price: float | None = None,
    today: date | None = None,
    quote_timeout: float = 10.0,
) -> list[dict[str, Any]]:
    """Search for option contracts using per-expiry contract details.

    Does not cartesian-product ``chain.strikes`` (union) against every expiry.
    """
    trading_class = (trading_class or underlying_symbol).strip().upper()
    stock = Stock(underlying_symbol, "SMART", "USD")
    ib.qualifyContracts(stock)

    log.info("Fetching option params for %s tradingClass=%s", underlying_symbol, trading_class)
    chains = ib.reqSecDefOptParams(stock.symbol, "", stock.secType, stock.conId)
    chain = select_option_chain(chains, trading_class=trading_class)
    if chain is None:
        log.warning("No option chain for %s tradingClass=%s", underlying_symbol, trading_class)
        return []

    expiries = expiries_in_window(
        list(chain.expirations),
        expiration_date_gte=expiration_date_gte,
        expiration_date_lte=expiration_date_lte,
        max_expiries=max_expiries,
        today=today,
    )
    if not expiries:
        log.warning("No expiries in window for %s", underlying_symbol)
        return []

    price = underlying_price
    price_source = "caller"
    if price is None:
        price, price_source = _underlying_price(ib, underlying_symbol)

    rights: set[str] | None = None
    if option_type:
        rights = {"C"} if option_type.lower() == "call" else {"P"}

    selected: list[Any] = []
    for expiry in expiries:
        probe = Option(
            underlying_symbol,
            expiry,
            exchange="SMART",
            currency="USD",
            multiplier="100",
            tradingClass=trading_class,
        )
        details = ib.reqContractDetails(probe)
        contracts = [d.contract for d in details if getattr(d, "contract", None) is not None]
        contracts = [
            c
            for c in contracts
            if (getattr(c, "tradingClass", "") or "").upper() == trading_class
        ]
        if rights:
            contracts = [c for c in contracts if (c.right or "").upper() in rights]
        if strike_price_gte is not None:
            contracts = [c for c in contracts if float(c.strike) >= strike_price_gte]
        if strike_price_lte is not None:
            contracts = [c for c in contracts if float(c.strike) <= strike_price_lte]
        if not contracts:
            continue
        ref = price
        if ref is None:
            strikes = [float(c.strike) for c in contracts]
            ref = sorted(strikes)[len(strikes) // 2]
            price_source = "median_strike"
        keep = set(nearest_strikes([float(c.strike) for c in contracts], ref, n_strikes))
        for contract in contracts:
            if float(contract.strike) in keep:
                selected.append(contract)
                if len(selected) >= limit:
                    break
        if len(selected) >= limit:
            break

    rows = [_contract_row(c, underlying_symbol) for c in selected]
    for row in rows:
        row["underlying_price"] = price
        row["price_source"] = price_source

    if include_quotes and selected:
        quotes = request_quotes(
            ib,
            selected,
            timeout=quote_timeout,
            require_greeks=require_greeks,
        )
        for row, quote in zip(rows, quotes):
            row["open_interest"] = quote.open_interest
            row["implied_vol"] = quote.implied_vol
            row["bid"] = quote.bid
            row["ask"] = quote.ask
            row["mid"] = quote.mid
            row["quote_status"] = quote.status
            row["quote_errors"] = [e.model_dump() for e in quote.errors]
            if quote.model_greeks:
                row["delta"] = quote.model_greeks.delta
                row["gamma"] = quote.model_greeks.gamma
                row["vega"] = quote.model_greeks.vega
                row["theta"] = quote.model_greeks.theta

    log.info("Found %d option contracts for %s", len(rows), underlying_symbol)
    return rows


def get_options_chain(
    ib: IB,
    underlying_symbol: str,
    *,
    min_dte: int = 0,
    max_dte: int = 45,
    limit: int = 100,
    trading_class: str | None = None,
    n_strikes: int = 5,
    max_expiries: int = 2,
    include_quotes: bool = False,
    require_greeks: bool = False,
    underlying_price: float | None = None,
    today: date | None = None,
    quote_timeout: float = 10.0,
) -> list[dict[str, Any]]:
    """Get options chain for a ticker within a DTE range."""
    day = today or datetime.now(ET).date()
    exp_gte = str(day + timedelta(days=min_dte))
    exp_lte = str(day + timedelta(days=max_dte))

    return get_option_contracts(
        ib,
        underlying_symbol,
        expiration_date_gte=exp_gte,
        expiration_date_lte=exp_lte,
        limit=limit,
        trading_class=trading_class,
        n_strikes=n_strikes,
        max_expiries=max_expiries,
        include_quotes=include_quotes,
        require_greeks=require_greeks,
        underlying_price=underlying_price,
        today=day,
        quote_timeout=quote_timeout,
    )
