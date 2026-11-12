"""Liquidity / quote-age thresholds for the research screen.

Liquidity numbers default to `strategies/active/spy-defined-risk-rr.yaml`
`rules.structure` (OI >= 500, spread <= 10% of mid, 30-45 DTE, wing $20).
That YAML is as-built defined-risk / superseded as product-in-force
(knowledge/ops/exit-strategy.md). This file does not edit that YAML.
Overrides live in `research/config.yaml` and are PROPOSALS for Will until
he says otherwise.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from core.strategy_loader import load

DEFAULT_STRATEGY = "strategies/active/spy-defined-risk-rr.yaml"
DEFAULT_CONFIG = "research/config.yaml"
# PROPOSAL for Will: live quotes older than this are stale.
DEFAULT_MAX_QUOTE_AGE_SECONDS = 60.0


@dataclass(frozen=True)
class ScreenThresholds:
    min_open_interest: int
    max_spread_pct_of_mid: float
    dte_min: int
    dte_max: int
    dte_target: int
    target_abs_delta: float
    wing_width: float
    strike_step: float
    max_quote_age_seconds: float
    strategy_path: str
    # True: delayed/frozen quotes still emit numbers, tagged diagnostic_only.
    delayed_is_diagnostic_only: bool = True

    def as_dict(self) -> dict[str, Any]:
        return {
            "min_open_interest": self.min_open_interest,
            "max_spread_pct_of_mid": self.max_spread_pct_of_mid,
            "dte_min": self.dte_min,
            "dte_max": self.dte_max,
            "dte_target": self.dte_target,
            "target_abs_delta": self.target_abs_delta,
            "wing_width": self.wing_width,
            "strike_step": self.strike_step,
            "max_quote_age_seconds": self.max_quote_age_seconds,
            "strategy_path": self.strategy_path,
            "delayed_is_diagnostic_only": self.delayed_is_diagnostic_only,
            "note": "PROPOSAL for Will: liquidity numbers inherited from strategy YAML unless overridden",
        }


def _read_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    raw = yaml.safe_load(path.read_text()) or {}
    if not isinstance(raw, dict):
        raise ValueError(f"{path} must be a YAML mapping")
    return raw


def load_thresholds(
    *,
    strategy_path: str | Path | None = None,
    config_path: str | Path | None = None,
) -> ScreenThresholds:
    cfg = _read_yaml(Path(config_path or DEFAULT_CONFIG))
    strat = Path(strategy_path or cfg.get("strategy") or DEFAULT_STRATEGY)
    rules = load(strat).rules
    if rules is None:
        raise ValueError(f"{strat} has no deterministic rules block")
    s, sig = rules.structure, rules.signals

    def pick(key: str, default):
        return default if cfg.get(key) is None else cfg[key]

    return ScreenThresholds(
        min_open_interest=int(pick("min_open_interest", s.min_open_interest)),
        max_spread_pct_of_mid=float(pick("max_spread_pct_of_mid", s.max_spread_pct_of_mid)),
        dte_min=int(pick("dte_min", s.dte_min)),
        dte_max=int(pick("dte_max", s.dte_max)),
        dte_target=int(pick("dte_target", s.dte_target)),
        target_abs_delta=float(pick("target_abs_delta", sig.target_abs_delta)),
        wing_width=float(pick("wing_width", s.wing_width)),
        strike_step=float(pick("strike_step", s.strike_step)),
        max_quote_age_seconds=float(pick("max_quote_age_seconds", DEFAULT_MAX_QUOTE_AGE_SECONDS)),
        strategy_path=str(strat),
        delayed_is_diagnostic_only=bool(pick("delayed_is_diagnostic_only", True)),
    )
