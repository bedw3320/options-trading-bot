"""Technical indicators via pandas-ta over OHLCV DataFrames."""

from __future__ import annotations

from typing import Any

import pandas as pd
import pandas_ta as ta

from utils.logging import get_logger

log = get_logger(__name__)


def compute_indicator(df: pd.DataFrame, indicator: dict) -> dict[str, Any]:
    """Compute a single technical indicator on an OHLCV DataFrame.

    Args:
        df: DataFrame with columns: open, high, low, close, volume
        indicator: Dict with 'name' and optional params (e.g. {'name': 'RSI', 'period': 14})

    Returns:
        Dict with indicator name and latest value(s).
    """
    name = indicator["name"].upper()
    period = indicator.get("period", 14)

    if df.empty or len(df) < period:
        return {"name": name, "value": None, "error": "Insufficient data"}

    try:
        if name == "RSI":
            result = ta.rsi(df["close"], length=period)
            val = float(result.iloc[-1]) if result is not None and not result.empty else None
            return {"name": f"RSI({period})", "value": round(val, 2) if val else None}

        elif name == "SMA":
            result = ta.sma(df["close"], length=period)
            val = float(result.iloc[-1]) if result is not None and not result.empty else None
            return {"name": f"SMA({period})", "value": round(val, 4) if val else None}

        elif name == "EMA":
            result = ta.ema(df["close"], length=period)
            val = float(result.iloc[-1]) if result is not None and not result.empty else None
            return {"name": f"EMA({period})", "value": round(val, 4) if val else None}

        elif name == "VWAP":
            result = ta.vwap(df["high"], df["low"], df["close"], df["volume"])
            val = float(result.iloc[-1]) if result is not None and not result.empty else None
            return {"name": "VWAP", "value": round(val, 4) if val else None}

        elif name == "MACD":
            result = ta.macd(df["close"])
            if result is not None and not result.empty:
                macd_val = float(result.iloc[-1, 0])
                signal_val = float(result.iloc[-1, 1])
                hist_val = float(result.iloc[-1, 2])
                return {
                    "name": "MACD",
                    "macd": round(macd_val, 4),
                    "signal": round(signal_val, 4),
                    "histogram": round(hist_val, 4),
                }
            return {"name": "MACD", "value": None}

        elif name == "BBANDS" or name == "BOLLINGER":
            result = ta.bbands(df["close"], length=period)
            if result is not None and not result.empty:
                return {
                    "name": f"BBANDS({period})",
                    "lower": round(float(result.iloc[-1, 0]), 4),
                    "mid": round(float(result.iloc[-1, 1]), 4),
                    "upper": round(float(result.iloc[-1, 2]), 4),
                }
            return {"name": f"BBANDS({period})", "value": None}

        elif name == "ATR":
            result = ta.atr(df["high"], df["low"], df["close"], length=period)
            val = float(result.iloc[-1]) if result is not None and not result.empty else None
            return {"name": f"ATR({period})", "value": round(val, 4) if val else None}

        elif name == "VOLUME_RATIO":
            lookback = indicator.get("lookback", 20)
            if len(df) >= lookback:
                avg_vol = df["volume"].iloc[-lookback:].mean()
                current_vol = df["volume"].iloc[-1]
                ratio = current_vol / avg_vol if avg_vol > 0 else 0
                return {
                    "name": f"VOLUME_RATIO({lookback})",
                    "value": round(ratio, 2),
                    "current": current_vol,
                    "average": round(avg_vol, 0),
                }
            return {"name": f"VOLUME_RATIO({lookback})", "value": None}

        else:
            return {"name": name, "value": None, "error": f"Unknown indicator: {name}"}

    except Exception as e:
        log.error("Error computing %s: %s", name, e)
        return {"name": name, "value": None, "error": str(e)}


def compute_all(df: pd.DataFrame, indicators: list[dict]) -> list[dict[str, Any]]:
    """Compute multiple indicators on a DataFrame."""
    return [compute_indicator(df, ind) for ind in indicators]
