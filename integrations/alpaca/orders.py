import json
from typing import Literal

import httpx

from schemas.alpaca import AlpacaOrderResponse
from utils.logging import get_logger

from .config import AlpacaConfig, auth_headers

log = get_logger(__name__)


def create_order(
    cfg: AlpacaConfig,
    *,
    symbol: str,
    notional: float,
    side: Literal["buy", "sell"],
    order_type: Literal["market", "limit", "stop_limit"] = "market",
    time_in_force: Literal["gtc", "ioc"] = "ioc",
    limit_price: float | None = None,
    stop_price: float | None = None,
) -> dict:
    if notional <= 0:
        raise ValueError("notional must be > 0")
    if order_type == "limit" and limit_price is None:
        raise ValueError("limit_price is required for limit orders")
    if order_type == "stop_limit" and (stop_price is None or limit_price is None):
        raise ValueError(
            "stop_price and limit_price are required for stop_limit orders"
        )

    payload: dict = {
        "symbol": symbol,
        "notional": notional,
        "side": side,
        "type": order_type,
        "time_in_force": time_in_force,
    }

    if limit_price is not None:
        payload["limit_price"] = limit_price
    if stop_price is not None:
        payload["stop_price"] = stop_price

    url = f"{cfg.base_url}/orders"
    log.info("Alpaca create_order: url=%s payload=%s", url, payload)

    r = httpx.post(url, headers=auth_headers(cfg), json=payload, timeout=20.0)

    log.info("Alpaca create_order: status=%s", r.status_code)
    if r.is_error:
        log.error("Alpaca create_order error body=%s", r.text)

    r.raise_for_status()
    data = r.json()

    log.info(
        "Alpaca create_order: id=%s status=%s filled_qty=%s symbol=%s side=%s notional=%s tif=%s",
        data.get("id"),
        data.get("status"),
        data.get("filled_qty"),
        data.get("symbol"),
        data.get("side"),
        data.get("notional"),
        data.get("time_in_force"),
    )

    log.info(
        "Alpaca create_order output=\n%s",
        json.dumps(data, indent=2, ensure_ascii=False),
    )

    return data


# get individual order
def get_order(cfg: AlpacaConfig, *, order_id: str) -> AlpacaOrderResponse:
    url = f"{cfg.base_url}/orders/{order_id}"
    log.info("Alpaca get_order: url=%s", url)

    r = httpx.get(url, headers=auth_headers(cfg), timeout=20.0)
    log.info("Alpaca get_order: status=%s", r.status_code)

    if r.is_error:
        log.error("Alpaca get_order error body=%s", r.text)

    r.raise_for_status()
    return AlpacaOrderResponse.model_validate(r.json())


# list all orders
def list_orders(
    cfg: AlpacaConfig,
    *,
    status: Literal["open", "closed", "all"] = "open",
    limit: int = 50,
) -> list[AlpacaOrderResponse]:
    url = f"{cfg.base_url}/orders"
    params = {"status": status, "limit": limit}
    log.info("Alpaca list_orders: url=%s params=%s", url, params)

    r = httpx.get(url, headers=auth_headers(cfg), params=params, timeout=20.0)
    log.info("Alpaca list_orders: status=%s", r.status_code)

    if r.is_error:
        log.error("Alpaca list_orders error body=%s", r.text)

    r.raise_for_status()
    data = r.json()
    return [AlpacaOrderResponse.model_validate(o) for o in data]
