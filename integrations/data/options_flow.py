"""Unusual options volume detection and flow analysis."""

from __future__ import annotations

from typing import Any

from ib_insync import IB

from integrations.ibkr.options_data import get_options_chain
from utils.logging import get_logger

log = get_logger(__name__)


def analyze_options_flow(
    ib: IB,
    symbol: str,
    *,
    min_dte: int = 0,
    max_dte: int = 45,
    min_volume_ratio: float = 2.0,
) -> dict[str, Any]:
    """Analyze options flow for unusual activity.

    Returns put/call ratio, volume analysis, and notable contracts.
    Uses live OI / IV from quotes when the Gateway provides them.
    """
    log.info("Analyzing options flow: %s DTE=%d-%d", symbol, min_dte, max_dte)

    contracts = get_options_chain(
        ib,
        symbol,
        min_dte=min_dte,
        max_dte=max_dte,
        limit=200,
        include_quotes=True,
    )

    if not contracts:
        return {
            "symbol": symbol,
            "total_contracts": 0,
            "error": "No option contracts found",
        }

    calls = [c for c in contracts if c.get("type", "").lower() == "call"]
    puts = [c for c in contracts if c.get("type", "").lower() == "put"]

    call_oi = sum(int(c.get("open_interest", 0) or 0) for c in calls)
    put_oi = sum(int(c.get("open_interest", 0) or 0) for c in puts)
    total_oi = call_oi + put_oi

    put_call_ratio = put_oi / call_oi if call_oi > 0 else None

    ivs = [
        float(c["implied_vol"])
        for c in contracts
        if c.get("implied_vol") is not None
    ]

    quote_errors: list[dict[str, Any]] = []
    seen: set[tuple[Any, str]] = set()
    for contract in contracts:
        for err in contract.get("quote_errors") or []:
            key = (err.get("code"), err.get("message", ""))
            if key in seen:
                continue
            seen.add(key)
            quote_errors.append(err)

    statuses = [c.get("quote_status") for c in contracts if c.get("quote_status")]
    quote_status = None
    for preferred in (
        "competing_live_session",
        "not_subscribed",
        "historical_session_conflict",
        "timeout",
        "ok",
    ):
        if preferred in statuses:
            quote_status = preferred
            break
    if quote_status is None and statuses:
        quote_status = statuses[0]

    return {
        "symbol": symbol,
        "total_contracts": len(contracts),
        "calls": len(calls),
        "puts": len(puts),
        "call_open_interest": call_oi,
        "put_open_interest": put_oi,
        "total_open_interest": total_oi,
        "put_call_ratio": round(put_call_ratio, 3) if put_call_ratio is not None else None,
        "avg_implied_vol": round(sum(ivs) / len(ivs), 4) if ivs else None,
        "contracts_with_oi": sum(1 for c in contracts if c.get("open_interest") is not None),
        "quote_status": quote_status,
        "quote_errors": quote_errors,
        "dte_range": f"{min_dte}-{max_dte}",
    }
