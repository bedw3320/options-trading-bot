"""Account info via ib_insync."""

from __future__ import annotations

from typing import Any

from ib_insync import IB

from utils.logging import get_logger

log = get_logger(__name__)


def get_account(ib: IB) -> dict[str, Any]:
    """Get account info as a dict (same shape as former Alpaca version)."""
    log.info("IB get_account")
    summary = ib.accountSummary()
    if not summary:
        raise RuntimeError("IB accountSummary returned empty — check connection")
    vals = {item.tag: item.value for item in summary}

    return {
        "id": vals.get("AccountCode", ""),
        "account_number": vals.get("AccountCode", ""),
        "status": "active",
        "crypto_status": None,
        "currency": vals.get("Currency", "USD"),
        "buying_power": vals.get("BuyingPower"),
        "cash": vals.get("TotalCashValue"),
        "portfolio_value": vals.get("NetLiquidation"),
        "equity": vals.get("NetLiquidation"),
        "last_equity": None,
        "trading_blocked": False,
        "account_blocked": False,
    }
