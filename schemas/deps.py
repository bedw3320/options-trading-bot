from __future__ import annotations

from dataclasses import dataclass

from ib_insync import IB
from tavily import TavilyClient


@dataclass
class Deps:
    ib: IB
    tavily: TavilyClient | None = None
    allow_trading: bool = False
