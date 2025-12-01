from dataclasses import dataclass

from tavily import TavilyClient

from integrations.alpaca.config import AlpacaConfig


@dataclass
class Deps:
    alpaca: AlpacaConfig
    tavily: TavilyClient
    allow_trading: bool = False
