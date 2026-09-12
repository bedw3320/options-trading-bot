"""Guarded execution boundary: preview → single-use token → revalidate → place."""

from __future__ import annotations

import hashlib
import json
import secrets
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from core.identity import assert_paper_identity
from integrations.ibkr.orders import create_order as ibkr_create_order
from integrations.ibkr.positions import close_position as ibkr_close_position
from schemas.output import OrderIntent

TOKEN_TTL_SECONDS = 60.0


class GuardedReject(Exception):
    """Soft reject: do not place. Distinct from identity hard-abort."""


def _fingerprint(payload: dict[str, Any]) -> str:
    blob = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(blob.encode()).hexdigest()


def _place_payload(intent: OrderIntent) -> dict[str, Any]:
    return {"action": "place", **intent.model_dump(mode="json")}


@dataclass(frozen=True)
class Preview:
    token: str
    expires_at: float
    fingerprint: str


@dataclass
class _Token:
    fingerprint: str
    expires_at: float
    used: bool = False


class GuardedBroker:
    """Single execution fence. Agent tools must not call ibkr_create_order."""

    def __init__(
        self,
        ib: Any,
        *,
        allow_trading: bool,
        place_fn: Callable[[Any, OrderIntent], dict[str, Any]] | None = None,
        close_fn: Callable[..., dict[str, Any]] | None = None,
        token_ttl_seconds: float = TOKEN_TTL_SECONDS,
        now: Callable[[], float] | None = None,
        expected_account_id: str | None = None,
        trading_mode: str | None = None,
        gateway_port: int | None = None,
    ) -> None:
        self._ib = ib
        self.allow_trading = allow_trading
        self._place_fn = place_fn
        self._close_fn = close_fn
        self._ttl = token_ttl_seconds
        self._now = now or time.time
        self._expected_account_id = expected_account_id
        self._trading_mode = trading_mode
        self._gateway_port = gateway_port
        self._tokens: dict[str, _Token] = {}

    def _assert_ready(self) -> None:
        assert_paper_identity(
            self._ib,
            expected_account_id=self._expected_account_id,
            trading_mode=self._trading_mode,
            gateway_port=self._gateway_port,
        )
        if not self.allow_trading:
            raise GuardedReject("Trading disabled (allow_trading=False).")

    def _issue(self, payload: dict[str, Any]) -> Preview:
        fingerprint = _fingerprint(payload)
        token = secrets.token_urlsafe(32)
        expires_at = self._now() + self._ttl
        self._tokens[token] = _Token(fingerprint=fingerprint, expires_at=expires_at)
        return Preview(token=token, expires_at=expires_at, fingerprint=fingerprint)

    def _consume(self, token: str, payload: dict[str, Any]) -> None:
        rec = self._tokens.get(token)
        if rec is None:
            raise GuardedReject("unknown confirmation token")
        if rec.used:
            raise GuardedReject("confirmation token already used")
        if self._now() >= rec.expires_at:
            rec.used = True
            raise GuardedReject("confirmation token expired")
        if rec.fingerprint != _fingerprint(payload):
            rec.used = True
            raise GuardedReject("intent does not match confirmation token")
        rec.used = True

    def preview(self, intent: OrderIntent) -> Preview:
        self._assert_ready()
        if intent.side == "hold":
            raise GuardedReject("hold is not a placeable intent")
        if intent.notional is None or intent.notional <= 0:
            raise GuardedReject("notional missing/invalid")
        return self._issue(_place_payload(intent))

    def confirm(
        self,
        token: str,
        intent: OrderIntent,
        *,
        revalidate: Callable[[OrderIntent], None] | None = None,
    ) -> dict[str, Any]:
        self._consume(token, _place_payload(intent))
        self._assert_ready()
        if revalidate is not None:
            revalidate(intent)
        if self._place_fn is not None:
            return self._place_fn(self._ib, intent)
        if intent.side not in ("buy", "sell") or intent.notional is None:
            raise GuardedReject("intent is not placeable")
        return ibkr_create_order(
            self._ib,
            symbol=intent.symbol,
            notional=float(intent.notional),
            side=intent.side,
            time_in_force=intent.time_in_force,
            order_type="market",
            contract_symbol=intent.contract_symbol,
        )

    def close(
        self,
        symbol: str,
        *,
        qty: float | None = None,
        percentage: float | None = None,
    ) -> dict[str, Any]:
        self._assert_ready()
        payload = {
            "action": "close",
            "symbol": symbol,
            "qty": qty,
            "percentage": percentage,
        }
        preview = self._issue(payload)
        return self.confirm_close(
            preview.token, symbol, qty=qty, percentage=percentage
        )

    def confirm_close(
        self,
        token: str,
        symbol: str,
        *,
        qty: float | None = None,
        percentage: float | None = None,
    ) -> dict[str, Any]:
        payload = {
            "action": "close",
            "symbol": symbol,
            "qty": qty,
            "percentage": percentage,
        }
        self._consume(token, payload)
        self._assert_ready()
        if self._close_fn is not None:
            return self._close_fn(self._ib, symbol, qty, percentage)
        return ibkr_close_position(
            self._ib,
            symbol_or_asset_id=symbol,
            qty=qty,
            percentage=percentage,
        )


def execute_intent(
    ib: Any,
    intent: OrderIntent,
    *,
    allow_trading: bool,
    place_fn: Callable[[Any, OrderIntent], dict[str, Any]] | None = None,
    revalidate: Callable[[OrderIntent], None] | None = None,
    expected_account_id: str | None = None,
    trading_mode: str | None = None,
    gateway_port: int | None = None,
) -> dict[str, Any]:
    broker = GuardedBroker(
        ib,
        allow_trading=allow_trading,
        place_fn=place_fn,
        expected_account_id=expected_account_id,
        trading_mode=trading_mode,
        gateway_port=gateway_port,
    )
    preview = broker.preview(intent)
    return broker.confirm(preview.token, intent, revalidate=revalidate)


def execute_close(
    ib: Any,
    symbol: str,
    *,
    allow_trading: bool,
    qty: float | None = None,
    percentage: float | None = None,
    close_fn: Callable[..., dict[str, Any]] | None = None,
    expected_account_id: str | None = None,
    trading_mode: str | None = None,
    gateway_port: int | None = None,
) -> dict[str, Any]:
    broker = GuardedBroker(
        ib,
        allow_trading=allow_trading,
        close_fn=close_fn,
        expected_account_id=expected_account_id,
        trading_mode=trading_mode,
        gateway_port=gateway_port,
    )
    return broker.close(symbol, qty=qty, percentage=percentage)
