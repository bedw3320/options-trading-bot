"""Structured decision record (Epic 1 lineage).

Append-only, keyed by cycle_id. Gate names/units are versioned with the
strategy engine (`defined_risk_risk_reversal_v0` + GATE_CATALOG_VERSION).
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

DECISION_SCHEMA_VERSION = "decision_v1"
GATE_CATALOG_VERSION = "gates_v1"

# Paper is the primary case. Records are written in every run mode anyway.
TradingMode = Literal["paper", "live"]
RunMode = Literal["dry_run", "paper"]
DecisionOutcome = Literal["trade", "abstain", "error"]
GateResult = Literal["pass", "fail", "skipped"]
SourceClass = Literal["live", "delayed", "fixture"]


class GateEval(BaseModel):
    """One gate check. Always recorded; never omitted because an earlier gate failed."""

    gate: str
    candidate_id: str | None = None
    value: float | None = None
    operator: str | None = None
    threshold: float | None = None
    unit: str
    result: GateResult
    skip_reason: str | None = None
    margin: float | None = None


class CandidateRecord(BaseModel):
    candidate_id: str
    legs: list[dict[str, Any]] = Field(default_factory=list)
    rank: int | None = None
    chosen: bool = False
    rejected_reason: str | None = None


class InputPoint(BaseModel):
    name: str
    value: float | str | None = None
    unit: str
    source: SourceClass
    age_seconds: float | None = None


class DecisionRecord(BaseModel):
    """One cycle's decision. Not acting (abstain/hold/error) is still a decision."""

    schema_version: str = DECISION_SCHEMA_VERSION
    gate_catalog_version: str = GATE_CATALOG_VERSION
    cycle_id: str
    recorded_at: str
    run_mode: RunMode
    trading_mode: TradingMode
    git_sha: str | None = None
    strategy_name: str
    strategy_version: str
    strategy_sha256: str
    strategy_yaml: str
    outcome: DecisionOutcome
    cycle_outcome: str | None = None
    binding_gate: str | None = None
    phase: str
    ranking: str
    data_trust: str
    derived_reasons: list[str] = Field(default_factory=list)
    inputs: dict[str, Any] = Field(default_factory=dict)
    candidates: list[CandidateRecord] = Field(default_factory=list)
    gates: list[GateEval] = Field(default_factory=list)
    opened_cycle_id: str | None = None
