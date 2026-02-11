"""Load and validate strategy YAML files."""

from __future__ import annotations

from pathlib import Path

import yaml

from schemas.strategy import StrategyConfig


def load(path: str | Path) -> StrategyConfig:
    """Load a strategy YAML file and return a validated StrategyConfig."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Strategy file not found: {path}")
    if path.suffix not in (".yaml", ".yml"):
        raise ValueError(f"Strategy file must be .yaml or .yml: {path}")

    with open(path) as f:
        raw = yaml.safe_load(f)

    if not isinstance(raw, dict):
        raise ValueError(f"Strategy file must contain a YAML mapping: {path}")

    return StrategyConfig.model_validate(raw)


def load_all(directory: str | Path) -> list[StrategyConfig]:
    """Load all strategy YAML files from a directory."""
    directory = Path(directory)
    strategies = []
    for path in sorted(directory.glob("*.yaml")) + sorted(directory.glob("*.yml")):
        strategies.append(load(path))
    return strategies
