"""Typed artifacts for the deterministic cycle (Epic 1 lineage)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

SnapshotStatus = Literal["ok", "unavailable"]


class OptionRow(BaseModel):
    """One quoted option. IV and delta are IB model values (delta signed)."""

    occ: str
    con_id: int | None = None
    expiry: str  # YYYYMMDD
    right: Literal["C", "P"]
    strike: float
    bid: float | None = None
    ask: float | None = None
    delta: float | None = None
    iv: float | None = None
    gamma: float | None = None
    vega: float | None = None
    theta: float | None = None
    open_interest: float | None = None
    status: str = "ok"

    @property
    def mid(self) -> float | None:
        if self.bid is None or self.ask is None or self.bid <= 0 or self.ask <= 0:
            return None
        return (self.bid + self.ask) / 2.0


class MarketSnapshot(BaseModel):
    """Everything the decision may use, timestamped. Nothing else is read."""

    as_of: str  # ISO 8601 with offset
    source: str  # "ib" | "cboe_delayed" | "alpaca:..." | "fixture:<path>"
    underlying: str
    status: SnapshotStatus = "ok"
    reason: str | None = None
    errors: list[dict] = Field(default_factory=list)
    underlying_price: float | None = None
    daily_closes: list[float] = Field(default_factory=list)
    expiry: str | None = None  # chosen YYYYMMDD
    options: list[OptionRow] = Field(default_factory=list)
    held_marks: dict[str, float] = Field(
        default_factory=dict, description="OCC -> mid for legs of the open position"
    )


class SignalValue(BaseModel):
    name: str
    value: float | None
    threshold: float | None = None
    passed: bool | None  # None = not evaluated
    required: bool = True
    note: str | None = None


class ComboLeg(BaseModel):
    occ: str
    con_id: int | None = None
    right: Literal["C", "P"]
    strike: float
    expiry: str
    action: Literal["BUY", "SELL"]
    ratio: int = 1
    bid: float | None = None
    ask: float | None = None
    delta: float | None = None


class ComboIntent(BaseModel):
    """Proposed multi-leg order. Not an order: GuardedBroker previews and confirms it."""

    strategy: str
    underlying: str
    purpose: Literal["open", "close"]
    legs: list[ComboLeg] = Field(min_length=1, max_length=4)
    quantity: int = Field(default=1, ge=1, le=1)
    action: Literal["BUY", "SELL"] = "BUY"
    limit_price: float = Field(description="Per-share net debit (>0) or credit (<0) for the combo")
    max_loss_usd: float | None = None
    position_id: str | None = None
    idempotency_key: str


class Decision(BaseModel):
    action: Literal["enter", "exit", "abstain"]
    reasons: list[str] = Field(min_length=1)
    exit_trigger: str | None = None
