import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


def _require_env(name: str) -> str:
    val = os.environ.get(name)
    if not val:
        raise RuntimeError(f"Missing env var: {name}")
    return val


@dataclass(frozen=True)
class AlpacaConfig:
    base_url: str
    key: str
    secret: str


def load_config() -> AlpacaConfig:
    return AlpacaConfig(
        base_url=_require_env("ALPACA_URL").rstrip("/"),
        key=_require_env("ALPACA_KEY"),
        secret=_require_env("ALPACA_SECRET"),
    )


def auth_headers(cfg: AlpacaConfig) -> dict[str, str]:
    return {
        "Apca-Api-Key-Id": cfg.key,
        "Apca-Api-Secret-Key": cfg.secret,
        "Content-Type": "application/json",
    }
