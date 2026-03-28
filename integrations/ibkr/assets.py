"""Asset listing via ib_insync."""

from __future__ import annotations

from typing import Any

from ib_insync import IB

from utils.logging import get_logger

log = get_logger(__name__)

# IB doesn't have a bulk asset listing API.
# For crypto, we maintain a known list of tradeable pairs on PAXOS.
_IB_CRYPTO_ASSETS = [
    {"symbol": "BTC", "name": "Bitcoin", "exchange": "PAXOS", "currency": "USD"},
    {"symbol": "ETH", "name": "Ethereum", "exchange": "PAXOS", "currency": "USD"},
    {"symbol": "LTC", "name": "Litecoin", "exchange": "PAXOS", "currency": "USD"},
    {"symbol": "BCH", "name": "Bitcoin Cash", "exchange": "PAXOS", "currency": "USD"},
]


def list_assets(
    ib: IB,
    *,
    asset_class: str = "us_equity",
) -> list[dict[str, Any]]:
    """List tradeable assets by class.

    IB doesn't support bulk listing like Alpaca. For equities, this returns
    an empty list — use symbol search instead. For crypto, returns known pairs.
    """
    if asset_class == "crypto":
        return list_crypto_assets(ib)

    log.info("IB list_assets: class=%s (note: IB does not support bulk listing)", asset_class)
    return []


def list_crypto_assets(ib: IB) -> list[dict[str, Any]]:
    """List known tradeable crypto assets on IB."""
    log.info("IB list_crypto_assets")
    return [
        {
            "id": a["symbol"],
            "class": "crypto",
            "exchange": a["exchange"],
            "symbol": a["symbol"],
            "name": a["name"],
            "status": "active",
            "tradable": True,
            "fractionable": True,
        }
        for a in _IB_CRYPTO_ASSETS
    ]
