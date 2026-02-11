"""Tests for strategy loading, validation, and prompt building."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from core.prompt_builder import build_strategy_prompt
from core.strategy_loader import load, load_all
from schemas.strategy import StrategyConfig


MINIMAL_STRATEGY = {
    "name": "test-strategy",
    "asset_universe": {
        "asset_classes": ["equity"],
        "tickers": ["AAPL"],
    },
    "schedule": {
        "frequency": "every 15 minutes",
    },
    "data_requirements": [
        {"source": "ohlcv", "params": {"timeframe": "1D", "bars": 30}},
    ],
    "entry": {
        "conditions": [
            {"description": "Price is above SMA(20)", "priority": 5},
        ],
    },
    "exit": {
        "conditions": [
            {"description": "Stop loss triggered", "priority": 10},
        ],
    },
}


def test_strategy_config_from_dict():
    config = StrategyConfig.model_validate(MINIMAL_STRATEGY)
    assert config.name == "test-strategy"
    assert config.asset_universe.asset_classes == ["equity"]
    assert config.asset_universe.tickers == ["AAPL"]
    assert len(config.entry.conditions) == 1
    assert len(config.exit.conditions) == 1
    assert config.risk.confidence_threshold == 0.75


def test_strategy_config_defaults():
    config = StrategyConfig.model_validate(MINIMAL_STRATEGY)
    assert config.version == "1.0.0"
    assert config.risk.max_position_pct == 5.0
    assert config.risk.max_daily_trades == 10
    assert config.schedule.timezone == "US/Eastern"
    assert config.entry.position_type == "long"


def test_strategy_config_validation_error():
    bad = {**MINIMAL_STRATEGY, "asset_universe": {"asset_classes": []}}
    with pytest.raises(ValidationError):
        StrategyConfig.model_validate(bad)


def test_load_yaml_file():
    with tempfile.NamedTemporaryFile(suffix=".yaml", mode="w", delete=False) as f:
        yaml.dump(MINIMAL_STRATEGY, f)
        path = f.name

    config = load(path)
    assert config.name == "test-strategy"
    Path(path).unlink()


def test_load_sol_momentum():
    config = load("strategies/examples/sol-momentum.yaml")
    assert config.name == "sol-momentum"
    assert "crypto" in config.asset_universe.asset_classes
    assert config.asset_universe.tickers == ["SOL/USD"]
    assert len(config.data_requirements) == 3
    assert config.risk.stop_loss_pct == 5.0


def test_load_nonexistent_file():
    with pytest.raises(FileNotFoundError):
        load("nonexistent.yaml")


def test_load_bad_extension():
    with tempfile.NamedTemporaryFile(suffix=".txt", mode="w", delete=False) as f:
        f.write("name: test")
        path = f.name
    with pytest.raises(ValueError, match="must be .yaml"):
        load(path)
    Path(path).unlink()


def test_load_all_from_directory():
    strategies = load_all("strategies/examples")
    assert len(strategies) >= 1
    assert any(s.name == "sol-momentum" for s in strategies)


def test_build_strategy_prompt():
    config = StrategyConfig.model_validate(MINIMAL_STRATEGY)
    prompt = build_strategy_prompt(config)
    assert "test-strategy" in prompt
    assert "AAPL" in prompt
    assert "Price is above SMA(20)" in prompt
    assert "Stop loss triggered" in prompt
    assert "confidence" in prompt.lower()


def test_build_strategy_prompt_with_market_state():
    config = StrategyConfig.model_validate(MINIMAL_STRATEGY)
    state = {
        "positions": {"AAPL": {"qty": "10", "side": "long"}},
        "orders": {"order1": {"status": "filled"}},
    }
    prompt = build_strategy_prompt(config, market_state=state)
    assert "AAPL" in prompt
    assert "long" in prompt
    assert "filled" in prompt
