from __future__ import annotations

import httpx

from schemas.alpaca import AlpacaOrderResponse, AlpacaPosition
from utils.logging import get_logger

from .config import AlpacaConfig, auth_headers

log = get_logger(__name__)


def list_positions(cfg: AlpacaConfig) -> list[AlpacaPosition]:
    url = f"{cfg.base_url}/positions"
    log.info("Alpaca list_positions: url=%s", url)

    r = httpx.get(url, headers=auth_headers(cfg), timeout=20.0)
    log.info("Alpaca list_positions: status=%s", r.status_code)

    if r.is_error:
        log.error("Alpaca list_positions error body=%s", r.text)

    r.raise_for_status()
    data = r.json()
    return [AlpacaPosition.model_validate(p) for p in data]


def close_position(
    cfg: AlpacaConfig,
    *,
    symbol_or_asset_id: str,
    qty: float | None = None,
    percentage: float | None = None,
) -> AlpacaOrderResponse:
    if qty is not None and percentage is not None:
        raise ValueError("Provide qty OR percentage, not both.")
    if percentage is not None and not (0 < percentage <= 100):
        raise ValueError("percentage must be in (0, 100].")

    url = f"{cfg.base_url}/positions/{symbol_or_asset_id}"
    params: dict = {}
    if qty is not None:
        params["qty"] = qty
    if percentage is not None:
        params["percentage"] = percentage

    log.info("Alpaca close_position: url=%s params=%s", url, params)

    r = httpx.delete(url, headers=auth_headers(cfg), params=params, timeout=20.0)
    log.info("Alpaca close_position: status=%s", r.status_code)

    if r.is_error:
        log.error("Alpaca close_position error body=%s", r.text)

    r.raise_for_status()
    return AlpacaOrderResponse.model_validate(r.json())
