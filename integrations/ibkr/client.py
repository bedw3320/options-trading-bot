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


def create_ib_client(
    trading_mode: str | None = None,
    *,
    client_id: int | None = None,
    readonly: bool = False,
) -> IB:
    """Create and connect an ib_insync IB client.

    Trading connections use a module-level singleton (IB max 32 per account).
    Readonly / explicit client_id connections are not stored as that singleton.

    Args:
        trading_mode: "paper" or "live". Defaults to TRADING_MODE env var or "paper".
        client_id: Override IB_CLIENT_ID (default 1).
        readonly: Connect with readonly=True (data / probe; cannot place).
    """
    global _ib, _conn_params

    mode = (trading_mode or os.environ.get("TRADING_MODE", "paper")).lower().strip()
    host = os.environ.get("IB_GATEWAY_HOST", "127.0.0.1")
    port = int(os.environ.get("IB_GATEWAY_PORT", "4002" if mode == "paper" else "4001"))
    cid = int(os.environ.get("IB_CLIENT_ID", "1") if client_id is None else client_id)

    params = {"host": host, "port": port, "clientId": cid, "readonly": readonly}

    if (
        not readonly
        and _ib is not None
        and _ib.isConnected()
        and _conn_params == params
    ):
        return _ib

    ib = IB()
    log.info(
        "Connecting to IB Gateway at %s:%d (mode=%s, clientId=%d, readonly=%s)",
        host,
        port,
        mode,
        cid,
        readonly,
    )
    ib.connect(host, port, clientId=cid, readonly=readonly)
    log.info("Connected to IB Gateway")
    # TRADING_MODE/port are not identity. Call core.identity.assert_paper_identity
    # before any place path (runner / GuardedBroker / paper_readiness).

    if not readonly and (_ib is None or not _ib.isConnected()):
        _ib = ib
        _conn_params = params
    return ib


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
