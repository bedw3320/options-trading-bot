"""Research SQLite store.

Separate file from state/state.db on purpose: trading lineage (cycles, fills,
kill switch, decision records) stays in the Epic 1 store. Skew snapshots are
observational, append-mostly, and must not share migrations with the runner.
Default path `state/research.db` so a Mini backup of `state/` captures both;
the file is gitignored like the rest of `state/`.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

DEFAULT_DB = "state/research.db"
DELTA_CONVENTION = "ib_model_signed"

SCHEMA = """
CREATE TABLE IF NOT EXISTS skew_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    trade_date TEXT NOT NULL,
    ticker TEXT NOT NULL,
    expiry TEXT,
    dte INTEGER,
    target_dte INTEGER,
    data_source TEXT NOT NULL,
    delta_convention TEXT NOT NULL,
    status TEXT NOT NULL,
    skip_reason TEXT,
    rr25 REAL,
    put_iv_25d REAL,
    call_iv_25d REAL,
    underlying_price REAL,
    payload_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_skew_ticker_date
    ON skew_snapshots(ticker, trade_date, target_dte);
"""


def _connect(db_path: str) -> sqlite3.Connection:
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    return conn


def ensure_tables(db_path: str) -> None:
    with _connect(db_path) as conn:
        conn.executescript(SCHEMA)


def has_ok_snapshot(db_path: str, *, ticker: str, trade_date: str, target_dte: int) -> bool:
    ensure_tables(db_path)
    with _connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT 1 FROM skew_snapshots
            WHERE ticker = ? AND trade_date = ? AND target_dte = ? AND status = 'ok'
            LIMIT 1
            """,
            (ticker, trade_date, target_dte),
        ).fetchone()
    return row is not None


def insert_snapshot(db_path: str, row: dict[str, Any]) -> int:
    ensure_tables(db_path)
    payload = row.get("payload") if "payload" in row else row.get("payload_json") or {}
    if not isinstance(payload, str):
        payload = json.dumps(payload, default=str)
    with _connect(db_path) as conn:
        cur = conn.execute(
            """
            INSERT INTO skew_snapshots (
                ts, trade_date, ticker, expiry, dte, target_dte, data_source,
                delta_convention, status, skip_reason, rr25, put_iv_25d, call_iv_25d,
                underlying_price, payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                row["ts"],
                row["trade_date"],
                row["ticker"],
                row.get("expiry"),
                row.get("dte"),
                row.get("target_dte"),
                row["data_source"],
                row.get("delta_convention") or DELTA_CONVENTION,
                row["status"],
                row.get("skip_reason"),
                row.get("rr25"),
                row.get("put_iv_25d"),
                row.get("call_iv_25d"),
                row.get("underlying_price"),
                payload,
            ),
        )
        return int(cur.lastrowid)


def list_snapshots(db_path: str, *, ticker: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
    ensure_tables(db_path)
    sql = "SELECT * FROM skew_snapshots"
    args: list[Any] = []
    if ticker:
        sql += " WHERE ticker = ?"
        args.append(ticker)
    sql += " ORDER BY id DESC LIMIT ?"
    args.append(limit)
    with _connect(db_path) as conn:
        rows = conn.execute(sql, args).fetchall()
    out = []
    for r in rows:
        item = dict(r)
        try:
            item["payload"] = json.loads(item.pop("payload_json"))
        except Exception:
            item["payload"] = item.pop("payload_json")
        out.append(item)
    return out
