"""paper_readiness entrypoint. Mock IB; no network."""

from __future__ import annotations

from unittest.mock import MagicMock

from core.paper_readiness import check_paper_readiness


def _ib(accounts: list[str]) -> MagicMock:
    ib = MagicMock()
    ib.managedAccounts = MagicMock(return_value=accounts)
    return ib


def test_ok_one_liner(monkeypatch):
    monkeypatch.setenv("TRADING_MODE", "paper")
    monkeypatch.setenv("IB_ACCOUNT_ID", "DUT116016")
    monkeypatch.delenv("IB_GATEWAY_PORT", raising=False)
    ok, line = check_paper_readiness(ib=_ib(["DUT116016"]))
    assert ok is True
    assert line == "OK paper_readiness account=DUT116016 mode=paper"


def test_fail_gateway_down():
    def boom():
        raise ConnectionRefusedError("Connection refused")

    ok, line = check_paper_readiness(connect=boom, trading_mode="paper")
    assert ok is False
    assert line.startswith("FAIL paper_readiness Gateway down:")
    assert "Connection refused" in line


def test_fail_live_mode(monkeypatch):
    monkeypatch.setenv("TRADING_MODE", "live")
    ok, line = check_paper_readiness(ib=_ib(["DUT116016"]), trading_mode="live")
    assert ok is False
    assert line.startswith("FAIL paper_readiness")
    assert "is not paper" in line


def test_fail_live_account(monkeypatch):
    monkeypatch.setenv("TRADING_MODE", "paper")
    monkeypatch.setenv("IB_ACCOUNT_ID", "U1234567")
    ok, line = check_paper_readiness(ib=_ib(["U1234567"]))
    assert ok is False
    assert "live-looking account" in line
