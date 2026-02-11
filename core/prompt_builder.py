"""Build agent prompts from strategy config + market state."""

from __future__ import annotations

from typing import Any

from schemas.strategy import StrategyConfig


def build_strategy_prompt(strategy: StrategyConfig, market_state: dict[str, Any] | None = None) -> str:
    """Turn a StrategyConfig + market snapshot into an agent prompt."""
    sections = [
        f"# Strategy: {strategy.name}",
        f"Description: {strategy.description}" if strategy.description else None,
        "",
        "## Asset Universe",
        f"Asset classes: {', '.join(strategy.asset_universe.asset_classes)}",
    ]

    if strategy.asset_universe.tickers:
        sections.append(f"Tickers: {', '.join(strategy.asset_universe.tickers)}")
    if strategy.asset_universe.filters:
        sections.append(f"Universe filters: {'; '.join(strategy.asset_universe.filters)}")

    sections.extend([
        "",
        "## Entry Conditions",
        f"Position type: {strategy.entry.position_type}",
        f"Minimum conditions to meet: {strategy.entry.min_conditions_met} of {len(strategy.entry.conditions)}",
    ])
    for i, cond in enumerate(strategy.entry.conditions, 1):
        sections.append(f"  {i}. [priority={cond.priority}] {cond.description}")

    sections.extend([
        "",
        "## Exit Conditions",
        f"Minimum conditions to meet: {strategy.exit.min_conditions_met} of {len(strategy.exit.conditions)}",
    ])
    for i, cond in enumerate(strategy.exit.conditions, 1):
        sections.append(f"  {i}. [priority={cond.priority}] {cond.description}")

    sections.extend([
        "",
        "## Risk Parameters",
        f"Max position size: {strategy.risk.max_position_pct}% of portfolio",
        f"Max total exposure: {strategy.risk.max_total_exposure_pct}%",
        f"Confidence threshold: {strategy.risk.confidence_threshold}",
        f"Max daily trades: {strategy.risk.max_daily_trades}",
    ])
    if strategy.risk.stop_loss_pct:
        sections.append(f"Stop loss: {strategy.risk.stop_loss_pct}%")
    if strategy.risk.take_profit_pct:
        sections.append(f"Take profit: {strategy.risk.take_profit_pct}%")

    if strategy.notes:
        sections.extend(["", "## Notes"])
        for note in strategy.notes:
            sections.append(f"- {note}")

    if market_state:
        sections.extend(["", "## Current Market State"])
        positions = market_state.get("positions", {})
        if positions:
            sections.append(f"Open positions: {positions}")
        else:
            sections.append("No open positions.")

        recent_orders = list((market_state.get("orders", {}) or {}).items())[-5:]
        if recent_orders:
            sections.append(f"Recent orders (last 5): {recent_orders}")

        if "data" in market_state:
            sections.append(f"Pre-computed data: {market_state['data']}")

    sections.extend([
        "",
        "## Instructions",
        "Evaluate the current market conditions against the entry/exit rules above.",
        "Return a decision with next_action + sleep_seconds.",
        "Only propose a trade if confidence >= the threshold above.",
        "If you propose a trade, populate the order field with symbol, side, and notional amount.",
    ])

    return "\n".join(s for s in sections if s is not None)
