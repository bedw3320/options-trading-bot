"""End-to-end tests: strategy load -> prompt build -> validation."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from core.prompt_builder import build_strategy_prompt
from core.strategy_loader import load, load_all
from core.market_hours import is_market_open, is_session_active, should_strategy_run
from schemas.market import MarketSnapshot, TickerSnapshot
from schemas.strategy import StrategyConfig


class TestHypeVolumeOptions:
    """End-to-end tests for the hype-volume-options strategy."""

    def test_loads_and_validates(self):
        strategy = load("strategies/examples/hype-volume-options.yaml")
        assert strategy.name == "hype-volume-options"
        assert strategy.version == "1.0.0"

    def test_asset_universe(self):
        strategy = load("strategies/examples/hype-volume-options.yaml")
        assert "equity" in strategy.asset_universe.asset_classes
        assert "option" in strategy.asset_universe.asset_classes
        assert strategy.asset_universe.tickers == []  # dynamic universe
        assert len(strategy.asset_universe.filters) > 0

    def test_data_requirements(self):
        strategy = load("strategies/examples/hype-volume-options.yaml")
        sources = [d.source for d in strategy.data_requirements]
        assert "social" in sources
        assert "options_flow" in sources
        assert "ohlcv" in sources
        assert "technicals" in sources
        assert "news" in sources
        assert "web_search" in sources

    def test_entry_conditions(self):
        strategy = load("strategies/examples/hype-volume-options.yaml")
        assert len(strategy.entry.conditions) == 5
        assert strategy.entry.min_conditions_met == 3
        assert strategy.entry.position_type == "long"
        # Highest priority should be options volume
        priorities = [c.priority for c in strategy.entry.conditions]
        assert max(priorities) >= 8

    def test_exit_conditions(self):
        strategy = load("strategies/examples/hype-volume-options.yaml")
        assert len(strategy.exit.conditions) >= 5
        assert strategy.exit.min_conditions_met == 1
        # Stop loss and take profit should be priority 10
        p10 = [c for c in strategy.exit.conditions if c.priority == 10]
        assert len(p10) >= 2

    def test_risk_parameters(self):
        strategy = load("strategies/examples/hype-volume-options.yaml")
        assert strategy.risk.max_position_pct == 3.0
        assert strategy.risk.stop_loss_pct == 8.0
        assert strategy.risk.take_profit_pct == 25.0
        assert strategy.risk.confidence_threshold == 0.80
        assert strategy.risk.max_daily_trades == 5

    def test_prompt_generation(self):
        strategy = load("strategies/examples/hype-volume-options.yaml")
        prompt = build_strategy_prompt(strategy)
        assert "hype-volume-options" in prompt
        assert "Social media mention surge" in prompt
        assert "Unusual options volume" in prompt
        assert "confidence" in prompt.lower()
        assert "equity" in prompt
        assert "option" in prompt

    def test_prompt_with_market_state(self):
        strategy = load("strategies/examples/hype-volume-options.yaml")
        state = {
            "positions": {
                "AAPL": {"qty": "5", "side": "long", "unrealized_pl": "150.00"},
            },
            "orders": {
                "ord1": {"status": "filled", "symbol": "AAPL", "side": "buy"},
            },
            "data": {
                "AAPL": {
                    "RSI(14)": 62.5,
                    "VOLUME_RATIO(20)": 2.3,
                    "social_mentions": 45,
                }
            },
        }
        prompt = build_strategy_prompt(strategy, market_state=state)
        assert "AAPL" in prompt
        assert "long" in prompt
        assert "RSI(14)" in prompt


class TestSolMomentum:
    """Verify the ported SOL strategy works end-to-end."""

    def test_loads(self):
        strategy = load("strategies/examples/sol-momentum.yaml")
        assert strategy.name == "sol-momentum"
        assert "crypto" in strategy.asset_universe.asset_classes

    def test_crypto_sessions(self):
        strategy = load("strategies/examples/sol-momentum.yaml")
        assert "24/7" in strategy.schedule.active_sessions


class TestAllStrategies:
    """Verify all example strategies load."""

    def test_load_all_examples(self):
        strategies = load_all("strategies/examples")
        assert len(strategies) >= 2
        names = [s.name for s in strategies]
        assert "sol-momentum" in names
        assert "hype-volume-options" in names

    def test_all_strategies_generate_prompts(self):
        strategies = load_all("strategies/examples")
        for strategy in strategies:
            prompt = build_strategy_prompt(strategy)
            assert strategy.name in prompt
            assert len(prompt) > 100


class TestMarketHours:
    """Test market session awareness."""

    def test_crypto_always_active(self):
        assert is_session_active("24/7", "crypto")
        assert is_session_active("market_hours", "crypto")

    def test_should_strategy_run_crypto(self):
        assert should_strategy_run(["24/7"], ["crypto"])

    def test_is_market_open_returns_bool(self):
        result = is_market_open()
        assert isinstance(result, bool)


class TestSchemaReference:
    """Verify the reference schema loads."""

    def test_schema_yaml_exists(self):
        path = Path("strategies/_schema.yaml")
        assert path.exists()

    def test_schema_yaml_is_valid(self):
        # The reference schema itself should be valid
        import yaml
        with open("strategies/_schema.yaml") as f:
            data = yaml.safe_load(f)
        assert data["name"] == "strategy-name"
        assert "asset_universe" in data
        assert "entry" in data
        assert "exit" in data
        assert "risk" in data
