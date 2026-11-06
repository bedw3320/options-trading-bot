"""Quoted chain / screen report types. Pure data; no IB."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

LegRole = Literal["put_25d", "call_25d", "put_wing", "call_wing"]
ScreenResult = Literal["pass", "fail", "diagnostic_only"]


class QuotedLeg(BaseModel):
    model_config = ConfigDict(extra="ignore")

    occ: str
    expiry: str
    right: Literal["C", "P"]
    strike: float
    bid: float | None = None
    ask: float | None = None
    delta: float | None = None
    iv: float | None = None
    open_interest: float | None = None
    volume: float | None = None
    quote_time: datetime | None = None
    market_data_type: int | None = None
    data_source: str = "unknown"
    status: str = "ok"

    @property
    def mid(self) -> float | None:
        if self.bid is None or self.ask is None or self.bid <= 0 or self.ask <= 0:
            return None
        return (self.bid + self.ask) / 2.0


class QuotedChain(BaseModel):
    """One ticker's quoted options for the screen / snapshot. Fixture-friendly."""

    model_config = ConfigDict(extra="ignore")

    ticker: str
    as_of: datetime
    underlying_price: float | None = None
    data_source: str
    market_data_type: int | None = None
    diagnostic_only: bool = False
    skip_reason: str | None = None
    legs: list[QuotedLeg] = Field(default_factory=list)


class LegReport(BaseModel):
    role: LegRole
    found: bool
    occ: str | None = None
    expiry: str | None = None
    strike: float | None = None
    right: str | None = None
    delta: float | None = None
    iv: float | None = None
    bid: float | None = None
    ask: float | None = None
    mid: float | None = None
    spread_abs: float | None = None
    spread_pct: float | None = None
    open_interest: float | None = None
    volume: float | None = None
    quote_age_seconds: float | None = None
    quote_time: datetime | None = None
    data_source: str | None = None
    market_data_type: int | None = None
    passed: bool = False
    reasons: list[str] = Field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class TickerScreen(BaseModel):
    ticker: str
    as_of: datetime
    expiry: str | None = None
    dte: int | None = None
    underlying_price: float | None = None
    data_source: str
    diagnostic_only: bool = False
    result: ScreenResult
    legs: list[LegReport] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)
    thresholds: dict[str, Any] = Field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")
