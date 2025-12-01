import httpx

from schemas.alpaca import AlpacaAccount
from utils.logging import get_logger

from .config import AlpacaConfig, auth_headers

log = get_logger(__name__)


def get_account(cfg: AlpacaConfig) -> AlpacaAccount:
    url = f"{cfg.base_url}/account"
    log.info("Alpaca get_account: url=%s", url)

    r = httpx.get(url, headers=auth_headers(cfg), timeout=20.0)
    log.info("Alpaca get_account: status=%s", r.status_code)

    if r.is_error:
        log.error("Alpaca get_account error body=%s", r.text)

    r.raise_for_status()
    return AlpacaAccount.model_validate(r.json())
