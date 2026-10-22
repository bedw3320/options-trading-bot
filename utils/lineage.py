"""Cycle lineage store (Epic 1): one cycle_id links inputs → fill.

Same SQLite file as utils/state.py (state/state.db, gitignored). Append-mostly:
artifacts are never updated; cycles get one terminal update (ended_at/outcome).
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from utils.time_et import ET

SCHEMA = """
CREATE TABLE IF NOT EXISTS cycles (
    cycle_id         TEXT PRIMARY KEY,
    strategy         TEXT NOT NULL,
    strategy_version TEXT NOT NULL,
    strategy_sha256  TEXT NOT NULL,
    mode             TEXT NOT NULL,            -- dry_run | paper
    started_at       TEXT NOT NULL,            -- UTC ISO
    ended_at         TEXT,
    outcome          TEXT,                     -- entered | exited | abstained | proposed_not_sent | error
    reasons_json     TEXT,
    git_sha          TEXT
);
CREATE TABLE IF NOT EXISTS cycle_artifacts (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    cycle_id     TEXT NOT NULL,
    kind         TEXT NOT NULL,                -- inputs | market_snapshot | signals | decision | intent | order | fill | reconcile | error | kill_switch
    ts           TEXT NOT NULL,
    payload_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_artifacts_cycle ON cycle_artifacts(cycle_id, id);
CREATE TABLE IF NOT EXISTS strategy_positions (
    position_id      TEXT PRIMARY KEY,
    strategy         TEXT NOT NULL,
    mode             TEXT NOT NULL,
    status           TEXT NOT NULL,            -- open | closed
    opened_cycle_id  TEXT NOT NULL,
    closed_cycle_id  TEXT,
    legs_json        TEXT NOT NULL,
    entry_price      REAL NOT NULL,            -- per-share net debit (<0 = credit)
    quantity         INTEGER NOT NULL,
    max_loss_usd     REAL,
    opened_at        TEXT NOT NULL,
    closed_at        TEXT,
    exit_price       REAL,
    realized_pnl_usd REAL,
    exit_trigger     TEXT
);
CREATE TABLE IF NOT EXISTS orders (
    idempotency_key  TEXT PRIMARY KEY,
    cycle_id         TEXT NOT NULL,
    strategy         TEXT NOT NULL,
    mode             TEXT NOT NULL,
    purpose          TEXT NOT NULL,
    position_id      TEXT,
    broker_order_id  TEXT,
    status           TEXT NOT NULL,
    intent_json      TEXT NOT NULL,
    created_at       TEXT NOT NULL,
    updated_at       TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS fills (
    exec_id          TEXT PRIMARY KEY,
    idempotency_key  TEXT,
    broker_order_id  TEXT,
    cycle_id         TEXT,
    mode             TEXT NOT NULL,
    payload_json     TEXT NOT NULL,
    recorded_at      TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS kill_switch (
    strategy   TEXT NOT NULL,
    mode       TEXT NOT NULL,
    latched    INTEGER NOT NULL,
    reason     TEXT,
    ts         TEXT NOT NULL,
    PRIMARY KEY (strategy, mode)
);
"""


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def to_et(iso: str | None) -> str:
    if not iso:
        return "-"
    try:
        return datetime.fromisoformat(iso).astimezone(ET).strftime("%Y-%m-%d %H:%M:%S ET")
    except ValueError:
        return iso


def _dumps(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)


class Lineage:
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as c:
            c.executescript(SCHEMA)

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        return conn

    # --- cycles -----------------------------------------------------------
    def start_cycle(
        self,
        *,
        strategy: str,
        strategy_version: str,
        strategy_sha256: str,
        mode: str,
        git_sha: str | None = None,
        cycle_id: str | None = None,
        started_at: str | None = None,
    ) -> str:
        cid = cycle_id or f"c-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:6]}"
        with self._conn() as c:
            c.execute(
                "INSERT INTO cycles(cycle_id, strategy, strategy_version, strategy_sha256, mode, started_at, git_sha)"
                " VALUES (?,?,?,?,?,?,?)",
                (cid, strategy, strategy_version, strategy_sha256, mode, started_at or utc_now_iso(), git_sha),
            )
        return cid

    def end_cycle(self, cycle_id: str, outcome: str, reasons: list[str]) -> None:
        with self._conn() as c:
            c.execute(
                "UPDATE cycles SET ended_at=?, outcome=?, reasons_json=? WHERE cycle_id=? AND ended_at IS NULL",
                (utc_now_iso(), outcome, _dumps(reasons), cycle_id),
            )

    def annotate_reasons(self, cycle_id: str, reasons: list[str]) -> None:
        """Replace the terminal reasons of an ended cycle (used to append audit notes)."""
        with self._conn() as c:
            c.execute("UPDATE cycles SET reasons_json=? WHERE cycle_id=?", (_dumps(reasons), cycle_id))

    def record(self, cycle_id: str, kind: str, payload: Any) -> None:
        with self._conn() as c:
            c.execute(
                "INSERT INTO cycle_artifacts(cycle_id, kind, ts, payload_json) VALUES (?,?,?,?)",
                (cycle_id, kind, utc_now_iso(), _dumps(payload)),
            )

    def get_cycle(self, cycle_id: str) -> dict[str, Any] | None:
        with self._conn() as c:
            if cycle_id == "last":
                row = c.execute("SELECT * FROM cycles ORDER BY started_at DESC, rowid DESC LIMIT 1").fetchone()
            else:
                row = c.execute("SELECT * FROM cycles WHERE cycle_id=?", (cycle_id,)).fetchone()
            if row is None:
                return None
            arts = c.execute(
                "SELECT kind, ts, payload_json FROM cycle_artifacts WHERE cycle_id=? ORDER BY id",
                (row["cycle_id"],),
            ).fetchall()
        out = dict(row)
        out["reasons"] = json.loads(out.pop("reasons_json") or "[]")
        out["artifacts"] = [
            {"kind": a["kind"], "ts": a["ts"], "payload": json.loads(a["payload_json"])} for a in arts
        ]
        return out

    def list_cycles(self, limit: int = 20, strategy: str | None = None) -> list[dict[str, Any]]:
        q = "SELECT cycle_id, strategy, mode, started_at, outcome, reasons_json FROM cycles"
        args: tuple = ()
        if strategy:
            q += " WHERE strategy=?"
            args = (strategy,)
        q += " ORDER BY started_at DESC, rowid DESC LIMIT ?"
        with self._conn() as c:
            rows = c.execute(q, (*args, limit)).fetchall()
        return [
            {**dict(r), "reasons": json.loads(r["reasons_json"] or "[]")} for r in rows
        ]

    def recent_outcomes(self, strategy: str, mode: str, n: int) -> list[str]:
        with self._conn() as c:
            rows = c.execute(
                "SELECT outcome FROM cycles WHERE strategy=? AND mode=? AND outcome IS NOT NULL"
                " ORDER BY started_at DESC, rowid DESC LIMIT ?",
                (strategy, mode, n),
            ).fetchall()
        return [r["outcome"] for r in rows]

    def signal_history(self, strategy: str, mode: str, name: str, limit: int = 252) -> list[float]:
        """Past values of one signal (for percentile). One per ET trading day.

        For each America/New_York date, keep the latest completed cycle that
        recorded a non-null value (later `started_at`, then later artifact id).
        Incomplete cycles are ignored. Result is oldest day first; `limit` is
        the number of days.
        """
        with self._conn() as c:
            rows = c.execute(
                "SELECT a.payload_json, a.id, c.started_at"
                " FROM cycle_artifacts a JOIN cycles c ON a.cycle_id=c.cycle_id"
                " WHERE a.kind='signals' AND c.strategy=? AND c.mode=? AND c.ended_at IS NOT NULL"
                " ORDER BY c.started_at ASC, a.id ASC",
                (strategy, mode),
            ).fetchall()
        by_day: dict[str, float] = {}
        for r in rows:
            val = None
            for s in json.loads(r["payload_json"]).get("signals", []):
                if s.get("name") == name and s.get("value") is not None:
                    val = float(s["value"])
                    break
            if val is None:
                continue
            day = datetime.fromisoformat(r["started_at"]).astimezone(ET).date().isoformat()
            by_day[day] = val
        days = sorted(by_day)
        return [by_day[d] for d in days[-limit:]]

    # --- positions ----------------------------------------------------------
    def open_positions(self, strategy: str, mode: str) -> list[dict[str, Any]]:
        with self._conn() as c:
            rows = c.execute(
                "SELECT * FROM strategy_positions WHERE strategy=? AND mode=? AND status='open'",
                (strategy, mode),
            ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["legs"] = json.loads(d.pop("legs_json"))
            out.append(d)
        return out

    def open_position(
        self,
        *,
        position_id: str,
        strategy: str,
        mode: str,
        cycle_id: str,
        legs: list[dict[str, Any]],
        entry_price: float,
        quantity: int,
        max_loss_usd: float | None,
    ) -> None:
        with self._conn() as c:
            c.execute(
                "INSERT INTO strategy_positions(position_id, strategy, mode, status, opened_cycle_id, legs_json,"
                " entry_price, quantity, max_loss_usd, opened_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (position_id, strategy, mode, "open", cycle_id, _dumps(legs), entry_price, quantity,
                 max_loss_usd, utc_now_iso()),
            )

    def close_position(
        self, position_id: str, *, cycle_id: str, exit_price: float, trigger: str
    ) -> float:
        with self._conn() as c:
            row = c.execute(
                "SELECT entry_price, quantity FROM strategy_positions WHERE position_id=?", (position_id,)
            ).fetchone()
            # Opened by BUYing the combo at entry_price; closed by SELLing it at exit_price.
            pnl = (exit_price - row["entry_price"]) * 100.0 * row["quantity"]
            c.execute(
                "UPDATE strategy_positions SET status='closed', closed_cycle_id=?, closed_at=?, exit_price=?,"
                " realized_pnl_usd=?, exit_trigger=? WHERE position_id=?",
                (cycle_id, utc_now_iso(), exit_price, pnl, trigger, position_id),
            )
        return pnl

    def realized_pnl_since(self, strategy: str, mode: str, since_iso: str) -> float:
        with self._conn() as c:
            row = c.execute(
                "SELECT COALESCE(SUM(realized_pnl_usd),0) AS s FROM strategy_positions"
                " WHERE strategy=? AND mode=? AND status='closed' AND closed_at>=?",
                (strategy, mode, since_iso),
            ).fetchone()
        return float(row["s"])

    def entries_since(self, strategy: str, mode: str, since_iso: str) -> int:
        with self._conn() as c:
            row = c.execute(
                "SELECT COUNT(*) AS n FROM orders WHERE strategy=? AND mode=? AND purpose='open'"
                " AND created_at>=? AND status NOT IN ('rejected')",
                (strategy, mode, since_iso),
            ).fetchone()
        return int(row["n"])

    # --- orders / fills -------------------------------------------------------
    def order_exists(self, idempotency_key: str) -> bool:
        with self._conn() as c:
            return c.execute(
                "SELECT 1 FROM orders WHERE idempotency_key=?", (idempotency_key,)
            ).fetchone() is not None

    def insert_order(self, *, intent: dict[str, Any], cycle_id: str, mode: str, status: str) -> None:
        now = utc_now_iso()
        with self._conn() as c:
            c.execute(
                "INSERT INTO orders(idempotency_key, cycle_id, strategy, mode, purpose, position_id, status,"
                " intent_json, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (intent["idempotency_key"], cycle_id, intent["strategy"], mode, intent["purpose"],
                 intent.get("position_id"), status, _dumps(intent), now, now),
            )

    def update_order(self, idempotency_key: str, *, status: str, broker_order_id: str | None = None) -> None:
        with self._conn() as c:
            c.execute(
                "UPDATE orders SET status=?, broker_order_id=COALESCE(?, broker_order_id), updated_at=?"
                " WHERE idempotency_key=?",
                (status, broker_order_id, utc_now_iso(), idempotency_key),
            )

    def orders_by_status(self, strategy: str, mode: str, statuses: tuple[str, ...]) -> list[dict[str, Any]]:
        marks = ",".join("?" * len(statuses))
        with self._conn() as c:
            rows = c.execute(
                f"SELECT * FROM orders WHERE strategy=? AND mode=? AND status IN ({marks})",
                (strategy, mode, *statuses),
            ).fetchall()
        return [dict(r) for r in rows]

    def known_broker_order_ids(self, strategy: str, mode: str) -> set[str]:
        with self._conn() as c:
            rows = c.execute(
                "SELECT broker_order_id FROM orders WHERE strategy=? AND mode=? AND broker_order_id IS NOT NULL",
                (strategy, mode),
            ).fetchall()
        return {str(r["broker_order_id"]) for r in rows}

    def record_fill(
        self, *, exec_id: str, idempotency_key: str | None, broker_order_id: str | None,
        cycle_id: str | None, mode: str, payload: dict[str, Any],
    ) -> bool:
        """Insert once per exec_id. Returns True if new."""
        with self._conn() as c:
            cur = c.execute(
                "INSERT OR IGNORE INTO fills(exec_id, idempotency_key, broker_order_id, cycle_id, mode,"
                " payload_json, recorded_at) VALUES (?,?,?,?,?,?,?)",
                (exec_id, idempotency_key, broker_order_id, cycle_id, mode, _dumps(payload), utc_now_iso()),
            )
            return cur.rowcount > 0

    def fill_exec_ids(self, mode: str) -> set[str]:
        with self._conn() as c:
            rows = c.execute("SELECT exec_id FROM fills WHERE mode=?", (mode,)).fetchall()
        return {r["exec_id"] for r in rows}

    # --- kill switch -------------------------------------------------------------
    def kill_state(self, strategy: str, mode: str) -> dict[str, Any] | None:
        with self._conn() as c:
            row = c.execute(
                "SELECT * FROM kill_switch WHERE strategy=? AND mode=? AND latched=1", (strategy, mode)
            ).fetchone()
        return dict(row) if row else None

    def latch_kill(self, strategy: str, mode: str, reason: str) -> None:
        with self._conn() as c:
            c.execute(
                "INSERT INTO kill_switch(strategy, mode, latched, reason, ts) VALUES (?,?,1,?,?)"
                " ON CONFLICT(strategy, mode) DO UPDATE SET latched=1, reason=excluded.reason, ts=excluded.ts"
                " WHERE kill_switch.latched=0",
                (strategy, mode, reason, utc_now_iso()),
            )

    def rearm(self, strategy: str, mode: str) -> bool:
        with self._conn() as c:
            cur = c.execute(
                "UPDATE kill_switch SET latched=0, ts=? WHERE strategy=? AND mode=? AND latched=1",
                (utc_now_iso(), strategy, mode),
            )
            return cur.rowcount > 0
