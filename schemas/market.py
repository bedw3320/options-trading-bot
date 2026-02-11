"""Market data models."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class TickerSnapshot(BaseModel):
    """Snapshot of all available data for a single ticker."""

    symbol: str
    asset_class: str = "equity"

    # OHLCV summary
    latest_close: float | None = None
    latest_volume: float | None = None
    avg_volume: float | None = None
    high: float | None = None
    low: float | None = None

    # Technicals
    technicals: dict[str, Any] = Field(default_factory=dict)

    # News/sentiment
    news_summary: list[str] = Field(default_factory=list)
    sentiment_score: float | None = None

    # Social signals
    social_mentions: int | None = None
    social_sentiment: float | None = None

    # Options flow
    options_volume_ratio: float | None = None
    put_call_ratio: float | None = None


class MarketSnapshot(BaseModel):
    """Aggregated market data for a strategy evaluation cycle."""

    tickers: dict[str, TickerSnapshot] = Field(default_factory=dict)
    timestamp: str | None = None
    notes: list[str] = Field(default_factory=list)
