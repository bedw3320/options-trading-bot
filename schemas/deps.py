from __future__ import annotations

from dataclasses import dataclass

from alpaca.trading.client import TradingClient
from tavily import TavilyClient


@dataclass
class Deps:
    alpaca: TradingClient
    tavily: TavilyClient | None = None
    allow_trading: bool = False
