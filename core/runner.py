from __future__ import annotations

import time
from typing import Any

from core.agent import agent
from core.market_hours import should_strategy_run
from core.prompt_builder import build_strategy_prompt
from integrations.alpaca.account import get_account
from integrations.alpaca.market_data import get_crypto_bars, get_stock_bars
from integrations.alpaca.orders import create_order as alpaca_create_order
from integrations.alpaca.orders import get_order as alpaca_get_order
from integrations.alpaca.positions import close_position as alpaca_close_position
from integrations.alpaca.positions import list_positions as alpaca_list_positions
from integrations.data.news import aggregate_news
from integrations.data.options_flow import analyze_options_flow
from integrations.data.social import aggregate_social
from integrations.data.technicals import compute_all
from schemas.deps import Deps
from schemas.strategy import StrategyConfig
from utils.logging import get_logger
from utils.state import append_event, count_daily_trades, load_state, save_state

log = get_logger(__name__)

MIN_SLEEP_SECONDS = 15


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


def _fetch_data_for_strategy(
    strategy: StrategyConfig,
    deps: Deps,
    positions: dict[str, Any],
) -> dict[str, Any]:
    """Fetch data from all sources declared in strategy.data_requirements.

    Each source is wrapped in try/except for graceful degradation.
    """
    data: dict[str, Any] = {}
    tickers = strategy.asset_universe.tickers or list(positions.keys())

    for req in strategy.data_requirements:
        source = req.source
        params = req.params

        try:
            if source == "ohlcv":
                timeframe = params.get("timeframe", "1D")
                bars_count = params.get("bars", 60)
                ohlcv = {}
                for ticker in tickers:
                    try:
                        if "crypto" in strategy.asset_universe.asset_classes:
                            ohlcv[ticker] = get_crypto_bars(ticker, timeframe=timeframe, bars=bars_count).to_dict("records")
                        else:
                            ohlcv[ticker] = get_stock_bars(ticker, timeframe=timeframe, bars=bars_count).to_dict("records")
                    except Exception as e:
                        log.warning("OHLCV fetch failed for %s: %s", ticker, e)
                data["ohlcv"] = ohlcv

            elif source == "technicals":
                indicators = params.get("indicators", [])
                technicals = {}
                ohlcv_data = data.get("ohlcv", {})
                for ticker in tickers:
                    try:
                        import pandas as pd

                        bars_list = ohlcv_data.get(ticker, [])
                        if bars_list:
                            df = pd.DataFrame(bars_list)
                            technicals[ticker] = compute_all(df, indicators)
                        else:
                            technicals[ticker] = []
                    except Exception as e:
                        log.warning("Technicals failed for %s: %s", ticker, e)
                data["technicals"] = technicals

            elif source == "news":
                keywords = params.get("keywords")
                max_results = params.get("max_results", 10)
                data["news"] = aggregate_news(deps.tavily, tickers, keywords=keywords, max_results=max_results)

            elif source == "social":
                subreddits = params.get("subreddits")
                data["social"] = aggregate_social(tickers, subreddits=subreddits)

            elif source == "options_flow":
                min_volume_ratio = params.get("min_volume_ratio", 2.0)
                flow = {}
                for ticker in tickers:
                    try:
                        flow[ticker] = analyze_options_flow(deps.alpaca, ticker, min_volume_ratio=min_volume_ratio)
                    except Exception as e:
                        log.warning("Options flow failed for %s: %s", ticker, e)
                data["options_flow"] = flow

        except Exception as e:
            log.warning("Data source '%s' failed: %s", source, e)

    return data


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

    # --- Market hours gate ---
    if not should_strategy_run(strategy.schedule.active_sessions, strategy.asset_universe.asset_classes):
        log.info("Market closed for strategy %s, sleeping", strategy.name)
        return 60

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

    # --- Data pipeline ---
    pipeline_data = _fetch_data_for_strategy(strategy, deps, state["positions"])
    state["data"] = pipeline_data

    prompt = build_strategy_prompt(strategy, market_state=state)

    # --- Agent call with error handling ---
    try:
        run = agent.run_sync(prompt, deps=deps)
        out = run.output
    except Exception as e:
        log.error("Agent run failed: %s", e)
        append_event(db_path, state_key, "agent_error", {"error": str(e)})
        return MIN_SLEEP_SECONDS

    print(out.model_dump_json(indent=2))

    append_event(
        db_path,
        state_key,
        "agent_output",
        out.model_dump(),
    )

    if not deps.allow_trading:
        return max(int(out.sleep_seconds), MIN_SLEEP_SECONDS)

    # --- Handle close_position ---
    if out.next_action == "close_position" and out.order and out.order.symbol:
        try:
            closed = alpaca_close_position(deps.alpaca, symbol_or_asset_id=out.order.symbol)
            append_event(db_path, state_key, "position_closed", {"order": closed})
        except Exception as e:
            log.error("Close position failed for %s: %s", out.order.symbol, e)
            append_event(db_path, state_key, "close_position_error", {"error": str(e)})
        return max(int(out.sleep_seconds), MIN_SLEEP_SECONDS)

    if out.next_action != "trade":
        return max(int(out.sleep_seconds), MIN_SLEEP_SECONDS)

    if out.confidence < conf_threshold:
        print(f"Skipping trade: confidence {out.confidence} < {conf_threshold}")
        return max(int(out.sleep_seconds), MIN_SLEEP_SECONDS)

    if not out.order or out.order.side in ("hold",):
        print("Trade requested but order missing/hold -> skipping.")
        return max(int(out.sleep_seconds), MIN_SLEEP_SECONDS)

    if out.order.notional is None or out.order.notional <= 0:
        print("Trade requested but notional missing/invalid -> skipping.")
        return max(int(out.sleep_seconds), MIN_SLEEP_SECONDS)

    # --- Risk controls ---
    daily_trades = count_daily_trades(db_path, state_key)
    if daily_trades >= strategy.risk.max_daily_trades:
        log.warning("Daily trade limit reached (%d/%d)", daily_trades, strategy.risk.max_daily_trades)
        append_event(db_path, state_key, "risk_blocked", {"reason": "max_daily_trades", "count": daily_trades})
        return max(int(out.sleep_seconds), MIN_SLEEP_SECONDS)

    try:
        account = get_account(deps.alpaca)
        equity = float(account.get("equity") or 0)
    except Exception as e:
        log.error("Failed to fetch account for risk checks: %s", e)
        append_event(db_path, state_key, "risk_blocked", {"reason": "account_fetch_failed", "error": str(e)})
        return MIN_SLEEP_SECONDS

    if equity > 0:
        max_position_notional = equity * (strategy.risk.max_position_pct / 100)
        if out.order.notional > max_position_notional:
            log.warning(
                "Position size $%.2f exceeds limit $%.2f (%.1f%% of $%.2f)",
                out.order.notional, max_position_notional, strategy.risk.max_position_pct, equity,
            )
            append_event(db_path, state_key, "risk_blocked", {
                "reason": "max_position_pct",
                "notional": out.order.notional,
                "limit": max_position_notional,
            })
            return max(int(out.sleep_seconds), MIN_SLEEP_SECONDS)

        current_exposure = sum(
            abs(float(p.get("market_value") or 0))
            for p in state.get("positions", {}).values()
        )
        max_exposure = equity * (strategy.risk.max_total_exposure_pct / 100)
        if current_exposure + out.order.notional > max_exposure:
            log.warning(
                "Total exposure $%.2f + $%.2f exceeds limit $%.2f",
                current_exposure, out.order.notional, max_exposure,
            )
            append_event(db_path, state_key, "risk_blocked", {
                "reason": "max_total_exposure_pct",
                "current_exposure": current_exposure,
                "order_notional": out.order.notional,
                "limit": max_exposure,
            })
            return max(int(out.sleep_seconds), MIN_SLEEP_SECONDS)

    # --- Place order with error handling ---
    try:
        placed = alpaca_create_order(
            deps.alpaca,
            symbol=out.order.symbol,
            notional=float(out.order.notional),
            side=out.order.side,
            time_in_force=out.order.time_in_force,
            order_type="market",
        )
    except Exception as e:
        log.error("Order placement failed: %s", e)
        append_event(db_path, state_key, "order_error", {"error": str(e)})
        return MIN_SLEEP_SECONDS

    append_event(db_path, state_key, "order_placed", {"order": placed})

    order_id = placed.get("id")
    if not order_id:
        print("Order placed but no id returned:", placed)
        return max(int(out.sleep_seconds), MIN_SLEEP_SECONDS)

    state.setdefault("orders", {})
    state["orders"].setdefault(order_id, {})
    save_state(db_path, state_key, state)

    time.sleep(poll_sleep_seconds)

    try:
        latest = reconcile_order_and_positions(
            deps,
            state,
            order_id,
            db_path=db_path,
            state_key=state_key,
        )
    except Exception as e:
        log.error("Order reconciliation failed: %s", e)
        append_event(db_path, state_key, "reconcile_error", {"error": str(e), "order_id": order_id})
        return MIN_SLEEP_SECONDS

    follow_up = f"""We placed an order. Here is the latest order status and current positions.
    Order: {latest}
    Positions: {state.get("positions", {})}
    Decide next_action + sleep_seconds.
    If proposing another trade, include confidence + sources + order.
    """

    try:
        run2 = agent.run_sync(follow_up, deps=deps)
        print(run2.output.model_dump_json(indent=2))
        append_event(db_path, state_key, "agent_followup_output", run2.output.model_dump())
        return max(int(run2.output.sleep_seconds), MIN_SLEEP_SECONDS)
    except Exception as e:
        log.error("Follow-up agent run failed: %s", e)
        append_event(db_path, state_key, "agent_followup_error", {"error": str(e)})
        return MIN_SLEEP_SECONDS
