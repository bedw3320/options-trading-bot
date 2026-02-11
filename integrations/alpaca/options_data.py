"""Options chain, quotes, and contract search via alpaca-py SDK."""

from __future__ import annotations

import os
from datetime import datetime, timedelta
from typing import Any

from alpaca.data.historical.option import OptionHistoricalDataClient
from alpaca.trading.client import TradingClient
from dotenv import load_dotenv

from utils.logging import get_logger

load_dotenv()
log = get_logger(__name__)


def _get_option_data_client() -> OptionHistoricalDataClient:
    return OptionHistoricalDataClient(
        api_key=os.environ.get("ALPACA_KEY"),
        secret_key=os.environ.get("ALPACA_SECRET"),
    )


def get_option_contracts(
    client: TradingClient,
    underlying_symbol: str,
    *,
    expiration_date_gte: str | None = None,
    expiration_date_lte: str | None = None,
    strike_price_gte: float | None = None,
    strike_price_lte: float | None = None,
    option_type: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """Search for option contracts using the Trading API.

    Returns a list of option contract dicts with symbol, expiration, strike, type.
    """
    from alpaca.trading.requests import GetOptionContractsRequest

    params: dict[str, Any] = {
        "underlying_symbols": [underlying_symbol],
        "limit": limit,
    }
    if expiration_date_gte:
        params["expiration_date_gte"] = expiration_date_gte
    if expiration_date_lte:
        params["expiration_date_lte"] = expiration_date_lte
    if strike_price_gte is not None:
        params["strike_price_gte"] = str(strike_price_gte)
    if strike_price_lte is not None:
        params["strike_price_lte"] = str(strike_price_lte)
    if option_type:
        params["type"] = option_type

    log.info("Fetching option contracts: %s params=%s", underlying_symbol, params)
    req = GetOptionContractsRequest(**params)
    response = client.get_option_contracts(req)

    contracts = []
    if response and response.option_contracts:
        for c in response.option_contracts:
            contracts.append({
                "symbol": c.symbol,
                "name": c.name,
                "underlying_symbol": c.underlying_symbol,
                "expiration_date": str(c.expiration_date) if c.expiration_date else None,
                "strike_price": str(c.strike_price) if c.strike_price else None,
                "type": str(c.type) if c.type else None,
                "status": str(c.status) if c.status else None,
                "tradable": c.tradable,
                "open_interest": str(c.open_interest) if c.open_interest else None,
            })

    log.info("Found %d option contracts for %s", len(contracts), underlying_symbol)
    return contracts


def get_options_chain(
    client: TradingClient,
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
        client,
        underlying_symbol,
        expiration_date_gte=exp_gte,
        expiration_date_lte=exp_lte,
        limit=limit,
    )
