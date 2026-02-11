"""Alpaca SDK client factory with paper/live toggle."""

from __future__ import annotations

import os

from dotenv import load_dotenv

from alpaca.trading.client import TradingClient

load_dotenv()


def _require_env(name: str) -> str:
    val = os.environ.get(name)
    if not val:
        raise RuntimeError(f"Missing env var: {name}")
    return val


def create_trading_client(
    trading_mode: str | None = None,
) -> TradingClient:
    """Create an Alpaca TradingClient.

    Args:
        trading_mode: "paper" or "live". Defaults to TRADING_MODE env var or "paper".
    """
    mode = (trading_mode or os.environ.get("TRADING_MODE", "paper")).lower().strip()
    paper = mode != "live"

    return TradingClient(
        api_key=_require_env("ALPACA_KEY"),
        secret_key=_require_env("ALPACA_SECRET"),
        paper=paper,
    )
