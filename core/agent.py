from __future__ import annotations

from typing import Any, Literal

from pydantic_ai import Agent, RunContext
from pydantic_ai.models.test import TestModel

from core.routing import build_model
from integrations.ibkr.account import get_account as ibkr_get_account
from integrations.ibkr.assets import list_crypto_assets as ibkr_list_crypto_assets
from integrations.ibkr.market_data import get_crypto_bars, get_stock_bars, get_stock_quote
from integrations.ibkr.options_data import get_options_chain as ibkr_get_options_chain
from integrations.ibkr.orders import create_order as ibkr_create_order
from integrations.ibkr.positions import close_position as ibkr_close_position
from integrations.ibkr.positions import list_positions as ibkr_list_positions
from integrations.tavily.search import web_search as tavily_web_search
from schemas.deps import Deps
from schemas.output import AgentResult

agent = Agent(
    TestModel(),
    deps_type=Deps,
    output_type=AgentResult,
    instructions=(
        """You are a multi-asset trading assistant (stocks, options, crypto).
        - Use tools when you need facts (news/price/context, account/positions).
        - Always include real URLs in `sources` when you used `web_search`.
        - Always output `confidence` in [0,1].
        - Always set `next_action` and `sleep_seconds`.
        - If you propose a trade, populate `order`.
        - Only call `create_order` or `close_position` if allow_trading=True.
        - If confidence < threshold, prefer next_action='wait' or 'noop' (no trade).
        - For options trades, include contract_symbol, option_type, strike, and dte in the order."""
    ),
    retries=3,
)


def configure_model(model_spec: str, *, strict: bool = True):
    """Call from main.py at runtime."""
    model = build_model(model_spec, strict=strict)
    if model is not None:
        agent.model = model
    return agent.model


@agent.tool
def web_search(
    ctx: RunContext[Deps],
    query: str,
    topic: Literal["general", "news", "finance"] = "news",
    days: int = 7,
    max_results: int = 5,
) -> dict[str, Any]:
    if ctx.deps.tavily is None:
        return {"error": "Tavily client not configured"}
    return tavily_web_search(
        ctx.deps.tavily,
        query=query,
        topic=topic,
        days=days,
        max_results=max_results,
    )


@agent.tool
def get_account(ctx: RunContext[Deps]) -> dict[str, Any]:
    return ibkr_get_account(ctx.deps.ib)


@agent.tool
def get_crypto_assets(ctx: RunContext[Deps]) -> list[dict[str, Any]]:
    return ibkr_list_crypto_assets(ctx.deps.ib)


@agent.tool
def get_positions(ctx: RunContext[Deps]) -> dict[str, Any]:
    positions = ibkr_list_positions(ctx.deps.ib)
    return {"positions": positions}


@agent.tool
def create_order(
    ctx: RunContext[Deps],
    symbol: str,
    notional: float,
    side: Literal["buy", "sell"],
    time_in_force: Literal["gtc", "ioc", "day"] = "ioc",
    contract_symbol: str | None = None,
) -> dict[str, Any]:
    if not ctx.deps.allow_trading:
        return {"ok": False, "reason": "Trading disabled (allow_trading=False)."}

    result = ibkr_create_order(
        ctx.deps.ib,
        symbol=symbol,
        notional=notional,
        side=side,
        time_in_force=time_in_force,
        order_type="market",
        contract_symbol=contract_symbol,
    )
    return {"ok": True, "order": result}


@agent.tool
def close_position(
    ctx: RunContext[Deps],
    symbol_or_asset_id: str,
    qty: float | None = None,
    percentage: float | None = None,
) -> dict[str, Any]:
    if not ctx.deps.allow_trading:
        return {"ok": False, "reason": "Trading disabled (allow_trading=False)."}

    order = ibkr_close_position(
        ctx.deps.ib,
        symbol_or_asset_id=symbol_or_asset_id,
        qty=qty,
        percentage=percentage,
    )
    return {"ok": True, "order": order}


@agent.tool
def get_stock_data(
    ctx: RunContext[Deps],
    symbol: str,
    timeframe: str = "1D",
    bars: int = 60,
) -> dict[str, Any]:
    """Get stock OHLCV data. Returns summary stats."""
    df = get_stock_bars(ctx.deps.ib, symbol, timeframe=timeframe, bars=bars)
    if df.empty:
        return {"error": f"No data for {symbol}"}
    latest = df.iloc[-1]
    return {
        "symbol": symbol,
        "bars": len(df),
        "latest_close": latest["close"],
        "latest_volume": latest["volume"],
        "high_52w": df["high"].max(),
        "low_52w": df["low"].min(),
        "avg_volume": df["volume"].mean(),
    }


@agent.tool
def get_crypto_data(
    ctx: RunContext[Deps],
    symbol: str,
    timeframe: str = "1H",
    bars: int = 48,
) -> dict[str, Any]:
    """Get crypto OHLCV data. Returns summary stats."""
    df = get_crypto_bars(ctx.deps.ib, symbol, timeframe=timeframe, bars=bars)
    if df.empty:
        return {"error": f"No data for {symbol}"}
    latest = df.iloc[-1]
    return {
        "symbol": symbol,
        "bars": len(df),
        "latest_close": latest["close"],
        "latest_volume": latest["volume"],
        "high": df["high"].max(),
        "low": df["low"].min(),
        "avg_volume": df["volume"].mean(),
    }


@agent.tool
def get_quote(
    ctx: RunContext[Deps],
    symbol: str,
) -> dict[str, Any]:
    """Get the latest quote (bid/ask) for a stock."""
    return get_stock_quote(ctx.deps.ib, symbol)


@agent.tool
def get_options_chain(
    ctx: RunContext[Deps],
    underlying_symbol: str,
    min_dte: int = 0,
    max_dte: int = 45,
    limit: int = 50,
) -> dict[str, Any]:
    """Get options chain for a ticker."""
    contracts = ibkr_get_options_chain(
        ctx.deps.ib,
        underlying_symbol,
        min_dte=min_dte,
        max_dte=max_dte,
        limit=limit,
    )
    return {"underlying": underlying_symbol, "contracts": contracts, "count": len(contracts)}
