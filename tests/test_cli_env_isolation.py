"""CLI dry-run must not inherit a developer's MARKET_DATA_SOURCE.

On the Mini, `.env` sets MARKET_DATA_SOURCE=cboe. Without isolation the four
cycle CLI tests fail (shadow record-only instead of SimBroker fills).
"""

from __future__ import annotations

from core.cli import main as cli_main, resolve_data_source


def test_resolve_data_source_dry_run_ignores_env(monkeypatch):
    monkeypatch.setenv("MARKET_DATA_SOURCE", "cboe")
    assert resolve_data_source(None, dry_run=True) == "ib"
    assert resolve_data_source("cboe", dry_run=True) == "cboe"
    assert resolve_data_source(None, dry_run=False) == "cboe"
    monkeypatch.delenv("MARKET_DATA_SOURCE")
    assert resolve_data_source(None, dry_run=False) == "ib"


def test_cli_dry_run_hostile_market_data_source_does_not_change_results(tmp_path, capsys, monkeypatch):
    """Hostile env var: still enters on fixtures, never shadow-refuses."""
    monkeypatch.setenv("MARKET_DATA_SOURCE", "cboe")
    monkeypatch.setenv("ALLOW_TRADING", "true")
    db = str(tmp_path / "s.db")
    assert cli_main(["--db", db, "run", "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "entered" in out
    assert "proposed_not_sent" not in out
    assert "shadow_record_only" not in out
