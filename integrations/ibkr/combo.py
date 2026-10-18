"""IBKR BAG (combo) orders for multi-leg option structures.

Only GuardedBroker.confirm_combo may call place_combo (LOOP constraint 1).
"""

from __future__ import annotations

from typing import Any

from ib_insync import Bag, ComboLeg, LimitOrder

from integrations.ibkr.occ import make_option
from integrations.ibkr.orders import fill_to_record
from schemas.cycle import ComboIntent
from utils.logging import get_logger

log = get_logger(__name__)


def build_bag(ib: Any, intent: ComboIntent) -> Bag:
    opts = [make_option(intent.underlying, l.expiry, l.strike, l.right) for l in intent.legs]
    ib.qualifyContracts(*opts)
    legs = []
    for opt, leg in zip(opts, intent.legs):
        con_id = getattr(opt, "conId", 0) or leg.con_id
        if not con_id:
            raise ValueError(f"could not qualify {leg.occ}")
        legs.append(ComboLeg(conId=int(con_id), ratio=leg.ratio, action=leg.action, exchange="SMART"))
    return Bag(symbol=intent.underlying, exchange="SMART", currency="USD", comboLegs=legs)


def place_combo(ib: Any, intent: ComboIntent) -> dict[str, Any]:
    bag = build_bag(ib, intent)
    order = LimitOrder(intent.action, intent.quantity, round(intent.limit_price, 2), tif="DAY")
    order.orderRef = intent.idempotency_key[:40]
    order.smartComboRoutingParams = []
    trade = ib.placeOrder(bag, order)
    ib.sleep(1)
    log.info("IB combo %s x%d @ %.2f -> orderId=%s", intent.action, intent.quantity,
             intent.limit_price, trade.order.orderId)
    return trade_status(trade)


def trade_status(trade: Any) -> dict[str, Any]:
    st = trade.orderStatus
    return {
        "broker_order_id": str(trade.order.orderId),
        "perm_id": getattr(trade.order, "permId", None),
        "status": st.status if st else None,
        "filled": float(st.filled) if st and st.filled is not None else 0.0,
        "avg_fill_price": float(st.avgFillPrice) if st and st.avgFillPrice else None,
        "fills": [fill_to_record(f) for f in (getattr(trade, "fills", None) or [])],
    }


def find_trade(ib: Any, broker_order_id: str) -> Any | None:
    for t in ib.trades():
        if str(t.order.orderId) == str(broker_order_id):
            return t
    return None
