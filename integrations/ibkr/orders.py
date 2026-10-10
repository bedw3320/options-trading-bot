"""Order creation and management via ib_insync."""

from __future__ import annotations

import time
from typing import Any, Literal

from ib_insync import IB, LimitOrder, MarketOrder, Stock, Crypto, Option, Trade

from integrations.ibkr.occ import option_from_occ, parse_occ_symbol
from integrations.ibkr.option_quotes import resolve_order_price, ticker_ready_for_order, wait_until
from utils.logging import get_logger
from utils.time_et import format_time_et, ib_exec_time_to_et

log = get_logger(__name__)


def fill_to_record(fill: Any) -> dict[str, Any]:
    """IB execution.time is UTC; persist time_et."""
    exe = getattr(fill, "execution", None)
    raw_time = getattr(exe, "time", None) if exe is not None else None
    if raw_time is None:
        raw_time = getattr(fill, "time", None)
    et = ib_exec_time_to_et(raw_time)
    contract = getattr(fill, "contract", None)
    return {
        "exec_id": getattr(exe, "execId", None) if exe is not None else None,
        "order_id": str(getattr(exe, "orderId", "") or "") if exe is not None else None,
        "symbol": getattr(contract, "symbol", None),
        "side": getattr(exe, "side", None) if exe is not None else None,
        "shares": getattr(exe, "shares", None) if exe is not None else None,
        "price": getattr(exe, "price", None) if exe is not None else None,
        "exchange": getattr(exe, "exchange", None) if exe is not None else None,
        "time_et": et.isoformat() if et else format_time_et(raw_time),
    }


def fills_for_order(ib: IB, order_id: str) -> list[dict[str, Any]]:
    getter = getattr(ib, "fills", None)
    raw = getter() if callable(getter) else []
    if not isinstance(raw, (list, tuple)):
        return []
    target = str(order_id)
    out: list[dict[str, Any]] = []
    for fill in raw:
        rec = fill_to_record(fill)
        if rec.get("order_id") == target:
            out.append(rec)
    return out


def _fills_from_trade(trade: Trade) -> list[dict[str, Any]]:
    raw = getattr(trade, "fills", None) or []
    if not isinstance(raw, (list, tuple)):
        return []
    return [fill_to_record(f) for f in raw]


def _trade_to_dict(trade: Trade) -> dict[str, Any]:
    o = trade.order
    st = trade.orderStatus
    fills = _fills_from_trade(trade)
    filled_at = fills[-1]["time_et"] if fills else None
    return {
        "id": str(o.orderId),
        "client_order_id": str(o.orderId),
        "created_at": None,
        "updated_at": None,
        "filled_at": filled_at,
        "symbol": trade.contract.symbol,
        "side": o.action.lower() if o.action else None,
        "type": o.orderType.lower() if o.orderType else None,
        "time_in_force": o.tif if o.tif else None,
        "qty": str(o.totalQuantity) if o.totalQuantity else None,
        "notional": None,
        "filled_qty": str(st.filled) if st else None,
        "filled_avg_price": str(st.avgFillPrice) if st and st.avgFillPrice else None,
        "status": st.status if st else None,
        "fills": fills,
    }


def _build_contract(symbol: str, contract_symbol: str | None = None):
    """Build the appropriate IB contract object.

    If contract_symbol is provided, treat as options OCC symbol (yymmdd).
    Otherwise, detect crypto vs equity by symbol format.
    """
    if contract_symbol:
        try:
            parts = parse_occ_symbol(contract_symbol)
            return option_from_occ(parts.occ_symbol, trading_class=parts.underlying)
        except ValueError:
            opt = Option()
            opt.localSymbol = contract_symbol
            opt.exchange = "SMART"
            opt.currency = "USD"
            return opt

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
    quote_timeout: float = 10.0,
) -> dict[str, Any]:
    """Create an order via ib_insync.

    IB uses qty-based orders, so we convert notional to qty by fetching
    the current price first. Options fail closed unless bid/ask are finite.
    """
    if notional <= 0:
        raise ValueError("notional must be > 0")

    contract = _build_contract(symbol, contract_symbol)
    ib.qualifyContracts(contract)
    is_option = (getattr(contract, "secType", "") or "").upper() == "OPT"

    # Stream — generic ticks are not used (and are illegal with snapshot=True).
    ticker = ib.reqMktData(contract, "", False, False)
    try:
        wait_until(
            lambda: ticker_ready_for_order(ticker, is_option=is_option),
            timeout=quote_timeout,
            sleep=ib.sleep,
            clock=time.monotonic,
        )
        try:
            price = resolve_order_price(ticker, is_option=is_option)
        except ValueError as exc:
            raise ValueError(f"Cannot determine price for {symbol} to convert notional to qty") from exc
    finally:
        try:
            ib.cancelMktData(contract)
        except Exception:
            pass

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
