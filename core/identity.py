"""Fail-closed IBKR account identity (LOOP constraint 2)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

LIVE_GATEWAY_PORT = 4001


class IdentityError(RuntimeError):
    """Hard abort: connected account or mode is not the configured paper identity."""


@dataclass(frozen=True)
class AccountIdentity:
    account_id: str
    managed_accounts: tuple[str, ...]
    trading_mode: str


def looks_paper(account_id: str) -> bool:
    """IBKR paper individual accounts are DU*."""
    return account_id.strip().upper().startswith("DU")


def looks_live(account_id: str) -> bool:
    """IBKR live individual accounts are U* (DU* is paper and starts with D)."""
    return account_id.strip().upper().startswith("U")


def collect_managed_accounts(ib: Any) -> list[str]:
    raw = None
    managed = getattr(ib, "managedAccounts", None)
    if callable(managed):
        raw = managed()
    elif managed:
        raw = managed
    if raw is None:
        wrapper = getattr(ib, "wrapper", None)
        raw = getattr(wrapper, "accounts", None) if wrapper is not None else None
    if raw is None:
        return []
    if isinstance(raw, str):
        parts = raw.replace(";", ",").split(",")
        return [part.strip() for part in parts if part.strip()]
    return [str(part).strip() for part in raw if str(part).strip()]


def assert_paper_identity(
    ib: Any,
    *,
    expected_account_id: str | None = None,
    trading_mode: str | None = None,
    gateway_port: int | None = None,
) -> AccountIdentity:
    """Verify Gateway accounts match IB_ACCOUNT_ID and look paper.

    Hard-aborts on live mode, live-looking U* accounts, port 4001, or mismatch.
    A configured id that is not DU* is allowed only if it matches and is not live.
    """
    mode = (
        trading_mode
        if trading_mode is not None
        else os.environ.get("TRADING_MODE", "paper")
    ).strip().lower() or "paper"
    if mode != "paper":
        raise IdentityError(f"TRADING_MODE={mode!r} is not paper; live is not armed")

    expected = (
        expected_account_id
        if expected_account_id is not None
        else os.environ.get("IB_ACCOUNT_ID", "")
    ).strip()
    if not expected:
        raise IdentityError("IB_ACCOUNT_ID is not set")

    port = gateway_port
    if port is None:
        raw_port = os.environ.get("IB_GATEWAY_PORT")
        port = int(raw_port) if raw_port else None
    if port == LIVE_GATEWAY_PORT:
        raise IdentityError(f"paper mode on live Gateway port {LIVE_GATEWAY_PORT}")

    accounts = collect_managed_accounts(ib)
    if not accounts:
        raise IdentityError("no managedAccounts from Gateway")

    live = [account for account in accounts if looks_live(account)]
    if live:
        raise IdentityError(f"live-looking account {live[0]}")

    matched = {account.upper(): account for account in accounts}.get(expected.upper())
    if matched is None:
        raise IdentityError(
            f"IB_ACCOUNT_ID {expected} not in managedAccounts {accounts}"
        )

    return AccountIdentity(
        account_id=matched,
        managed_accounts=tuple(accounts),
        trading_mode=mode,
    )
