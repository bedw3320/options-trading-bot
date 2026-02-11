"""Asset listing via alpaca-py SDK."""

from __future__ import annotations

from typing import Any

from alpaca.trading.client import TradingClient
from alpaca.trading.enums import AssetClass
from alpaca.trading.requests import GetAssetsRequest

from utils.logging import get_logger

log = get_logger(__name__)


def list_assets(
    client: TradingClient,
    *,
    asset_class: str = "us_equity",
) -> list[dict[str, Any]]:
    """List tradeable assets by class."""
    class_map = {
        "us_equity": AssetClass.US_EQUITY,
        "crypto": AssetClass.CRYPTO,
    }
    cls = class_map.get(asset_class)
    if cls is None:
        raise ValueError(f"Unknown asset class: {asset_class}. Use: {list(class_map)}")

    req = GetAssetsRequest(asset_class=cls)
    log.info("Alpaca list_assets: class=%s", asset_class)
    assets = client.get_all_assets(req)

    result = [
        {
            "id": str(a.id),
            "class": str(a.asset_class) if a.asset_class else None,
            "exchange": str(a.exchange) if a.exchange else None,
            "symbol": a.symbol,
            "name": a.name,
            "status": str(a.status) if a.status else None,
            "tradable": a.tradable,
            "fractionable": a.fractionable,
        }
        for a in assets
        if a.tradable
    ]
    log.info("Alpaca list_assets: found %d tradeable", len(result))
    return result


def list_crypto_assets(client: TradingClient) -> list[dict[str, Any]]:
    """List tradeable crypto assets."""
    return list_assets(client, asset_class="crypto")
