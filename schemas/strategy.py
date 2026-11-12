"""Strategy configuration schema.

Strategies are YAML files that describe trading logic declaratively.
Entry/exit conditions are descriptive strings interpreted by the AI agent,
not executable code. The runner pre-computes referenced data and the agent
applies judgment to the conditions.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator


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
    rules: "DeterministicRules | None" = Field(
        default=None,
        description="Deterministic rules. When set, core/cycle.py decides (no LLM).",
    )


# ---------------------------------------------------------------------------
# Deterministic rules. When present, the deterministic cycle (core/cycle.py)
# decides; no LLM is in the decision path.
#
# In-force engine: standard_risk_reversal_v1 (short put + long call).
# defined_risk_risk_reversal_v0 remains parseable for the historical YAML
# only; the runner refuses to execute it.
# ---------------------------------------------------------------------------

IN_FORCE_ENGINE = "standard_risk_reversal_v1"
HISTORICAL_ENGINE = "defined_risk_risk_reversal_v0"


class UniverseRules(BaseModel):
    """US large-cap universe. Never loaded from strategies/watchlist.yaml."""

    source: Literal["sp500"] = "sp500"
    tickers: list[str] = Field(
        default_factory=list,
        description="Optional explicit overlay. Empty = full source list. Not the theme watchlist.",
    )


class SignalRules(BaseModel):
    """Entry signals. Convention: rr25 = IV(25d call) - IV(25d put), IV as decimals.

    In-force binding signal is rr25 only. Other fields may be computed for
    lineage but are not required unless explicitly flagged.
    """

    target_abs_delta: float = Field(default=0.25, gt=0.0, lt=0.5)
    max_rr25: float = Field(
        default=-0.05,
        le=0.0,
        description="Entry needs rr25 <= this (-0.05 = put wing 5 vol pts richer).",
    )
    min_put_call_iv_ratio: float = Field(default=1.15, ge=1.0)
    require_iv_over_rv: bool = False
    require_event_blackout: bool = False
    require_put_call_iv_ratio: bool = False
    rv_lookback_days: int = Field(default=20, ge=5, le=252)
    skew_percentile_min: float = Field(default=75.0, ge=0.0, le=100.0)
    skew_percentile_required: bool = Field(
        default=False,
        description="Not a binding gate for the locked core.",
    )
    skew_percentile_min_history: int = Field(default=60, ge=10)


class StructureRules(BaseModel):
    """Standard RR: short 25d put + long 25d call, one expiry, 1 lot.

    wing_width / max_net_debit are historical defined-risk fields (optional).
    """

    dte_min: int = Field(default=30, ge=1)
    dte_max: int = Field(default=45, ge=1)
    dte_target: int = Field(default=38, ge=1)
    short_put_delta_min: float = Field(default=0.15, gt=0.0, lt=0.5)
    short_put_delta_max: float = Field(default=0.35, gt=0.0, lt=0.5)
    short_put_delta_target: float = Field(default=0.25, gt=0.0, lt=0.5)
    long_call_delta_min: float = Field(default=0.15, gt=0.0, lt=0.5)
    long_call_delta_max: float = Field(default=0.35, gt=0.0, lt=0.5)
    long_call_delta_target: float = Field(default=0.25, gt=0.0, lt=0.5)
    wing_width: float | None = Field(
        default=None,
        description="Historical defined-risk wing ($). None for standard RR.",
    )
    max_net_debit: float | None = Field(
        default=None,
        description="Historical defined-risk per-share debit cap. None for standard RR.",
    )
    strike_step: float = Field(default=5.0, gt=0.0, description="Only strikes on this grid are quoted.")
    max_spread_pct_of_mid: float = Field(default=10.0, gt=0.0, le=100.0)
    min_open_interest: int = Field(default=500, ge=0)

    @model_validator(mode="after")
    def _check_ranges(self) -> "StructureRules":
        if not (self.dte_min <= self.dte_target <= self.dte_max):
            raise ValueError("dte_min <= dte_target <= dte_max required")
        if not (self.short_put_delta_min <= self.short_put_delta_target <= self.short_put_delta_max):
            raise ValueError("short put delta target outside [min, max]")
        if not (self.long_call_delta_min <= self.long_call_delta_target <= self.long_call_delta_max):
            raise ValueError("long call delta target outside [min, max]")
        if self.wing_width is not None and self.wing_width <= 0:
            raise ValueError("wing_width must be positive when set")
        if self.max_net_debit is not None and self.max_net_debit < 0:
            raise ValueError("max_net_debit must be >= 0 when set")
        return self


class SizingRules(BaseModel):
    contracts: Literal[1] = Field(default=1, description="v0 is one combo, fixed.")
    max_new_opens_per_run: int = Field(default=5, ge=1)
    max_new_opens_per_day: int = Field(default=10, ge=1)
    one_structure_per_name: Literal[True] = True
    max_loss_usd: float | None = Field(
        default=None,
        description="Historical defined-risk cap. None for standard RR (paper account is the cap).",
    )
    max_open_positions: int | None = Field(
        default=None,
        description="None = no outstanding position-count cap.",
    )
    max_entries_per_day: int | None = Field(
        default=None,
        description="Legacy alias; in-force path uses max_new_opens_per_day.",
    )


class DeterministicExitRules(BaseModel):
    """Product-in-force: no automated exits. Close is manual flatten only."""

    automated: bool = Field(
        default=False,
        description="False = hold until manual flatten or expiry. Yellow-zone numbers below are historical.",
    )
    time_stop_dte: int | None = Field(default=None, ge=0)
    underlying_stop_pct_below_short_put: float | None = Field(default=None, ge=0.0, le=20.0)
    take_profit_usd: float | None = Field(default=None, gt=0.0)
    stop_loss_usd: float | None = Field(default=None, gt=0.0)


class KillSwitchRules(BaseModel):
    daily_loss_limit_usd: float | None = Field(
        default=None,
        description="Dropped for the locked core; paper DUT116016 equity/margin is the testing-period cap.",
    )
    max_consecutive_errors: int = Field(default=3, ge=1)
    latch_on_reconcile_drift: Literal[True] = True
    latch_on_identity_failure: Literal[True] = True


class ExecutionRules(BaseModel):
    paper_only: Literal[True] = Field(default=True, description="v0 cannot be armed live.")
    required_account_prefix: Literal["DU"] = "DU"
    order_type: Literal["limit_mid"] = "limit_mid"
    fill_wait_seconds: int = Field(default=30, ge=1, le=600)
    cancel_unfilled: Literal[True] = True
    entry_slots_et: tuple[str, ...] = ("10:00", "15:00")
    entry_slot_grace_minutes: int = Field(default=10, ge=0, le=30)
    entry_timezone: Literal["America/Toronto"] = "America/Toronto"
    entry_window_et: tuple[str, str] | None = Field(
        default=None,
        description="Legacy inclusive range. Ignored when entry_slots_et is set.",
    )
    client_id: int = Field(default=11, ge=0)


class EventRules(BaseModel):
    """Informational unless signals.require_event_blackout (off for the locked core)."""

    dates: list[str] = Field(default_factory=list, description="YYYY-MM-DD")
    block_days_before: int = Field(default=3, ge=0)


class DeterministicRules(BaseModel):
    engine: Literal["standard_risk_reversal_v1", "defined_risk_risk_reversal_v0"]
    underlying: str | None = Field(
        default=None,
        description="Single-name historical strategies. In-force universe replaces this.",
    )
    universe: UniverseRules | None = None
    signals: SignalRules = Field(default_factory=SignalRules)
    structure: StructureRules = Field(default_factory=StructureRules)
    sizing: SizingRules = Field(default_factory=SizingRules)
    exits: DeterministicExitRules = Field(default_factory=DeterministicExitRules)
    kill_switch: KillSwitchRules = Field(default_factory=KillSwitchRules)
    execution: ExecutionRules = Field(default_factory=ExecutionRules)
    events: EventRules = Field(default_factory=EventRules)

    @model_validator(mode="after")
    def _engine_shape(self) -> "DeterministicRules":
        if self.engine == HISTORICAL_ENGINE:
            if not self.underlying:
                raise ValueError("defined-risk engine requires underlying")
            if self.structure.wing_width is None:
                raise ValueError("defined-risk engine requires wing_width")
        if self.engine == IN_FORCE_ENGINE:
            if self.universe is None:
                raise ValueError("standard RR requires universe (sp500); do not load watchlist.yaml")
            if self.structure.wing_width is not None:
                raise ValueError("standard RR has no protective put / wing")
            if self.structure.max_net_debit is not None:
                raise ValueError("standard RR has no net-debit cap")
            if self.exits.automated:
                raise ValueError("standard RR has no automated exits")
            if self.sizing.max_loss_usd is not None:
                raise ValueError("standard RR has no coded max-loss cap")
        return self

    def opens_per_run(self) -> int:
        return self.sizing.max_new_opens_per_run

    def opens_per_day(self) -> int:
        if self.sizing.max_new_opens_per_day:
            return self.sizing.max_new_opens_per_day
        return self.sizing.max_entries_per_day or 10


StrategyConfig.model_rebuild()
