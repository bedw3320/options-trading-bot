"""Tests for the data pipeline modules.

NOTE: Must not run in same process as test_agent.py which mocks sys.modules.
"""

from __future__ import annotations

import sys

# Clean up any MagicMock pollution from test_agent.py
for key in list(sys.modules):
    if key.startswith("integrations") and hasattr(sys.modules[key], "_mock_name"):
        del sys.modules[key]

import pandas as pd
import pytest

from integrations.data.technicals import compute_all, compute_indicator
from schemas.market import MarketSnapshot, TickerSnapshot


@pytest.fixture
def sample_ohlcv():
    """Create a sample OHLCV DataFrame for testing."""
    import numpy as np

    np.random.seed(42)
    n = 60
    close = 100 + np.cumsum(np.random.randn(n) * 0.5)
    return pd.DataFrame({
        "open": close - np.random.rand(n) * 0.5,
        "high": close + np.random.rand(n) * 1.0,
        "low": close - np.random.rand(n) * 1.0,
        "close": close,
        "volume": np.random.randint(1000000, 5000000, n).astype(float),
    })


def test_compute_rsi(sample_ohlcv):
    result = compute_indicator(sample_ohlcv, {"name": "RSI", "period": 14})
    assert result["name"] == "RSI(14)"
    assert result["value"] is not None
    assert 0 <= result["value"] <= 100


def test_compute_sma(sample_ohlcv):
    result = compute_indicator(sample_ohlcv, {"name": "SMA", "period": 20})
    assert result["name"] == "SMA(20)"
    assert result["value"] is not None


def test_compute_ema(sample_ohlcv):
    result = compute_indicator(sample_ohlcv, {"name": "EMA", "period": 12})
    assert result["name"] == "EMA(12)"
    assert result["value"] is not None


def test_compute_macd(sample_ohlcv):
    result = compute_indicator(sample_ohlcv, {"name": "MACD"})
    assert result["name"] == "MACD"
    assert "macd" in result
    assert "signal" in result


def test_compute_bbands(sample_ohlcv):
    result = compute_indicator(sample_ohlcv, {"name": "BBANDS", "period": 20})
    assert "lower" in result
    assert "mid" in result
    assert "upper" in result
    assert result["lower"] < result["mid"] < result["upper"]


def test_compute_atr(sample_ohlcv):
    result = compute_indicator(sample_ohlcv, {"name": "ATR", "period": 14})
    assert result["name"] == "ATR(14)"
    assert result["value"] is not None
    assert result["value"] > 0


def test_compute_volume_ratio(sample_ohlcv):
    result = compute_indicator(sample_ohlcv, {"name": "VOLUME_RATIO", "lookback": 20})
    assert "value" in result
    assert result["value"] is not None
    assert result["value"] > 0


def test_compute_unknown_indicator(sample_ohlcv):
    result = compute_indicator(sample_ohlcv, {"name": "UNKNOWN_IND"})
    assert "error" in result


def test_compute_insufficient_data():
    tiny_df = pd.DataFrame({
        "open": [100.0, 101.0],
        "high": [102.0, 103.0],
        "low": [99.0, 100.0],
        "close": [101.0, 102.0],
        "volume": [1000000.0, 1100000.0],
    })
    result = compute_indicator(tiny_df, {"name": "RSI", "period": 14})
    assert result["value"] is None


def test_compute_all(sample_ohlcv):
    indicators = [
        {"name": "RSI", "period": 14},
        {"name": "SMA", "period": 20},
        {"name": "MACD"},
    ]
    results = compute_all(sample_ohlcv, indicators)
    assert len(results) == 3
    assert results[0]["name"] == "RSI(14)"
    assert results[1]["name"] == "SMA(20)"
    assert results[2]["name"] == "MACD"


def test_ticker_snapshot():
    snap = TickerSnapshot(
        symbol="AAPL",
        latest_close=150.0,
        technicals={"RSI(14)": 55.0},
    )
    assert snap.symbol == "AAPL"
    assert snap.technicals["RSI(14)"] == 55.0


def test_market_snapshot():
    snap = MarketSnapshot(
        tickers={
            "AAPL": TickerSnapshot(symbol="AAPL", latest_close=150.0),
            "TSLA": TickerSnapshot(symbol="TSLA", latest_close=250.0),
        }
    )
    assert len(snap.tickers) == 2
    assert snap.tickers["AAPL"].latest_close == 150.0
