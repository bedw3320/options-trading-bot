import json

import httpx

from utils.logging import get_logger

from .config import AlpacaConfig, auth_headers

log = get_logger(__name__)

_TIMEOUT = 20.0


def list_crypto_assets(cfg: AlpacaConfig) -> list[dict]:
    url = f"{cfg.base_url}/assets"
    params = {"asset_class": "crypto"}

    log.info("Alpaca list_crypto_assets: url=%s params=%s", url, params)

    r = httpx.get(url, headers=auth_headers(cfg), params=params, timeout=_TIMEOUT)

    log.info("Alpaca list_crypto_assets: status=%s", r.status_code)
    if r.is_error:
        log.error("Alpaca list_crypto_assets error body=%s", r.text)

    r.raise_for_status()
    data = r.json()

    if not isinstance(data, list):
        log.error("Alpaca list_crypto_assets: unexpected response type=%s", type(data))
        return []

    sample = [a.get("symbol") for a in data[:5] if isinstance(a, dict)]
    log.info("Alpaca list_crypto_assets: count=%s sample=%s", len(data), sample)

    # Full, non-truncated output (pretty-printed)
    log.info(
        "Alpaca list_crypto_assets output=\n%s",
        json.dumps(data, indent=2, ensure_ascii=False),
    )

    return data
