"""Stock and crypto OHLCV data via ib_insync."""

from __future__ import annotations

import math
from typing import Any

import pandas as pd
from ib_insync import IB, Stock, Crypto

from utils.logging import get_logger

log = get_logger(__name__)

_BAR_SIZE_MAP = {
    "1Min": "1 min",
    "5Min": "5 mins",
    "15Min": "15 mins",
    "1H": "1 hour",
    "4H": "4 hours",
    "1D": "1 day",
    "1W": "1 week",
    "1M": "1 month",
}

# Compute IB durationStr from desired bar count.
# US market: ~6.5 trading hours/day = 390 min. Overshoot for weekends/holidays.
_DURATION_MAP = {
    "1Min": lambda bars: f"{max(1, math.ceil(bars / 390) + 1)} D",
    "5Min": lambda bars: f"{max(1, math.ceil(bars / 78) + 1)} D",
    "15Min": lambda bars: f"{max(1, math.ceil(bars / 26) + 1)} D",
    "1H": lambda bars: f"{max(1, math.ceil(bars / 6.5) + 1)} D",
    "4H": lambda bars: f"{max(1, math.ceil(bars / 1.625) + 1)} D",
    "1D": lambda bars: f"{max(1, bars * 2)} D",
    "1W": lambda bars: f"{max(1, bars * 10)} D",
    "1M": lambda bars: f"{max(1, bars)} M",
}


def _bars_to_df(ib_bars, symbol: str) -> pd.DataFrame:
    """Convert ib_insync BarData list to a pandas DataFrame."""
    if not ib_bars:
        return pd.DataFrame()

    records = []
    for bar in ib_bars:
        records.append({
            "symbol": symbol,
            "timestamp": bar.date,
            "open": float(bar.open),
            "high": float(bar.high),
            "low": float(bar.low),
            "close": float(bar.close),
            "volume": float(bar.volume),
            "vwap": float(bar.average) if hasattr(bar, "average") and bar.average else None,
        })

    df = pd.DataFrame(records)
    if not df.empty:
        df = df.sort_values("timestamp").reset_index(drop=True)
    return df


def get_stock_bars(
    ib: IB,
    symbol: str,
    timeframe: str = "1D",
    bars: int = 60,
) -> pd.DataFrame:
    """Get stock OHLCV bars as a DataFrame."""
    bar_size = _BAR_SIZE_MAP.get(timeframe)
    if bar_size is None:
        raise ValueError(f"Unknown timeframe: {timeframe}. Use: {list(_BAR_SIZE_MAP)}")

    duration = _DURATION_MAP[timeframe](bars)
    contract = Stock(symbol, "SMART", "USD")
    ib.qualifyContracts(contract)

    log.info("Fetching stock bars: %s %s x%d (duration=%s)", symbol, timeframe, bars, duration)
    ib_bars = ib.reqHistoricalData(
        contract,
        endDateTime="",
        durationStr=duration,
        barSizeSetting=bar_size,
        whatToShow="TRADES",
        useRTH=True,
    )

    df = _bars_to_df(ib_bars, symbol)
    if not df.empty:
        df = df.tail(bars).reset_index(drop=True)
    return df


def get_crypto_bars(
    ib: IB,
    symbol: str,
    timeframe: str = "1H",
    bars: int = 48,
) -> pd.DataFrame:
    """Get crypto OHLCV bars as a DataFrame."""
    bar_size = _BAR_SIZE_MAP.get(timeframe)
    if bar_size is None:
        raise ValueError(f"Unknown timeframe: {timeframe}. Use: {list(_BAR_SIZE_MAP)}")

    duration = _DURATION_MAP[timeframe](bars)

    # Parse crypto symbol (e.g., "SOL/USD" -> Crypto("SOL", "PAXOS", "USD"))
    if "/" in symbol:
        parts = symbol.split("/")
        contract = Crypto(parts[0], "PAXOS", parts[1] if len(parts) > 1 else "USD")
    else:
        contract = Crypto(symbol, "PAXOS", "USD")

    ib.qualifyContracts(contract)

    log.info("Fetching crypto bars: %s %s x%d (duration=%s)", symbol, timeframe, bars, duration)
    ib_bars = ib.reqHistoricalData(
        contract,
        endDateTime="",
        durationStr=duration,
        barSizeSetting=bar_size,
        whatToShow="AGGTRADES",
        useRTH=False,
    )

    df = _bars_to_df(ib_bars, symbol)
    if not df.empty:
        df = df.tail(bars).reset_index(drop=True)
    return df


def get_stock_quote(ib: IB, symbol: str) -> dict[str, Any]:
    """Get the latest quote for a stock."""
    contract = Stock(symbol, "SMART", "USD")
    ib.qualifyContracts(contract)

    ticker = ib.reqMktData(contract, snapshot=True)
    ib.sleep(2)
    ib.cancelMktData(contract)

    return {
        "symbol": symbol,
        "ask_price": float(ticker.ask) if ticker.ask and ticker.ask > 0 else None,
        "bid_price": float(ticker.bid) if ticker.bid and ticker.bid > 0 else None,
        "ask_size": float(ticker.askSize) if ticker.askSize else None,
        "bid_size": float(ticker.bidSize) if ticker.bidSize else None,
        "timestamp": None,
    }
