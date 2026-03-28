"""Order creation and management via ib_insync."""

from __future__ import annotations

from typing import Any, Literal

from ib_insync import IB, LimitOrder, MarketOrder, Stock, Crypto, Option, Trade

from utils.logging import get_logger

log = get_logger(__name__)


def _trade_to_dict(trade: Trade) -> dict[str, Any]:
    o = trade.order
    st = trade.orderStatus
    return {
        "id": str(o.orderId),
        "client_order_id": str(o.orderId),
        "created_at": None,
        "updated_at": None,
        "filled_at": None,
        "symbol": trade.contract.symbol,
        "side": o.action.lower() if o.action else None,
        "type": o.orderType.lower() if o.orderType else None,
        "time_in_force": o.tif if o.tif else None,
        "qty": str(o.totalQuantity) if o.totalQuantity else None,
        "notional": None,
        "filled_qty": str(st.filled) if st else None,
        "filled_avg_price": str(st.avgFillPrice) if st and st.avgFillPrice else None,
        "status": st.status if st else None,
    }


def _build_contract(symbol: str, contract_symbol: str | None = None):
    """Build the appropriate IB contract object.

    If contract_symbol is provided, treat as options OCC symbol.
    Otherwise, detect crypto vs equity by symbol format.
    """
    if contract_symbol:
        # Parse OCC-style option symbol
        # OCC format: "AAPL  240315C00150000" — 6-char padded underlying, YYMMDD, C/P, 8-digit strike
        import re
        m = re.match(r'^(.{1,6})\s*(\d{6})([CP])(\d{8})$', contract_symbol.strip())
        if m:
            underlying = m.group(1).strip()
            date_str = m.group(2)
            right = m.group(3)
            strike = int(m.group(4)) / 1000.0
            expiry = "20" + date_str
            return Option(underlying, expiry, strike, right, "SMART")
        # Fallback: treat contract_symbol as localSymbol
        opt = Option()
        opt.localSymbol = contract_symbol
        return opt

    # Crypto symbols contain "/" (e.g., "BTC/USD") or common crypto tickers
    if "/" in symbol:
        parts = symbol.split("/")
        return Crypto(parts[0], "PAXOS", parts[1] if len(parts) > 1 else "USD")

    return Stock(symbol, "SMART", "USD")


def create_order(
    ib: IB,
    *,
    symbol: str,
    notional: float,
    side: Literal["buy", "sell"],
    order_type: Literal["market", "limit", "stop_limit"] = "market",
    time_in_force: Literal["gtc", "ioc", "day"] = "ioc",
    limit_price: float | None = None,
    stop_price: float | None = None,
    contract_symbol: str | None = None,
) -> dict[str, Any]:
    """Create an order via ib_insync.

    IB uses qty-based orders, so we convert notional to qty by fetching
    the current price first.
    """
    if notional <= 0:
        raise ValueError("notional must be > 0")

    contract = _build_contract(symbol, contract_symbol)
    ib.qualifyContracts(contract)

    # Fetch current price to convert notional -> qty
    ticker = ib.reqMktData(contract, snapshot=True)
    ib.sleep(2)  # wait for snapshot data
    price = ticker.last if ticker.last and ticker.last > 0 else ticker.close
    if not price or price <= 0:
        # Fallback: try midpoint of bid/ask
        if ticker.bid and ticker.ask and ticker.bid > 0:
            price = (ticker.bid + ticker.ask) / 2
        else:
            raise ValueError(f"Cannot determine price for {symbol} to convert notional to qty")
    ib.cancelMktData(contract)

    # For options: price is per-share, multiplier is 100, so cost per contract = price * 100
    # For stocks/crypto: multiplier is 1, so cost per unit = price
    multiplier = float(contract.multiplier) if contract.multiplier else 1.0
    cost_per_unit = price * multiplier
    qty = max(1, int(notional / cost_per_unit))

    action = "BUY" if side == "buy" else "SELL"
    tif = time_in_force.upper()

    log.info("IB create_order: %s %s qty=%d (notional=$%.2f @ $%.2f) %s", action, symbol, qty, notional, price, order_type)

    if order_type == "market":
        order = MarketOrder(action, qty, tif=tif)
    elif order_type == "limit":
        if limit_price is None:
            raise ValueError("limit_price is required for limit orders")
        order = LimitOrder(action, qty, limit_price, tif=tif)
    elif order_type == "stop_limit":
        if stop_price is None or limit_price is None:
            raise ValueError("stop_price and limit_price required for stop_limit orders")
        from ib_insync import Order as IBOrder
        order = IBOrder(
            action=action,
            totalQuantity=qty,
            orderType="STP LMT",
            lmtPrice=limit_price,
            auxPrice=stop_price,
            tif=tif,
        )
    else:
        raise ValueError(f"Unsupported order type: {order_type}")

    trade = ib.placeOrder(contract, order)
    ib.sleep(1)  # brief wait for acknowledgment

    result = _trade_to_dict(trade)
    log.info("IB create_order result: id=%s status=%s", result["id"], result["status"])
    return result


def get_order(ib: IB, *, order_id: str) -> dict[str, Any]:
    """Get a single order by ID."""
    log.info("IB get_order: %s", order_id)
    target_id = int(order_id)
    for trade in ib.trades():
        if trade.order.orderId == target_id:
            return _trade_to_dict(trade)
    return {"id": order_id, "status": "not_found"}


def list_orders(
    ib: IB,
    *,
    status: Literal["open", "closed", "all"] = "open",
    limit: int = 50,
) -> list[dict[str, Any]]:
    """List orders with optional status filter."""
    log.info("IB list_orders: status=%s limit=%s", status, limit)

    if status == "open":
        trades = ib.openTrades()
    else:
        trades = ib.trades()

    results = [_trade_to_dict(t) for t in trades[:limit]]

    if status == "closed":
        results = [r for r in results if r["status"] in ("Filled", "Cancelled", "Inactive")]

    return results
