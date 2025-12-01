from typing import Literal

from pydantic import BaseModel, Field


class OrderIntent(BaseModel):
    symbol: str
    side: Literal["buy", "sell", "hold"]
    notional: float | None = Field(default=None, ge=0)
    time_in_force: Literal["gtc", "ioc"] = "ioc"


class AgentResult(BaseModel):
    summary: str
    rationale: list[str] = Field(min_length=1, max_length=8)
    sources: list[str] = Field(default_factory=list, max_length=10)
    confidence: float = Field(ge=0.0, le=1.0)
    order: OrderIntent | None = None
