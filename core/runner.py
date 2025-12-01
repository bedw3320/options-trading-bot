from __future__ import annotations

import time
from typing import Any

from core.agent import agent
from integrations.alpaca.orders import create_order as alpaca_create_order
from integrations.alpaca.orders import get_order as alpaca_get_order
from integrations.alpaca.positions import list_positions as alpaca_list_positions
from schemas.deps import Deps
from utils.state import load_state, save_state


def snapshot_positions(deps: Deps) -> dict[str, Any]:
    positions = alpaca_list_positions(deps.alpaca)
    return {
        p.symbol: {
            "qty": p.qty,
            "side": p.side,
            "market_value": p.market_value,
            "avg_entry_price": p.avg_entry_price,
            "current_price": p.current_price,
            "unrealized_pl": p.unrealized_pl,
            "unrealized_plpc": p.unrealized_plpc,
        }
        for p in positions
    }


def reconcile_order_and_positions(
    deps: Deps,
    state: dict[str, Any],
    order_id: str,
) -> dict[str, Any]:
    order = alpaca_get_order(deps.alpaca, order_id=order_id).model_dump()

    state.setdefault("orders", {})
    state["orders"][order_id] = {
        "status": order.get("status"),
        "filled_qty": order.get("filled_qty"),
        "filled_avg_price": order.get("filled_avg_price"),
        "symbol": order.get("symbol"),
        "side": order.get("side"),
        "notional": order.get("notional"),
        "updated_at": order.get("updated_at"),
        "last_checked_ts": int(time.time()),
    }

    state["positions"] = snapshot_positions(deps)
    save_state(state)
    return order


def run_once(
    deps: Deps,
    *,
    prompt: str,
    conf_threshold: float = 0.75,
    poll_sleep_seconds: int = 30,
    state_path: str = "state.json",
) -> None:
    state = load_state(state_path)

    # 1) ask agent
    run = agent.run_sync(prompt, deps=deps)
    out = run.output.model_dump()

    confidence = float(out.get("confidence", 0.0))
    order_intent = out.get("order") or {}

    print(run.output.model_dump_json(indent=2))

    # 2) hard gates (deterministic)
    if not deps.allow_trading:
        return
    if confidence < conf_threshold:
        print(f"Skipping trade: confidence {confidence} < {conf_threshold}")
        return

    side = order_intent.get("side")
    if side in (None, "hold"):
        print("No trade to place (hold/none).")
        return

    notional = order_intent.get("notional")
    if notional is None:
        print("Trade proposed but notional is missing -> skipping.")
        return

    # 3) place order
    placed = alpaca_create_order(
        deps.alpaca,
        symbol=order_intent["symbol"],
        notional=float(notional),
        side=side,  # buy/sell
        time_in_force=order_intent.get("time_in_force", "ioc"),
        order_type="market",
    )

    order_id = placed.get("id")
    if not order_id:
        print("Order placed but no id returned:", placed)
        return

    state.setdefault("orders", {})
    state["orders"].setdefault(order_id, {})
    save_state(state, state_path)

    # pause to wait for order to fill
    time.sleep(poll_sleep_seconds)
    latest = reconcile_order_and_positions(deps, state, order_id)

    # letting agent know, order placed
    follow_up = (
        "We placed an order. Here is the latest order status and current positions.\n"
        f"Order: {latest}\n"
        f"Positions: {state.get('positions', {})}\n\n"
        "What should we do next? (wait / adjust / close / do nothing). "
        "If proposing a new trade, include order + confidence + sources."
    )

    run2 = agent.run_sync(follow_up, deps=deps)
    print(run2.output.model_dump_json(indent=2))
