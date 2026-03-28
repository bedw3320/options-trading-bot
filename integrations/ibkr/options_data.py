"""Options chain and contract data via ib_insync."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from ib_insync import IB, Stock, Option

from utils.logging import get_logger

log = get_logger(__name__)


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
) -> list[dict[str, Any]]:
    """Search for option contracts using IB's option chain API.

    Returns a list of option contract dicts matching the Alpaca format.
    """
    stock = Stock(underlying_symbol, "SMART", "USD")
    ib.qualifyContracts(stock)

    log.info("Fetching option params for %s", underlying_symbol)
    chains = ib.reqSecDefOptParams(stock.symbol, "", stock.secType, stock.conId)

    if not chains:
        log.warning("No option chains found for %s", underlying_symbol)
        return []

    # Use the SMART exchange chain (most common)
    chain = next((c for c in chains if c.exchange == "SMART"), chains[0])

    contracts = []
    for expiry in sorted(chain.expirations):
        # Filter by date range
        if expiration_date_gte and expiry < expiration_date_gte.replace("-", ""):
            continue
        if expiration_date_lte and expiry > expiration_date_lte.replace("-", ""):
            continue

        for strike in sorted(chain.strikes):
            if strike_price_gte is not None and strike < strike_price_gte:
                continue
            if strike_price_lte is not None and strike > strike_price_lte:
                continue

            rights = []
            if option_type:
                rights = ["C" if option_type.lower() == "call" else "P"]
            else:
                rights = ["C", "P"]

            for right in rights:
                contracts.append({
                    "symbol": f"{underlying_symbol}{expiry}{right}{int(strike * 1000):08d}",
                    "name": f"{underlying_symbol} {expiry} {strike} {right}",
                    "underlying_symbol": underlying_symbol,
                    "expiration_date": f"{expiry[:4]}-{expiry[4:6]}-{expiry[6:8]}",
                    "strike_price": str(strike),
                    "type": "call" if right == "C" else "put",
                    "status": "active",
                    "tradable": True,
                    "open_interest": None,
                })

                if len(contracts) >= limit:
                    break
            if len(contracts) >= limit:
                break
        if len(contracts) >= limit:
            break

    log.info("Found %d option contracts for %s", len(contracts), underlying_symbol)
    return contracts


def get_options_chain(
    ib: IB,
    underlying_symbol: str,
    *,
    min_dte: int = 0,
    max_dte: int = 45,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """Get options chain for a ticker within a DTE range."""
    today = datetime.now().date()
    exp_gte = str(today + timedelta(days=min_dte))
    exp_lte = str(today + timedelta(days=max_dte))

    return get_option_contracts(
        ib,
        underlying_symbol,
        expiration_date_gte=exp_gte,
        expiration_date_lte=exp_lte,
        limit=limit,
    )
