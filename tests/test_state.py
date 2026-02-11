"""Tests for utils/state.py — state persistence and event logging."""

from __future__ import annotations

import json
import tempfile
import time
from pathlib import Path

import pytest

from utils.state import (
    DEFAULT_STATE,
    append_event,
    count_daily_trades,
    ensure_tables,
    load_state,
    save_state,
)


@pytest.fixture
def db_path(tmp_path):
    return str(tmp_path / "test_state.db")


class TestLoadState:
    def test_missing_key_returns_defaults(self, db_path):
        state = load_state(db_path, "nonexistent")
        assert state == DEFAULT_STATE
        assert "orders" in state
        assert "positions" in state
        assert "meta" in state

    def test_round_trip(self, db_path):
        original = {"orders": {"o1": {"status": "filled"}}, "positions": {}, "meta": {"x": 1}}
        save_state(db_path, "k1", original)
        loaded = load_state(db_path, "k1")
        assert loaded == original

    def test_corrupted_json_returns_defaults(self, db_path):
        ensure_tables(db_path)
        import sqlite3

        conn = sqlite3.connect(db_path)
        conn.execute(
            "INSERT INTO agent_state(state_key, state_json, updated_ts) VALUES(?, ?, ?)",
            ("bad", "NOT-JSON", int(time.time())),
        )
        conn.commit()
        conn.close()

        state = load_state(db_path, "bad")
        assert state == DEFAULT_STATE


class TestSaveState:
    def test_save_and_load(self, db_path):
        save_state(db_path, "s1", {"orders": {}, "positions": {"BTC": {}}, "meta": {}})
        loaded = load_state(db_path, "s1")
        assert "BTC" in loaded["positions"]

    def test_overwrite(self, db_path):
        save_state(db_path, "s1", {"orders": {}, "positions": {}, "meta": {"v": 1}})
        save_state(db_path, "s1", {"orders": {}, "positions": {}, "meta": {"v": 2}})
        loaded = load_state(db_path, "s1")
        assert loaded["meta"]["v"] == 2


class TestAppendEvent:
    def test_appends_correctly(self, db_path):
        append_event(db_path, "k1", "cycle_start", {"ts": 1})
        append_event(db_path, "k1", "agent_output", {"ts": 2})

        import sqlite3

        conn = sqlite3.connect(db_path)
        rows = conn.execute(
            "SELECT event_type FROM agent_events WHERE state_key = ? ORDER BY id",
            ("k1",),
        ).fetchall()
        conn.close()
        assert [r[0] for r in rows] == ["cycle_start", "agent_output"]


class TestCountDailyTrades:
    def test_zero_trades(self, db_path):
        assert count_daily_trades(db_path, "k1") == 0

    def test_counts_todays_orders(self, db_path):
        append_event(db_path, "k1", "order_placed", {"order": {"id": "1"}})
        append_event(db_path, "k1", "order_placed", {"order": {"id": "2"}})
        assert count_daily_trades(db_path, "k1") == 2

    def test_ignores_other_keys(self, db_path):
        append_event(db_path, "k1", "order_placed", {"order": {"id": "1"}})
        append_event(db_path, "k2", "order_placed", {"order": {"id": "2"}})
        assert count_daily_trades(db_path, "k1") == 1

    def test_ignores_non_order_events(self, db_path):
        append_event(db_path, "k1", "cycle_start", {})
        append_event(db_path, "k1", "order_placed", {"order": {"id": "1"}})
        append_event(db_path, "k1", "agent_output", {})
        assert count_daily_trades(db_path, "k1") == 1
