"""Watchlist YAML schema.

Not a StrategyConfig. The runner and core/cycle.py do not load this file
(Epic 5). Humans maintain strategies/watchlist.yaml; this model validates the
row schema. Helpers here are for a later runner — do not import them from
core/cycle.py in this slice.

Backward compatible with PR #16 rows: `allowed_direction` is an alias for
`direction`; a string `falsifier` still parses (CI rejects it — structured
{metric, threshold, source, expires} is required in the repo file).
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Direction = Literal["bullish", "bearish"]
Status = Literal["record_only", "active", "demoted"]
SkewSide = Literal["put_rich", "call_rich"]

# v0 shrunk plan (Will): one theme, three record_only candidates. SPY is the
# paper baseline, not a candidate. Encoded here so CI — not memory — enforces it.
MAX_RECORD_ONLY_NAMES = 3
MAX_RECORD_ONLY_THEMES = 1
SPY_TICKER = "SPY"
APPROVED_BY_ALLOWED = frozenset({"will"})
# PROPOSAL for Will: evidence older than this cannot promote a name to active.
EVIDENCE_STALE_AFTER_DAYS = 30
DELTA_CONVENTION = "ib_model_signed"


class Falsifier(BaseModel):
    """Machine-checkable invalidation. A tripped or expired falsifier blocks new entries."""

    model_config = ConfigDict(extra="ignore")

    metric: str = Field(min_length=1)
    threshold: str | float | int
    source: str = Field(min_length=1, description="URL or human ref. Required.")
    expires: date
    tripped: bool = False
    tripped_on: date | None = None
    note: str | None = None


class NameExits(BaseModel):
    """Per-name exit defaults. Numbers are proposals until Will edits them."""

    model_config = ConfigDict(extra="ignore")

    profit_take: float = Field(description="USD take-profit. PROPOSAL if copied from SPY YAML.")
    stop: float = Field(description="USD stop. PROPOSAL if copied from SPY YAML.")
    dte_close: int = Field(default=21, ge=0, description="Close at or below this DTE. Default 21.")
    close_before_blackout: bool = True


class WatchlistName(BaseModel):
    """One name on the shared two-way watchlist."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    ticker: str = Field(min_length=1)
    direction: Direction = Field(
        description="bullish = sell puts (defined-risk); bearish = sell calls (defined-risk)."
    )
    status: Status
    theme: str | None = None
    thesis: str = Field(min_length=1, description="Written by a human; no thesis, no trade.")
    sources: list[str] = Field(default_factory=list)
    falsifier: Falsifier | str | None = Field(
        default=None,
        description="Structured {metric, threshold, source, expires}. A leftover string still parses.",
    )
    events_to_avoid: list[str] = Field(default_factory=list)
    cluster: str | None = Field(default=None, description="Cluster tag, e.g. neocloud, index.")
    exits: NameExits | None = None
    narrative: str | None = Field(
        default=None,
        description="Free-form; ignored by the runner. Not an input to any gate.",
    )

    financing_dependence: str | None = Field(
        default=None,
        description="Debt, capex, refinancing dates; human-written. TBD when unknown.",
    )
    added_by: str = Field(min_length=1)
    added_on: date

    forecast_horizon: str | None = Field(
        default=None,
        description="Pre-registration: evaluation horizon, logged before outcomes. e.g. '12 weeks'.",
    )
    probability: float | None = Field(default=None, ge=0.0, le=1.0)
    registered_at: date | None = None

    approved_by: str | None = Field(
        default=None,
        description="Only Will sets this. CI requires 'will' (case-insensitive) to stay/become active.",
    )
    approved_on: date | None = None
    evidence_as_of: date | None = None

    @field_validator("ticker")
    @classmethod
    def _ticker(cls, v: str) -> str:
        return v.strip().upper()

    @model_validator(mode="before")
    @classmethod
    def _alias_direction(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        data = dict(data)
        if "direction" not in data and data.get("allowed_direction") in ("bullish", "bearish"):
            data["direction"] = data["allowed_direction"]
        return data

    @property
    def allowed_direction(self) -> Direction:
        """PR #13/#16 name. Same as `direction`."""
        return self.direction

    def structured_falsifier(self) -> Falsifier | None:
        return self.falsifier if isinstance(self.falsifier, Falsifier) else None


class Watchlist(BaseModel):
    """Top-level watchlist document (`names:`)."""

    model_config = ConfigDict(extra="ignore")

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


def is_spy(name: WatchlistName) -> bool:
    return name.ticker.upper() == SPY_TICKER


def falsifier_blocks_new_entries(
    name: WatchlistName, *, today: date | None = None
) -> tuple[bool, str | None]:
    """Tripped or expired structured falsifier => no new entries.

    The runner does not call this yet. A leftover string falsifier is not
    machine-checkable; CI forbids strings in the repo file.
    """
    today = today or date.today()
    f = name.structured_falsifier()
    if f is None:
        return False, None
    if f.tripped:
        when = f.tripped_on.isoformat() if f.tripped_on else "unspecified"
        return True, f"falsifier_tripped:{f.metric}:{when}"
    if f.expires < today:
        return True, f"falsifier_expired:{f.expires.isoformat()}"
    return False, None


def thesis_agrees_with_skew(
    direction: Direction, skew_side: SkewSide | None
) -> tuple[bool, str]:
    """Thesis direction and skew direction must agree before a name can be active.

    Skew data is not fetched here (snapshot job / later Epic 5). Callers pass
    `skew_side` once they have it.

    bullish thesis sells puts when puts are rich; bearish sells calls when
    calls are rich. Missing skew cannot promote (fail closed).
    """
    if skew_side is None:
        return False, "skew_unavailable"
    if direction == "bullish" and skew_side == "put_rich":
        return True, "thesis_bullish_agrees_put_rich"
    if direction == "bearish" and skew_side == "call_rich":
        return True, "thesis_bearish_agrees_call_rich"
    return False, f"thesis_{direction}_disagrees_{skew_side}"


def evidence_blocks_promotion(
    name: WatchlistName,
    *,
    today: date | None = None,
    stale_after_days: int = EVIDENCE_STALE_AFTER_DAYS,
) -> tuple[bool, str | None]:
    """Missing or stale evidence blocks promotion to active. SPY is exempt (paper baseline)."""
    today = today or date.today()
    if is_spy(name):
        return False, None
    if len(name.sources) < 1:
        return True, "missing_sources"
    if name.structured_falsifier() is None:
        return True, "missing_structured_falsifier"
    if name.evidence_as_of is None:
        return True, "missing_evidence_as_of"
    age = (today - name.evidence_as_of).days
    if age > stale_after_days:
        return True, f"stale_evidence:{age}d>{stale_after_days}d"
    return False, None


def will_approval(name: WatchlistName) -> tuple[bool, str | None]:
    """Only Will may mark a name active. Date required with the marker."""
    who = (name.approved_by or "").strip().lower()
    if who not in APPROVED_BY_ALLOWED:
        return False, "missing_will_approval"
    if name.approved_on is None:
        return False, "missing_approved_on"
    return True, None


def blocks_new_entries(
    name: WatchlistName, *, today: date | None = None
) -> tuple[bool, str | None]:
    """Runner helper (not wired): no new exposure unless active and falsifier is live."""
    today = today or date.today()
    if name.status != "active":
        return True, f"status_{name.status}"
    blocked, why = falsifier_blocks_new_entries(name, today=today)
    if blocked:
        return True, why
    return False, None


def can_promote_to_active(
    name: WatchlistName,
    *,
    today: date | None = None,
    skew_side: SkewSide | None = None,
    stale_after_days: int = EVIDENCE_STALE_AFTER_DAYS,
) -> tuple[bool, list[str]]:
    """Documented promotion check. Does not mutate YAML. Skew data comes later."""
    today = today or date.today()
    reasons: list[str] = []
    if name.status == "demoted":
        reasons.append("status_demoted")
    blocked, why = evidence_blocks_promotion(name, today=today, stale_after_days=stale_after_days)
    if blocked and why:
        reasons.append(why)
    blocked, why = falsifier_blocks_new_entries(name, today=today)
    if blocked and why:
        reasons.append(why)
    ok, why = thesis_agrees_with_skew(name.direction, skew_side)
    if not ok:
        reasons.append(why)
    ok, why = will_approval(name)
    if not ok and why:
        reasons.append(why)
    return not reasons, reasons


def lint_watchlist(wl: Watchlist, *, today: date | None = None) -> list[str]:
    """CI rules. Failures are strings; empty list means OK.

    - non-SPY entries need sources (>=1)
    - a falsifier, if present, must be structured with threshold, source, expires
    - status=active requires approved_by: will + approved_on (only Will sets this)
    - v0 cap: <=3 record_only names, <=1 theme among them
    - record_only non-SPY names need forecast_horizon + registered_at
    """
    today = today or date.today()
    errors: list[str] = []
    record_only = [n for n in wl.names if n.status == "record_only"]
    if len(record_only) > MAX_RECORD_ONLY_NAMES:
        errors.append(
            f"v0 cap: at most {MAX_RECORD_ONLY_NAMES} record_only names, got {len(record_only)}"
        )
    themes = sorted({(n.theme or "").strip() for n in record_only if (n.theme or "").strip()})
    if len(themes) > MAX_RECORD_ONLY_THEMES:
        errors.append(
            f"v0 cap: at most {MAX_RECORD_ONLY_THEMES} theme among record_only names, got {themes}"
        )
    seen: set[str] = set()
    for n in wl.names:
        if n.ticker in seen:
            errors.append(f"{n.ticker}: duplicate ticker")
        seen.add(n.ticker)
        if not is_spy(n) and len(n.sources) < 1:
            errors.append(f"{n.ticker}: non-SPY entry requires sources (>=1)")
        if n.falsifier is not None and n.structured_falsifier() is None:
            errors.append(
                f"{n.ticker}: falsifier must be structured "
                "(metric, threshold, source, expires) — string form is legacy-only"
            )
        else:
            f = n.structured_falsifier()
            if f is not None:
                if f.threshold == "" or f.threshold is None:
                    errors.append(f"{n.ticker}: falsifier lacks threshold")
                if not str(f.source).strip():
                    errors.append(f"{n.ticker}: falsifier lacks source")
                if f.expires is None:
                    errors.append(f"{n.ticker}: falsifier lacks expires")
        if n.status == "active":
            ok, why = will_approval(n)
            if not ok:
                errors.append(
                    f"{n.ticker}: active requires approved_by: will and approved_on "
                    f"(only Will sets this); {why}"
                )
        if n.status == "record_only" and not is_spy(n):
            if not (n.forecast_horizon or "").strip():
                errors.append(f"{n.ticker}: record_only requires forecast_horizon (pre-registration)")
            if n.registered_at is None:
                errors.append(f"{n.ticker}: record_only requires registered_at (pre-registration)")
        _ = today  # reserved for as-of lints; stale evidence is a promotion helper, not a CI fail
    return errors


def lint_watchlist_file(path: str | Path = "strategies/watchlist.yaml") -> list[str]:
    return lint_watchlist(load_watchlist(path))
