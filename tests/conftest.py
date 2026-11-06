"""Process isolation for the test suite.

A Mini/developer `.env` may set MARKET_DATA_SOURCE=cboe. Tests must still
pass: dry-run does not inherit that env (see core.cli.resolve_data_source).
We skip dotenv so other secrets/flags in `.env` cannot arm trading.
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _skip_dotenv_and_keep_paper(monkeypatch):
    monkeypatch.setenv("OTB_SKIP_DOTENV", "1")
    monkeypatch.delenv("ALLOW_TRADING", raising=False)
    monkeypatch.setenv("TRADING_MODE", "paper")
