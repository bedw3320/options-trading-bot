"""Paper Gateway readiness: connect, identity, no orders.

    uv run python -m core.paper_readiness
"""

from __future__ import annotations

import os
import sys
from collections.abc import Callable
from typing import Any

from dotenv import load_dotenv

from core.identity import AccountIdentity, IdentityError, assert_paper_identity
from integrations.ibkr.client import create_ib_client, disconnect


def check_paper_readiness(
    *,
    ib: Any | None = None,
    connect: Callable[[], Any] | None = None,
    disconnect_fn: Callable[[], None] | None = None,
    expected_account_id: str | None = None,
    trading_mode: str | None = None,
    gateway_port: int | None = None,
) -> tuple[bool, str]:
    """Return (ok, one-line OK/FAIL). Never places an order."""
    mode = (
        trading_mode
        if trading_mode is not None
        else os.environ.get("TRADING_MODE", "paper")
    ).strip().lower() or "paper"
    if mode != "paper":
        return False, f"FAIL paper_readiness TRADING_MODE={mode!r} is not paper"

    created = False
    client = ib
    if client is None:
        try:
            if connect is not None:
                client = connect()
            else:
                client = create_ib_client("paper")
                created = True
        except Exception as exc:
            return False, f"FAIL paper_readiness Gateway down: {exc}"

    try:
        identity: AccountIdentity = assert_paper_identity(
            client,
            expected_account_id=expected_account_id,
            trading_mode=mode,
            gateway_port=gateway_port,
        )
    except IdentityError as exc:
        return False, f"FAIL paper_readiness {exc}"
    finally:
        if created:
            (disconnect_fn or disconnect)()

    return True, (
        f"OK paper_readiness account={identity.account_id} mode={identity.trading_mode}"
    )


def main() -> int:
    load_dotenv()
    ok, line = check_paper_readiness()
    print(line)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
