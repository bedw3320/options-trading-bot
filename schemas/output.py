from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class OrderIntent(BaseModel):
    symbol: str
    side: Literal["buy", "sell", "hold"]
    notional: float | None = Field(default=None, ge=0)
    time_in_force: Literal["gtc", "ioc", "day"] = "ioc"
    # Options fields (optional - only used for option orders)
    contract_symbol: str | None = Field(default=None, description="OCC option contract symbol")
    option_type: Literal["call", "put"] | None = None
    strike: float | None = Field(default=None, ge=0)
    dte: int | None = Field(default=None, ge=0, description="Days to expiration")


class AgentResult(BaseModel):
    summary: str
    rationale: list[str] = Field(min_length=1, max_length=8)
    sources: list[str] = Field(default_factory=list, max_length=10)

    confidence: float = Field(ge=0.0, le=1.0)
    order: OrderIntent | None = None

    next_action: Literal["wait", "trade", "close_position", "noop"] = "wait"
    sleep_seconds: int = Field(default=300, ge=15, le=3600)
    note: str | None = None
