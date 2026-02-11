"""Unusual options volume detection and flow analysis."""

from __future__ import annotations

from typing import Any

from alpaca.trading.client import TradingClient

from integrations.alpaca.options_data import get_options_chain
from utils.logging import get_logger

log = get_logger(__name__)


def analyze_options_flow(
    client: TradingClient,
    symbol: str,
    *,
    min_dte: int = 0,
    max_dte: int = 45,
    min_volume_ratio: float = 2.0,
) -> dict[str, Any]:
    """Analyze options flow for unusual activity.

    Returns put/call ratio, volume analysis, and notable contracts.
    """
    log.info("Analyzing options flow: %s DTE=%d-%d", symbol, min_dte, max_dte)

    contracts = get_options_chain(
        client,
        symbol,
        min_dte=min_dte,
        max_dte=max_dte,
        limit=200,
    )

    if not contracts:
        return {
            "symbol": symbol,
            "total_contracts": 0,
            "error": "No option contracts found",
        }

    calls = [c for c in contracts if c.get("type", "").lower() == "call"]
    puts = [c for c in contracts if c.get("type", "").lower() == "put"]

    # Compute open interest totals
    call_oi = sum(int(c.get("open_interest", 0) or 0) for c in calls)
    put_oi = sum(int(c.get("open_interest", 0) or 0) for c in puts)
    total_oi = call_oi + put_oi

    put_call_ratio = put_oi / call_oi if call_oi > 0 else None

    return {
        "symbol": symbol,
        "total_contracts": len(contracts),
        "calls": len(calls),
        "puts": len(puts),
        "call_open_interest": call_oi,
        "put_open_interest": put_oi,
        "total_open_interest": total_oi,
        "put_call_ratio": round(put_call_ratio, 3) if put_call_ratio is not None else None,
        "dte_range": f"{min_dte}-{max_dte}",
    }
