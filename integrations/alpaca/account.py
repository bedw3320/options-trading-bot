"""Account info via alpaca-py SDK."""

from __future__ import annotations

from typing import Any

from alpaca.trading.client import TradingClient

from utils.logging import get_logger

log = get_logger(__name__)


def get_account(client: TradingClient) -> dict[str, Any]:
    """Get account info as a dict."""
    log.info("Alpaca get_account via SDK")
    acct = client.get_account()
    return {
        "id": str(acct.id),
        "account_number": acct.account_number,
        "status": str(acct.status) if acct.status else None,
        "crypto_status": str(acct.crypto_status) if acct.crypto_status else None,
        "currency": acct.currency,
        "buying_power": str(acct.buying_power) if acct.buying_power else None,
        "cash": str(acct.cash) if acct.cash else None,
        "portfolio_value": str(acct.portfolio_value) if acct.portfolio_value else None,
        "equity": str(acct.equity) if acct.equity else None,
        "last_equity": str(acct.last_equity) if acct.last_equity else None,
        "trading_blocked": acct.trading_blocked,
        "account_blocked": acct.account_blocked,
    }
