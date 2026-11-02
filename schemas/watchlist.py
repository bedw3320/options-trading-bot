"""Watchlist YAML schema.

Not a StrategyConfig. The runner and core/cycle.py do not load this file.
Humans maintain strategies/watchlist.yaml; this model validates the documented
row schema so optional fields (e.g. falsifier) cannot break existing rows.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field


class WatchlistName(BaseModel):
    """One name on the shared two-way watchlist."""

    ticker: str = Field(min_length=1)
    allowed_direction: Literal["bullish", "bearish", "both"]
    thesis: str = Field(min_length=1, description="Written by a human; no thesis, no trade.")
    falsifier: str | None = Field(
        default=None,
        description="Optional. What would prove the thesis wrong. Omit rather than invent.",
    )
    financing_dependence: str = Field(
        description="Debt, capex, refinancing dates; human-written. TBD when unknown.",
    )
    events_to_avoid: list[str] = Field(
        description="Earnings, lockups, secondaries/converts; FOMC for index names.",
    )
    status: Literal["active", "record_only"]
    added_by: str = Field(min_length=1)
    added_on: date


class Watchlist(BaseModel):
    """Top-level watchlist document (`names:`)."""

    names: list[WatchlistName] = Field(min_length=1)


def load_watchlist(path: str | Path = "strategies/watchlist.yaml") -> Watchlist:
    """Load and validate a watchlist YAML file. Not used by the runner."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Watchlist file not found: {path}")
    if path.suffix not in (".yaml", ".yml"):
        raise ValueError(f"Watchlist file must be .yaml or .yml: {path}")

    with open(path) as f:
        raw = yaml.safe_load(f)

    if not isinstance(raw, dict):
        raise ValueError(f"Watchlist file must contain a YAML mapping: {path}")

    return Watchlist.model_validate(raw)
