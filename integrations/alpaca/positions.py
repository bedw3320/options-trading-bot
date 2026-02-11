"""Position management via alpaca-py SDK."""

from __future__ import annotations

from typing import Any

from alpaca.trading.client import TradingClient
from alpaca.trading.requests import ClosePositionRequest

from utils.logging import get_logger

log = get_logger(__name__)


def list_positions(client: TradingClient) -> list[dict[str, Any]]:
    """List all open positions as dicts."""
    log.info("Alpaca list_positions via SDK")
    positions = client.get_all_positions()
    return [
        {
            "asset_id": str(p.asset_id),
            "symbol": p.symbol,
            "asset_class": str(p.asset_class) if p.asset_class else None,
            "exchange": str(p.exchange) if p.exchange else None,
            "qty": str(p.qty) if p.qty else None,
            "avg_entry_price": str(p.avg_entry_price) if p.avg_entry_price else None,
            "current_price": str(p.current_price) if p.current_price else None,
            "market_value": str(p.market_value) if p.market_value else None,
            "unrealized_pl": str(p.unrealized_pl) if p.unrealized_pl else None,
            "unrealized_plpc": str(p.unrealized_plpc) if p.unrealized_plpc else None,
            "side": str(p.side) if p.side else None,
        }
        for p in positions
    ]


def close_position(
    client: TradingClient,
    *,
    symbol_or_asset_id: str,
    qty: float | None = None,
    percentage: float | None = None,
) -> dict[str, Any]:
    """Close a position (fully or partially)."""
    if qty is not None and percentage is not None:
        raise ValueError("Provide qty OR percentage, not both.")

    log.info("Alpaca close_position: %s qty=%s pct=%s", symbol_or_asset_id, qty, percentage)

    close_options = ClosePositionRequest(
        qty=str(qty) if qty is not None else None,
        percentage=str(percentage) if percentage is not None else None,
    )

    order = client.close_position(symbol_or_asset_id, close_options=close_options)
    return {
        "id": str(order.id),
        "status": str(order.status) if order.status else None,
        "symbol": order.symbol,
        "side": str(order.side) if order.side else None,
        "filled_qty": str(order.filled_qty) if order.filled_qty else None,
    }
