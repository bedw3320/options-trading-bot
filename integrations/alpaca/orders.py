"""Order creation and management via alpaca-py SDK."""

from __future__ import annotations

from typing import Any, Literal

from alpaca.trading.client import TradingClient
from alpaca.trading.enums import OrderSide, OrderType, TimeInForce, QueryOrderStatus
from alpaca.trading.requests import (
    GetOrdersRequest,
    LimitOrderRequest,
    MarketOrderRequest,
    StopLimitOrderRequest,
)

from utils.logging import get_logger

log = get_logger(__name__)

_SIDE_MAP = {"buy": OrderSide.BUY, "sell": OrderSide.SELL}
_TIF_MAP = {
    "gtc": TimeInForce.GTC,
    "ioc": TimeInForce.IOC,
    "day": TimeInForce.DAY,
    "opg": TimeInForce.OPG,
}


def _order_to_dict(order: Any) -> dict[str, Any]:
    return {
        "id": str(order.id),
        "client_order_id": order.client_order_id,
        "created_at": str(order.created_at) if order.created_at else None,
        "updated_at": str(order.updated_at) if order.updated_at else None,
        "filled_at": str(order.filled_at) if order.filled_at else None,
        "symbol": order.symbol,
        "side": str(order.side) if order.side else None,
        "type": str(order.type) if order.type else None,
        "time_in_force": str(order.time_in_force) if order.time_in_force else None,
        "qty": str(order.qty) if order.qty else None,
        "notional": str(order.notional) if order.notional else None,
        "filled_qty": str(order.filled_qty) if order.filled_qty else None,
        "filled_avg_price": str(order.filled_avg_price) if order.filled_avg_price else None,
        "status": str(order.status) if order.status else None,
    }


def create_order(
    client: TradingClient,
    *,
    symbol: str,
    notional: float,
    side: Literal["buy", "sell"],
    order_type: Literal["market", "limit", "stop_limit"] = "market",
    time_in_force: Literal["gtc", "ioc", "day"] = "ioc",
    limit_price: float | None = None,
    stop_price: float | None = None,
) -> dict[str, Any]:
    """Create an order via the SDK."""
    if notional <= 0:
        raise ValueError("notional must be > 0")

    sdk_side = _SIDE_MAP[side]
    sdk_tif = _TIF_MAP[time_in_force]

    log.info("Alpaca create_order: %s %s $%.2f %s", side, symbol, notional, order_type)

    if order_type == "market":
        req = MarketOrderRequest(
            symbol=symbol,
            notional=notional,
            side=sdk_side,
            time_in_force=sdk_tif,
        )
    elif order_type == "limit":
        if limit_price is None:
            raise ValueError("limit_price is required for limit orders")
        req = LimitOrderRequest(
            symbol=symbol,
            notional=notional,
            side=sdk_side,
            time_in_force=sdk_tif,
            limit_price=limit_price,
        )
    elif order_type == "stop_limit":
        if stop_price is None or limit_price is None:
            raise ValueError("stop_price and limit_price required for stop_limit orders")
        req = StopLimitOrderRequest(
            symbol=symbol,
            notional=notional,
            side=sdk_side,
            time_in_force=sdk_tif,
            limit_price=limit_price,
            stop_price=stop_price,
        )
    else:
        raise ValueError(f"Unsupported order type: {order_type}")

    order = client.submit_order(req)
    result = _order_to_dict(order)
    log.info("Alpaca create_order result: id=%s status=%s", result["id"], result["status"])
    return result


def get_order(client: TradingClient, *, order_id: str) -> dict[str, Any]:
    """Get a single order by ID."""
    log.info("Alpaca get_order: %s", order_id)
    order = client.get_order_by_id(order_id)
    return _order_to_dict(order)


def list_orders(
    client: TradingClient,
    *,
    status: Literal["open", "closed", "all"] = "open",
    limit: int = 50,
) -> list[dict[str, Any]]:
    """List orders with optional status filter."""
    status_map = {
        "open": QueryOrderStatus.OPEN,
        "closed": QueryOrderStatus.CLOSED,
        "all": QueryOrderStatus.ALL,
    }
    req = GetOrdersRequest(status=status_map[status], limit=limit)
    log.info("Alpaca list_orders: status=%s limit=%s", status, limit)
    orders = client.get_orders(req)
    return [_order_to_dict(o) for o in orders]
