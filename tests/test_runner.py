"""Tests for core/runner.py — runner hardening, risk controls, error handling."""

from __future__ import annotations

import tempfile
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from schemas.output import AgentResult, OrderIntent
from schemas.strategy import StrategyConfig


MINIMAL_STRATEGY = {
    "name": "test-strat",
    "asset_universe": {"asset_classes": ["crypto"], "tickers": ["SOL/USD"]},
    "schedule": {"frequency": "every 5 minutes", "active_sessions": ["24/7"]},
    "data_requirements": [{"source": "ohlcv", "params": {"timeframe": "1H", "bars": 24}}],
    "entry": {"conditions": [{"description": "Price above SMA", "priority": 5}]},
    "exit": {"conditions": [{"description": "Stop loss", "priority": 10}]},
    "risk": {
        "confidence_threshold": 0.75,
        "max_daily_trades": 5,
        "max_position_pct": 10.0,
        "max_total_exposure_pct": 50.0,
    },
}


def _make_strategy(**overrides) -> StrategyConfig:
    data = {**MINIMAL_STRATEGY, **overrides}
    return StrategyConfig.model_validate(data)


def _make_agent_result(**overrides) -> AgentResult:
    defaults = {
        "summary": "Test",
        "rationale": ["reason"],
        "sources": [],
        "confidence": 0.9,
        "order": None,
        "next_action": "wait",
        "sleep_seconds": 60,
        "note": None,
    }
    defaults.update(overrides)
    return AgentResult.model_validate(defaults)


class _FakeRunResult:
    def __init__(self, output: AgentResult):
        self.output = output


@pytest.fixture
def db_path(tmp_path):
    return str(tmp_path / "test.db")


@pytest.fixture
def mock_deps():
    deps = MagicMock()
    deps.allow_trading = True
    deps.tavily = None
    deps.alpaca = MagicMock()
    return deps


# Patches applied to all runner tests
@pytest.fixture(autouse=True)
def _patch_externals(monkeypatch):
    """Patch all external calls so tests never hit real APIs."""
    monkeypatch.setattr("core.runner.alpaca_list_positions", lambda client: [])
    monkeypatch.setattr("core.runner.should_strategy_run", lambda sessions, classes: True)
    monkeypatch.setattr(
        "core.runner._fetch_data_for_strategy",
        lambda strategy, deps, positions: {},
    )
    monkeypatch.setattr(
        "core.runner.build_strategy_prompt",
        lambda strategy, market_state=None: "test prompt",
    )


class TestConfidenceGating:
    def test_low_confidence_skips_trade(self, mock_deps, db_path, monkeypatch):
        out = _make_agent_result(confidence=0.3, next_action="trade")
        monkeypatch.setattr("core.runner.agent.run_sync", lambda *a, **kw: _FakeRunResult(out))

        from core.runner import run_once

        result = run_once(mock_deps, strategy=_make_strategy(), db_path=db_path, state_key="k1")
        assert result >= 15


class TestDailyTradeLimit:
    def test_limit_reached_blocks_trade(self, mock_deps, db_path, monkeypatch):
        order = OrderIntent(symbol="SOL/USD", side="buy", notional=100.0)
        out = _make_agent_result(confidence=0.9, next_action="trade", order=order)
        monkeypatch.setattr("core.runner.agent.run_sync", lambda *a, **kw: _FakeRunResult(out))
        monkeypatch.setattr("core.runner.count_daily_trades", lambda db, key: 5)

        from core.runner import run_once

        result = run_once(mock_deps, strategy=_make_strategy(), db_path=db_path, state_key="k1")
        assert result >= 15


class TestPositionSizeLimit:
    def test_oversized_order_blocked(self, mock_deps, db_path, monkeypatch):
        order = OrderIntent(symbol="SOL/USD", side="buy", notional=5000.0)
        out = _make_agent_result(confidence=0.9, next_action="trade", order=order)
        monkeypatch.setattr("core.runner.agent.run_sync", lambda *a, **kw: _FakeRunResult(out))
        monkeypatch.setattr("core.runner.count_daily_trades", lambda db, key: 0)
        monkeypatch.setattr(
            "core.runner.get_account",
            lambda client: {"equity": "10000"},
        )

        from core.runner import run_once

        # max_position_pct=10% of $10000 = $1000, order is $5000
        result = run_once(mock_deps, strategy=_make_strategy(), db_path=db_path, state_key="k1")
        assert result >= 15


class TestTradingDisabled:
    def test_allow_trading_false_skips(self, mock_deps, db_path, monkeypatch):
        mock_deps.allow_trading = False
        out = _make_agent_result(confidence=0.9, next_action="trade")
        monkeypatch.setattr("core.runner.agent.run_sync", lambda *a, **kw: _FakeRunResult(out))

        from core.runner import run_once

        result = run_once(mock_deps, strategy=_make_strategy(), db_path=db_path, state_key="k1")
        assert result >= 15


class TestErrorHandling:
    def test_agent_exception_returns_gracefully(self, mock_deps, db_path, monkeypatch):
        def raise_error(*a, **kw):
            raise RuntimeError("LLM exploded")

        monkeypatch.setattr("core.runner.agent.run_sync", raise_error)

        from core.runner import MIN_SLEEP_SECONDS, run_once

        result = run_once(mock_deps, strategy=_make_strategy(), db_path=db_path, state_key="k1")
        assert result == MIN_SLEEP_SECONDS

    def test_order_placement_error_returns_gracefully(self, mock_deps, db_path, monkeypatch):
        order = OrderIntent(symbol="SOL/USD", side="buy", notional=100.0)
        out = _make_agent_result(confidence=0.9, next_action="trade", order=order)
        monkeypatch.setattr("core.runner.agent.run_sync", lambda *a, **kw: _FakeRunResult(out))
        monkeypatch.setattr("core.runner.count_daily_trades", lambda db, key: 0)
        monkeypatch.setattr("core.runner.get_account", lambda client: {"equity": "100000"})
        monkeypatch.setattr(
            "core.runner.alpaca_create_order",
            MagicMock(side_effect=RuntimeError("API down")),
        )

        from core.runner import MIN_SLEEP_SECONDS, run_once

        result = run_once(mock_deps, strategy=_make_strategy(), db_path=db_path, state_key="k1")
        assert result == MIN_SLEEP_SECONDS


class TestMarketHoursGate:
    def test_market_closed_returns_early(self, mock_deps, db_path, monkeypatch):
        # Override autouse patch to make market closed
        monkeypatch.setattr("core.runner.should_strategy_run", lambda sessions, classes: False)

        from core.runner import run_once

        result = run_once(mock_deps, strategy=_make_strategy(), db_path=db_path, state_key="k1")
        assert result == 60


class TestTotalExposureLimit:
    def test_exposure_exceeded_blocks_trade(self, mock_deps, db_path, monkeypatch):
        order = OrderIntent(symbol="SOL/USD", side="buy", notional=1000.0)
        out = _make_agent_result(confidence=0.9, next_action="trade", order=order)
        monkeypatch.setattr("core.runner.agent.run_sync", lambda *a, **kw: _FakeRunResult(out))
        monkeypatch.setattr("core.runner.count_daily_trades", lambda db, key: 0)
        monkeypatch.setattr("core.runner.get_account", lambda client: {"equity": "10000"})
        # Current exposure: $4500, limit = 50% of $10000 = $5000, new order = $1000 -> exceeds
        monkeypatch.setattr(
            "core.runner.snapshot_positions",
            lambda deps: {"SOL/USD": {"market_value": "4500"}},
        )

        from core.runner import run_once

        result = run_once(mock_deps, strategy=_make_strategy(), db_path=db_path, state_key="k1")
        assert result >= 15
