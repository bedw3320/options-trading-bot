from __future__ import annotations

import time
from typing import Any

from core.agent import agent
from core.prompt_builder import build_strategy_prompt
from integrations.alpaca.orders import create_order as alpaca_create_order
from integrations.alpaca.orders import get_order as alpaca_get_order
from integrations.alpaca.positions import list_positions as alpaca_list_positions
from schemas.deps import Deps
from schemas.strategy import StrategyConfig
from utils.state import append_event, load_state, save_state


def snapshot_positions(deps: Deps) -> dict[str, Any]:
    positions = alpaca_list_positions(deps.alpaca)
    return {
        p["symbol"]: {
            "qty": p.get("qty"),
            "side": p.get("side"),
            "market_value": p.get("market_value"),
            "avg_entry_price": p.get("avg_entry_price"),
            "current_price": p.get("current_price"),
            "unrealized_pl": p.get("unrealized_pl"),
            "unrealized_plpc": p.get("unrealized_plpc"),
        }
        for p in positions
    }


def reconcile_order_and_positions(
    deps: Deps,
    state: dict[str, Any],
    order_id: str,
    *,
    db_path: str,
    state_key: str,
) -> dict[str, Any]:
    order = alpaca_get_order(deps.alpaca, order_id=order_id)

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
    save_state(db_path, state_key, state)

    append_event(
        db_path,
        state_key,
        "order_reconciled",
        {"order_id": order_id, "order": order, "positions": state["positions"]},
    )

    return order


def run_once(
    deps: Deps,
    *,
    strategy: StrategyConfig,
    poll_sleep_seconds: int = 30,
    db_path: str = "state/state.db",
    state_key: str | None = None,
) -> int:
    """Run one evaluation cycle for a strategy.

    Accepts a StrategyConfig instead of a raw prompt string.
    Uses strategy.risk.confidence_threshold for trade gating.
    """
    if state_key is None:
        state_key = strategy.name

    conf_threshold = strategy.risk.confidence_threshold

    # load latest snapshot state
    state = load_state(db_path, state_key)

    # refresh snapshot
    state["positions"] = snapshot_positions(deps)
    state.setdefault("meta", {})
    state["meta"]["last_cycle_ts"] = int(time.time())
    state["meta"]["strategy"] = strategy.name
    save_state(db_path, state_key, state)

    append_event(
        db_path,
        state_key,
        "cycle_start",
        {"positions": state["positions"], "meta": state["meta"]},
    )

    prompt = build_strategy_prompt(strategy, market_state=state)

    run = agent.run_sync(prompt, deps=deps)
    out = run.output

    print(out.model_dump_json(indent=2))

    append_event(
        db_path,
        state_key,
        "agent_output",
        out.model_dump(),
    )

    if not deps.allow_trading:
        return max(int(out.sleep_seconds), 15)

    if out.next_action != "trade":
        return max(int(out.sleep_seconds), 15)

    if out.confidence < conf_threshold:
        print(f"Skipping trade: confidence {out.confidence} < {conf_threshold}")
        return max(int(out.sleep_seconds), 15)

    if not out.order or out.order.side in ("hold",):
        print("Trade requested but order missing/hold -> skipping.")
        return max(int(out.sleep_seconds), 15)

    if out.order.notional is None or out.order.notional <= 0:
        print("Trade requested but notional missing/invalid -> skipping.")
        return max(int(out.sleep_seconds), 15)

    placed = alpaca_create_order(
        deps.alpaca,
        symbol=out.order.symbol,
        notional=float(out.order.notional),
        side=out.order.side,
        time_in_force=out.order.time_in_force,
        order_type="market",
    )

    append_event(db_path, state_key, "order_placed", {"order": placed})

    order_id = placed.get("id")
    if not order_id:
        print("Order placed but no id returned:", placed)
        return max(int(out.sleep_seconds), 15)

    state.setdefault("orders", {})
    state["orders"].setdefault(order_id, {})
    save_state(db_path, state_key, state)

    time.sleep(poll_sleep_seconds)

    latest = reconcile_order_and_positions(
        deps,
        state,
        order_id,
        db_path=db_path,
        state_key=state_key,
    )

    follow_up = f"""We placed an order. Here is the latest order status and current positions.
    Order: {latest}
    Positions: {state.get("positions", {})}
    Decide next_action + sleep_seconds.
    If proposing another trade, include confidence + sources + order.
    """

    run2 = agent.run_sync(follow_up, deps=deps)
    print(run2.output.model_dump_json(indent=2))

    append_event(db_path, state_key, "agent_followup_output", run2.output.model_dump())

    return max(int(run2.output.sleep_seconds), 15)
