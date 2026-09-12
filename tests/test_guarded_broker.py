"""GuardedBroker: token single-use/expiry, trading-disabled reject, identity abort."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from core.guarded_broker import GuardedBroker, GuardedReject, execute_intent
from core.identity import IdentityError
from schemas.output import OrderIntent, TradeIntent


def _ib(accounts: list[str] | None = None) -> MagicMock:
    ib = MagicMock()
    ib.managedAccounts = MagicMock(return_value=accounts or ["DUT116016"])
    return ib


def _broker(**overrides) -> GuardedBroker:
    kwargs = {
        "ib": _ib(),
        "allow_trading": True,
        "expected_account_id": "DUT116016",
        "trading_mode": "paper",
        "place_fn": MagicMock(return_value={"id": "1", "status": "Submitted"}),
        "now": lambda: 1_000.0,
        "token_ttl_seconds": 30.0,
    }
    kwargs.update(overrides)
    return GuardedBroker(**kwargs)


def _intent() -> OrderIntent:
    return OrderIntent(symbol="SOL/USD", side="buy", notional=100.0)


class TestTradeIntentAlias:
    def test_alias_is_order_intent(self):
        assert TradeIntent is OrderIntent


class TestTradingDisabled:
    def test_preview_rejects_when_trading_disabled(self):
        broker = _broker(allow_trading=False)
        with pytest.raises(GuardedReject, match="Trading disabled"):
            broker.preview(_intent())
        broker._place_fn.assert_not_called()

    def test_execute_intent_rejects_when_trading_disabled(self):
        place_fn = MagicMock()
        with pytest.raises(GuardedReject, match="Trading disabled"):
            execute_intent(
                _ib(),
                _intent(),
                allow_trading=False,
                place_fn=place_fn,
                expected_account_id="DUT116016",
                trading_mode="paper",
            )
        place_fn.assert_not_called()


class TestTokenHandshake:
    def test_preview_confirm_places_once(self):
        broker = _broker()
        intent = _intent()
        preview = broker.preview(intent)
        result = broker.confirm(preview.token, intent)
        assert result["id"] == "1"
        broker._place_fn.assert_called_once()

    def test_token_single_use(self):
        broker = _broker()
        intent = _intent()
        preview = broker.preview(intent)
        broker.confirm(preview.token, intent)
        with pytest.raises(GuardedReject, match="already used"):
            broker.confirm(preview.token, intent)
        assert broker._place_fn.call_count == 1

    def test_token_expiry(self):
        clock = {"t": 1_000.0}

        def now() -> float:
            return clock["t"]

        broker = _broker(now=now, token_ttl_seconds=30.0)
        intent = _intent()
        preview = broker.preview(intent)
        clock["t"] = 1_031.0
        with pytest.raises(GuardedReject, match="expired"):
            broker.confirm(preview.token, intent)
        broker._place_fn.assert_not_called()

    def test_intent_mismatch_rejects(self):
        broker = _broker()
        preview = broker.preview(_intent())
        other = OrderIntent(symbol="AAPL", side="buy", notional=100.0)
        with pytest.raises(GuardedReject, match="does not match"):
            broker.confirm(preview.token, other)
        broker._place_fn.assert_not_called()

    def test_revalidate_failure_does_not_place(self):
        broker = _broker()
        intent = _intent()
        preview = broker.preview(intent)

        def boom(_intent: OrderIntent) -> None:
            raise GuardedReject("max_position_pct")

        with pytest.raises(GuardedReject, match="max_position_pct"):
            broker.confirm(preview.token, intent, revalidate=boom)
        broker._place_fn.assert_not_called()


class TestIdentityOnPlace:
    def test_live_account_aborts_before_place(self):
        broker = _broker(ib=_ib(["U1234567"]), expected_account_id="U1234567")
        with pytest.raises(IdentityError, match="live-looking"):
            broker.preview(_intent())
        broker._place_fn.assert_not_called()
