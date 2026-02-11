"""Stock and crypto OHLCV data via alpaca-py SDK."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any

import pandas as pd
from alpaca.data.historical import CryptoHistoricalDataClient, StockHistoricalDataClient
from alpaca.data.requests import CryptoBarsRequest, StockBarsRequest, StockLatestQuoteRequest
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit
from dotenv import load_dotenv

from utils.logging import get_logger

load_dotenv()
log = get_logger(__name__)

_TIMEFRAME_MAP = {
    "1Min": TimeFrame(1, TimeFrameUnit.Minute),
    "5Min": TimeFrame(5, TimeFrameUnit.Minute),
    "15Min": TimeFrame(15, TimeFrameUnit.Minute),
    "1H": TimeFrame(1, TimeFrameUnit.Hour),
    "4H": TimeFrame(4, TimeFrameUnit.Hour),
    "1D": TimeFrame(1, TimeFrameUnit.Day),
    "1W": TimeFrame(1, TimeFrameUnit.Week),
    "1M": TimeFrame(1, TimeFrameUnit.Month),
}


def _get_stock_client() -> StockHistoricalDataClient:
    return StockHistoricalDataClient(
        api_key=os.environ.get("ALPACA_KEY"),
        secret_key=os.environ.get("ALPACA_SECRET"),
    )


def _get_crypto_client() -> CryptoHistoricalDataClient:
    return CryptoHistoricalDataClient()


def _bars_to_df(bars: Any) -> pd.DataFrame:
    """Convert alpaca bar set to a pandas DataFrame."""
    records = []
    for symbol, bar_list in bars.items():
        for bar in bar_list:
            records.append({
                "symbol": symbol,
                "timestamp": bar.timestamp,
                "open": float(bar.open),
                "high": float(bar.high),
                "low": float(bar.low),
                "close": float(bar.close),
                "volume": float(bar.volume),
                "vwap": float(bar.vwap) if bar.vwap else None,
            })
    df = pd.DataFrame(records)
    if not df.empty:
        df = df.sort_values("timestamp").reset_index(drop=True)
    return df


def get_stock_bars(
    symbol: str,
    timeframe: str = "1D",
    bars: int = 60,
) -> pd.DataFrame:
    """Get stock OHLCV bars as a DataFrame."""
    tf = _TIMEFRAME_MAP.get(timeframe)
    if tf is None:
        raise ValueError(f"Unknown timeframe: {timeframe}. Use: {list(_TIMEFRAME_MAP)}")

    end = datetime.now(timezone.utc)
    start = end - timedelta(days=bars * 2)  # overshoot to account for non-trading days

    client = _get_stock_client()
    req = StockBarsRequest(
        symbol_or_symbols=symbol,
        timeframe=tf,
        start=start,
        end=end,
        limit=bars,
    )
    log.info("Fetching stock bars: %s %s x%d", symbol, timeframe, bars)
    bar_set = client.get_stock_bars(req)
    return _bars_to_df(bar_set.data)


def get_crypto_bars(
    symbol: str,
    timeframe: str = "1H",
    bars: int = 48,
) -> pd.DataFrame:
    """Get crypto OHLCV bars as a DataFrame."""
    tf = _TIMEFRAME_MAP.get(timeframe)
    if tf is None:
        raise ValueError(f"Unknown timeframe: {timeframe}. Use: {list(_TIMEFRAME_MAP)}")

    end = datetime.now(timezone.utc)
    start = end - timedelta(days=bars * 2)

    client = _get_crypto_client()
    req = CryptoBarsRequest(
        symbol_or_symbols=symbol,
        timeframe=tf,
        start=start,
        end=end,
        limit=bars,
    )
    log.info("Fetching crypto bars: %s %s x%d", symbol, timeframe, bars)
    bar_set = client.get_crypto_bars(req)
    return _bars_to_df(bar_set.data)


def get_stock_quote(symbol: str) -> dict[str, Any]:
    """Get the latest quote for a stock."""
    client = _get_stock_client()
    req = StockLatestQuoteRequest(symbol_or_symbols=symbol)
    quotes = client.get_stock_latest_quote(req)
    quote = quotes.get(symbol)
    if not quote:
        return {}
    return {
        "symbol": symbol,
        "ask_price": float(quote.ask_price) if quote.ask_price else None,
        "bid_price": float(quote.bid_price) if quote.bid_price else None,
        "ask_size": float(quote.ask_size) if quote.ask_size else None,
        "bid_size": float(quote.bid_size) if quote.bid_size else None,
        "timestamp": str(quote.timestamp) if quote.timestamp else None,
    }
