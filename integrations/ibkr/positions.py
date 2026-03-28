"""Position management via ib_insync."""

from __future__ import annotations

from typing import Any

import math

from ib_insync import IB, MarketOrder

from utils.logging import get_logger

log = get_logger(__name__)


def _classify_contract(contract) -> str:
    sec_type = contract.secType
    if sec_type == "STK":
        return "us_equity"
    if sec_type == "OPT":
        return "option"
    if sec_type == "CRYPTO":
        return "crypto"
    return sec_type.lower()


def list_positions(ib: IB) -> list[dict[str, Any]]:
    """List all open positions as dicts (same shape as former Alpaca version)."""
    log.info("IB list_positions")
    positions = ib.positions()
    result = []
    for pos in positions:
        c = pos.contract
        multiplier = float(c.multiplier) if c.multiplier else 1.0
        result.append({
            "asset_id": str(c.conId),
            "symbol": c.symbol,
            "asset_class": _classify_contract(c),
            "exchange": c.exchange or "SMART",
            "qty": str(pos.position),
            "avg_entry_price": str(pos.avgCost / multiplier),
            "current_price": None,
            "market_value": str(pos.position * pos.avgCost) if pos.avgCost else None,
            "unrealized_pl": None,
            "unrealized_plpc": None,
            "side": "long" if pos.position > 0 else "short",
        })
    return result


def close_position(
    ib: IB,
    *,
    symbol_or_asset_id: str,
    qty: float | None = None,
    percentage: float | None = None,
) -> dict[str, Any]:
    """Close a position (fully or partially) by placing an opposing market order."""
    if qty is not None and percentage is not None:
        raise ValueError("Provide qty OR percentage, not both.")

    log.info("IB close_position: %s qty=%s pct=%s", symbol_or_asset_id, qty, percentage)

    # Find the position
    target = None
    for pos in ib.positions():
        if pos.contract.symbol == symbol_or_asset_id or str(pos.contract.conId) == symbol_or_asset_id:
            target = pos
            break

    if target is None:
        raise ValueError(f"No open position found for {symbol_or_asset_id}")

    position_qty = abs(float(target.position))
    if qty is not None:
        close_qty = min(abs(qty), position_qty)
    elif percentage is not None:
        close_qty = position_qty * (percentage / 100.0)
    else:
        close_qty = position_qty

    close_qty = math.ceil(close_qty)
    if close_qty <= 0:
        raise ValueError(f"Computed close qty is 0 for {symbol_or_asset_id}")

    # Opposing side
    action = "SELL" if target.position > 0 else "BUY"
    contract = target.contract
    ib.qualifyContracts(contract)

    order = MarketOrder(action, close_qty)
    trade = ib.placeOrder(contract, order)
    ib.sleep(1)  # brief wait for order acknowledgment

    return {
        "id": str(trade.order.orderId),
        "status": trade.orderStatus.status if trade.orderStatus else None,
        "symbol": contract.symbol,
        "side": action.lower(),
        "filled_qty": str(trade.orderStatus.filled) if trade.orderStatus else None,
    }
