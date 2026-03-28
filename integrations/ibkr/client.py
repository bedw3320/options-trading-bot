"""Interactive Brokers client factory via ib_insync."""

from __future__ import annotations

import os

from dotenv import load_dotenv
from ib_insync import IB

from utils.logging import get_logger

load_dotenv()
log = get_logger(__name__)

_ib: IB | None = None
_conn_params: dict | None = None


def _require_env(name: str) -> str:
    val = os.environ.get(name)
    if not val:
        raise RuntimeError(f"Missing env var: {name}")
    return val


def create_ib_client(trading_mode: str | None = None) -> IB:
    """Create and connect an ib_insync IB client.

    Uses a module-level singleton. IB connections are stateful and
    expensive; IB enforces a max of 32 per account.

    Args:
        trading_mode: "paper" or "live". Defaults to TRADING_MODE env var or "paper".
    """
    global _ib, _conn_params

    mode = (trading_mode or os.environ.get("TRADING_MODE", "paper")).lower().strip()
    host = os.environ.get("IB_GATEWAY_HOST", "127.0.0.1")
    port = int(os.environ.get("IB_GATEWAY_PORT", "4002" if mode == "paper" else "4001"))
    client_id = int(os.environ.get("IB_CLIENT_ID", "1"))

    _conn_params = {"host": host, "port": port, "clientId": client_id}

    if _ib is not None and _ib.isConnected():
        return _ib

    ib = IB()
    log.info("Connecting to IB Gateway at %s:%d (mode=%s, clientId=%d)", host, port, mode, client_id)
    ib.connect(host, port, clientId=client_id)
    log.info("Connected to IB Gateway")

    _ib = ib
    return _ib


def ensure_connected(ib: IB) -> IB:
    """Reconnect if the connection was dropped."""
    if ib.isConnected():
        return ib

    if _conn_params is None:
        raise RuntimeError("IB connection params not set — call create_ib_client first")

    log.warning("IB connection lost, reconnecting...")
    try:
        ib.connect(**_conn_params)
        if not ib.isConnected():
            raise RuntimeError("IB connect() returned but isConnected() is False")
    except Exception as e:
        raise RuntimeError(f"Failed to reconnect to IB Gateway: {e}") from e

    log.info("Reconnected to IB Gateway")
    return ib


def disconnect() -> None:
    """Cleanly disconnect the IB client."""
    global _ib
    if _ib is not None:
        log.info("Disconnecting from IB Gateway")
        _ib.disconnect()
        _ib = None
