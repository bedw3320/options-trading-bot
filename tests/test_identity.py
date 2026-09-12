"""Identity gate: hard abort on mismatch / live. Mock IB only."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from core.identity import (
    IdentityError,
    assert_paper_identity,
    collect_managed_accounts,
    looks_live,
    looks_paper,
)


def _ib(accounts) -> MagicMock:
    ib = MagicMock()
    ib.managedAccounts = MagicMock(return_value=accounts)
    return ib


class TestLooks:
    def test_du_is_paper_not_live(self):
        assert looks_paper("DUT116016")
        assert not looks_live("DUT116016")

    def test_u_is_live(self):
        assert looks_live("U1234567")
        assert not looks_paper("U1234567")


class TestCollectManagedAccounts:
    def test_callable(self):
        assert collect_managed_accounts(_ib(["DUT1", "DUT2"])) == ["DUT1", "DUT2"]

    def test_comma_string(self):
        ib = MagicMock()
        ib.managedAccounts = "DUT1, DUT2"
        assert collect_managed_accounts(ib) == ["DUT1", "DUT2"]


class TestAssertPaperIdentity:
    def test_matching_paper_account(self, monkeypatch):
        monkeypatch.setenv("TRADING_MODE", "paper")
        monkeypatch.setenv("IB_ACCOUNT_ID", "DUT116016")
        monkeypatch.delenv("IB_GATEWAY_PORT", raising=False)
        ident = assert_paper_identity(_ib(["DUT116016"]))
        assert ident.account_id == "DUT116016"
        assert ident.trading_mode == "paper"

    def test_configured_non_du_id_allowed_if_not_live(self, monkeypatch):
        monkeypatch.setenv("TRADING_MODE", "paper")
        monkeypatch.setenv("IB_ACCOUNT_ID", "PAPER1")
        ident = assert_paper_identity(_ib(["PAPER1"]))
        assert ident.account_id == "PAPER1"

    def test_mismatch_aborts(self, monkeypatch):
        monkeypatch.setenv("TRADING_MODE", "paper")
        monkeypatch.setenv("IB_ACCOUNT_ID", "DUT999")
        with pytest.raises(IdentityError, match="not in managedAccounts"):
            assert_paper_identity(_ib(["DUT116016"]))

    def test_live_account_aborts(self, monkeypatch):
        monkeypatch.setenv("TRADING_MODE", "paper")
        monkeypatch.setenv("IB_ACCOUNT_ID", "U1234567")
        with pytest.raises(IdentityError, match="live-looking account"):
            assert_paper_identity(_ib(["U1234567"]))

    def test_live_mode_aborts(self, monkeypatch):
        monkeypatch.setenv("TRADING_MODE", "live")
        monkeypatch.setenv("IB_ACCOUNT_ID", "DUT116016")
        with pytest.raises(IdentityError, match="is not paper"):
            assert_paper_identity(_ib(["DUT116016"]))

    def test_missing_account_id_aborts(self, monkeypatch):
        monkeypatch.setenv("TRADING_MODE", "paper")
        monkeypatch.delenv("IB_ACCOUNT_ID", raising=False)
        with pytest.raises(IdentityError, match="IB_ACCOUNT_ID is not set"):
            assert_paper_identity(_ib(["DUT116016"]))

    def test_empty_managed_accounts_aborts(self, monkeypatch):
        monkeypatch.setenv("TRADING_MODE", "paper")
        monkeypatch.setenv("IB_ACCOUNT_ID", "DUT116016")
        with pytest.raises(IdentityError, match="no managedAccounts"):
            assert_paper_identity(_ib([]))

    def test_live_port_aborts(self, monkeypatch):
        monkeypatch.setenv("TRADING_MODE", "paper")
        monkeypatch.setenv("IB_ACCOUNT_ID", "DUT116016")
        monkeypatch.setenv("IB_GATEWAY_PORT", "4001")
        with pytest.raises(IdentityError, match="live Gateway port"):
            assert_paper_identity(_ib(["DUT116016"]))
