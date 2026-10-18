"""Execution brokers for the deterministic cycle.

IBExecution: real IBKR paper via GuardedBroker (identity + token + revalidate).
SimBroker: dry-run; fills at the limit instantly, positions from the lineage store.
Both expose the same small contract so the cycle code path is identical.
"""

from __future__ import annotations

import itertools
import time
from collections.abc import Callable
from typing import Any, Protocol

from core.guarded_broker import GuardedBroker
from schemas.cycle import ComboIntent


class ExecutionBroker(Protocol):
    def place(self, intent: ComboIntent, *, revalidate: Callable[[ComboIntent], None]) -> dict[str, Any]: ...
    def wait(self, broker_order_id: str, seconds: int) -> dict[str, Any]: ...
    def cancel(self, broker_order_id: str) -> dict[str, Any]: ...
    def status(self, broker_order_id: str) -> dict[str, Any] | None: ...
    def option_positions(self, underlying: str) -> dict[str, float]: ...
    def open_order_ids(self, underlying: str) -> set[str]: ...
    def executions(self) -> list[dict[str, Any]]: ...


class IBExecution:
    def __init__(self, ib: Any, *, allow_trading: bool, expected_account_id: str | None = None,
                 sleep: Callable[[float], None] | None = None) -> None:
        self.ib = ib
        self.guard = GuardedBroker(ib, allow_trading=allow_trading, expected_account_id=expected_account_id,
                                   trading_mode="paper")
        self._sleep = sleep or ib.sleep

    def place(self, intent: ComboIntent, *, revalidate: Callable[[ComboIntent], None]) -> dict[str, Any]:
        preview = self.guard.preview_combo(intent)
        return self.guard.confirm_combo(preview.token, intent, revalidate=revalidate)

    def status(self, broker_order_id: str) -> dict[str, Any] | None:
        from integrations.ibkr.combo import find_trade, trade_status

        trade = find_trade(self.ib, broker_order_id)
        return trade_status(trade) if trade is not None else None

    def wait(self, broker_order_id: str, seconds: int) -> dict[str, Any]:
        deadline = time.monotonic() + seconds
        st = self.status(broker_order_id) or {"broker_order_id": broker_order_id, "status": "unknown", "fills": []}
        while st.get("status") != "Filled" and time.monotonic() < deadline:
            self._sleep(1.0)
            st = self.status(broker_order_id) or st
        return st

    def cancel(self, broker_order_id: str) -> dict[str, Any]:
        from integrations.ibkr.combo import find_trade, trade_status

        trade = find_trade(self.ib, broker_order_id)
        if trade is None:
            return {"broker_order_id": broker_order_id, "status": "not_found", "fills": []}
        if trade.orderStatus.status != "Filled":
            self.ib.cancelOrder(trade.order)
            self._sleep(2.0)
        return trade_status(trade)

    def settle(self) -> None:
        self._sleep(3.0)

    def option_positions(self, underlying: str) -> dict[str, float]:
        from integrations.ibkr.occ import format_occ_symbol

        out: dict[str, float] = {}
        for pos in self.ib.positions():
            c = pos.contract
            if (c.secType or "").upper() != "OPT" or c.symbol != underlying:
                continue
            occ = format_occ_symbol(c.symbol, c.lastTradeDateOrContractMonth, c.right, c.strike)
            out[occ] = out.get(occ, 0.0) + float(pos.position)
        return {k: v for k, v in out.items() if v != 0}

    def open_order_ids(self, underlying: str) -> set[str]:
        return {str(t.order.orderId) for t in self.ib.openTrades() if t.contract.symbol == underlying}

    def executions(self) -> list[dict[str, Any]]:
        from integrations.ibkr.orders import fill_to_record

        return [fill_to_record(f) for f in self.ib.fills()]


class SimBroker:
    """Dry-run broker. Positions are seeded from the lineage store so reconcile is real."""

    def __init__(self, positions: dict[str, float] | None = None, *, fill: bool = True) -> None:
        self._positions = dict(positions or {})
        self._orders: dict[str, dict[str, Any]] = {}
        self._ids = itertools.count(1)
        self._fill = fill
        self._execs: list[dict[str, Any]] = []

    def place(self, intent: ComboIntent, *, revalidate: Callable[[ComboIntent], None]) -> dict[str, Any]:
        revalidate(intent)
        oid = f"sim-{next(self._ids)}"
        rec: dict[str, Any] = {"broker_order_id": oid, "status": "Submitted", "filled": 0.0,
                               "avg_fill_price": None, "fills": [], "intent": intent}
        if self._fill:
            sign = 1 if intent.action == "BUY" else -1
            for leg in intent.legs:
                leg_sign = 1 if leg.action == "BUY" else -1
                q = self._positions.get(leg.occ, 0.0) + sign * leg_sign * intent.quantity
                if q == 0:
                    self._positions.pop(leg.occ, None)
                else:
                    self._positions[leg.occ] = q
            fill = {"exec_id": f"{oid}-x1", "order_id": oid, "symbol": intent.underlying,
                    "side": intent.action, "shares": intent.quantity, "price": intent.limit_price}
            self._execs.append(fill)
            rec.update(status="Filled", filled=float(intent.quantity), avg_fill_price=intent.limit_price,
                       fills=[fill])
        self._orders[oid] = rec
        return {k: v for k, v in rec.items() if k != "intent"}

    def status(self, broker_order_id: str) -> dict[str, Any] | None:
        rec = self._orders.get(broker_order_id)
        return None if rec is None else {k: v for k, v in rec.items() if k != "intent"}

    def wait(self, broker_order_id: str, seconds: int) -> dict[str, Any]:
        return self.status(broker_order_id) or {"broker_order_id": broker_order_id, "status": "unknown", "fills": []}

    def cancel(self, broker_order_id: str) -> dict[str, Any]:
        rec = self._orders[broker_order_id]
        if rec["status"] != "Filled":
            rec["status"] = "Cancelled"
        return self.status(broker_order_id)

    def option_positions(self, underlying: str) -> dict[str, float]:
        return {k: v for k, v in self._positions.items() if k.startswith(underlying)}

    def open_order_ids(self, underlying: str) -> set[str]:
        return {oid for oid, r in self._orders.items() if r["status"] not in ("Filled", "Cancelled")}

    def executions(self) -> list[dict[str, Any]]:
        return list(self._execs)
