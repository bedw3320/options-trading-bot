"""Golden-fixture liquidity screen. No Gateway."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from integrations.ibkr.option_quotes import is_delayed_market_data, market_data_source_label
from research.config import load_thresholds
from research.liquidity import screen_chain
from research.models import QuotedChain
from research.screen import main as screen_main

FIX = Path("tests/fixtures/research")


def _chain(name: str) -> QuotedChain:
    return QuotedChain.model_validate(json.loads((FIX / name).read_text()))


def _th():
    return load_thresholds()


def _by_role(screen):
    return {leg.role: leg for leg in screen.legs}


def test_ib_market_data_type_labels():
    assert market_data_source_label(1) == "ib_live"
    assert market_data_source_label(3) == "ib_delayed"
    assert market_data_source_label(4) == "ib_delayed_frozen"
    assert is_delayed_market_data(3) and not is_delayed_market_data(1)


def test_thresholds_inherit_strategy_yaml_oi_and_spread():
    th = _th()
    assert th.min_open_interest == 500
    assert th.max_spread_pct_of_mid == 10
    assert th.dte_min == 30 and th.dte_max == 45
    assert th.wing_width == 20


def test_liquid_chain_passes_all_four_legs():
    s = screen_chain(_chain("liquid_chain.json"), _th())
    assert s.result == "pass"
    assert s.diagnostic_only is False
    assert s.data_source == "ib_live"
    assert s.expiry == "20261218" and s.dte == 42
    by = _by_role(s)
    assert by["put_25d"].strike == 650 and by["put_25d"].passed
    assert by["call_25d"].strike == 690 and by["call_25d"].passed
    assert by["put_wing"].strike == 630 and by["put_wing"].passed
    assert by["call_wing"].strike == 710 and by["call_wing"].passed
    assert by["put_25d"].open_interest == 8000
    assert by["put_25d"].volume == 1200
    assert by["put_25d"].spread_abs == pytest.approx(0.2)
    assert by["put_25d"].data_source == "ib_live"


def test_illiquid_wing_fails_oi():
    s = screen_chain(_chain("illiquid_wing.json"), _th())
    assert s.result == "fail"
    wing = _by_role(s)["put_wing"]
    assert wing.found and not wing.passed
    assert any("OI 50 < 500" in r for r in wing.reasons)


def test_missing_wing_strike():
    s = screen_chain(_chain("missing_wing.json"), _th())
    assert s.result == "fail"
    by = _by_role(s)
    assert by["put_wing"].found is False
    assert "missing_wing_strike" in by["put_wing"].reasons
    assert by["call_wing"].found is False
    assert "missing_wing_strike" in by["call_wing"].reasons


def test_crossed_and_stale_quotes():
    s = screen_chain(_chain("crossed_stale.json"), _th())
    assert s.result == "fail"
    by = _by_role(s)
    assert "crossed_quote" in by["put_25d"].reasons
    assert any(r.startswith("stale_quote") for r in by["call_25d"].reasons)


def test_missing_greeks():
    s = screen_chain(_chain("missing_greeks.json"), _th())
    assert s.result == "fail"
    by = _by_role(s)
    assert by["put_25d"].found is False
    assert "missing_greeks" in by["put_25d"].reasons
    assert by["call_25d"].found is False


def test_delayed_chain_is_diagnostic_only():
    s = screen_chain(_chain("delayed_chain.json"), _th())
    assert s.result == "diagnostic_only"
    assert s.diagnostic_only is True
    assert s.data_source == "ib_delayed"
    assert _by_role(s)["put_25d"].passed  # numbers still reported


def test_screen_cli_writes_json_and_md(tmp_path):
    out = tmp_path / "screens"
    rc = screen_main([
        "--fixture", str(FIX / "liquid_chain.json"),
        "--output-dir", str(out),
    ])
    assert rc == 0
    json_path = out / "2026-11-06.json"
    md_path = out / "2026-11-06.md"
    assert json_path.exists() and md_path.exists()
    blob = json.loads(json_path.read_text())
    assert blob["tickers"][0]["result"] == "pass"
    assert blob["tickers"][0]["data_source"] == "ib_live"
    md = md_path.read_text()
    assert "put_25d" in md and "ib_live" in md and "pass" in md
