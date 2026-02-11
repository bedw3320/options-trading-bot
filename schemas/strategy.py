"""Strategy configuration schema.

Strategies are YAML files that describe trading logic declaratively.
Entry/exit conditions are descriptive strings interpreted by the AI agent,
not executable code. The runner pre-computes referenced data and the agent
applies judgment to the conditions.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class AssetUniverse(BaseModel):
    """Which assets and asset classes the strategy trades."""

    asset_classes: list[Literal["equity", "option", "crypto"]] = Field(
        min_length=1,
        description="Asset classes this strategy trades.",
    )
    tickers: list[str] = Field(
        default_factory=list,
        description="Explicit ticker list. Empty = dynamic universe.",
    )
    filters: list[str] = Field(
        default_factory=list,
        description="Descriptive filters for dynamic universe, e.g. 'S&P 500 components'.",
    )


class Schedule(BaseModel):
    """When the strategy runs."""

    frequency: str = Field(
        description="How often to evaluate, e.g. 'every 5 minutes', 'hourly', 'daily at market open'.",
    )
    active_sessions: list[str] = Field(
        default_factory=lambda: ["market_hours"],
        description="When to run: 'market_hours', 'extended_hours', '24/7', 'pre_market', 'post_market'.",
    )
    timezone: str = Field(
        default="US/Eastern",
        description="Timezone for schedule interpretation.",
    )


class DataRequirement(BaseModel):
    """A single data source the strategy needs."""

    source: Literal["ohlcv", "technicals", "news", "social", "options_flow", "web_search"] = Field(
        description="Data source type.",
    )
    params: dict = Field(
        default_factory=dict,
        description="Source-specific parameters (e.g. indicators, timeframes, keywords).",
    )


class Condition(BaseModel):
    """A descriptive condition for entry/exit.

    These are natural language strings the AI agent interprets,
    not executable code. Referenced indicators (RSI, volume, etc.)
    are pre-computed and provided as context.
    """

    description: str = Field(
        description="Natural language condition, e.g. 'RSI(14) crosses above 30 and volume > 2x 20-day average'.",
    )
    priority: int = Field(
        default=1,
        ge=1,
        le=10,
        description="Priority weight 1-10 (10 = must-have, 1 = nice-to-have).",
    )


class EntryRules(BaseModel):
    """Conditions for opening a position."""

    conditions: list[Condition] = Field(min_length=1)
    min_conditions_met: int = Field(
        default=1,
        ge=1,
        description="Minimum number of conditions that should be met to consider entry.",
    )
    position_type: Literal["long", "short", "both"] = Field(default="long")


class ExitRules(BaseModel):
    """Conditions for closing a position."""

    conditions: list[Condition] = Field(min_length=1)
    min_conditions_met: int = Field(default=1, ge=1)


class RiskParams(BaseModel):
    """Risk management parameters."""

    max_position_pct: float = Field(
        default=5.0,
        ge=0.1,
        le=100.0,
        description="Max portfolio % per position.",
    )
    max_total_exposure_pct: float = Field(
        default=50.0,
        ge=1.0,
        le=100.0,
        description="Max total portfolio exposure %.",
    )
    stop_loss_pct: float | None = Field(
        default=None,
        ge=0.1,
        le=50.0,
        description="Stop loss % from entry.",
    )
    take_profit_pct: float | None = Field(
        default=None,
        ge=0.1,
        le=500.0,
        description="Take profit % from entry.",
    )
    max_daily_trades: int = Field(
        default=10,
        ge=1,
        description="Maximum trades per day.",
    )
    confidence_threshold: float = Field(
        default=0.75,
        ge=0.0,
        le=1.0,
        description="Minimum agent confidence to execute a trade.",
    )


class StrategyConfig(BaseModel):
    """Top-level strategy configuration.

    This is the Pydantic model that validates strategy YAML files.
    """

    name: str = Field(description="Human-readable strategy name.")
    version: str = Field(default="1.0.0")
    description: str = Field(default="", description="What this strategy does, in plain English.")

    asset_universe: AssetUniverse
    schedule: Schedule
    data_requirements: list[DataRequirement] = Field(min_length=1)
    entry: EntryRules
    exit: ExitRules
    risk: RiskParams = Field(default_factory=RiskParams)
    notes: list[str] = Field(
        default_factory=list,
        description="Free-form notes for the human or the agent.",
    )
