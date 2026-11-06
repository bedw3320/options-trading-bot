"""Daily skew snapshot job.

Records, once per ET trading day near the close, per watchlist ticker, per-strike
IV and delta for the ~30 DTE and ~45 DTE expiries plus derived rr25 and 25d
put/call IV. Delayed or stale data is skipped with a recorded reason — never
invented.

    TRADING_MODE=paper IB_GATEWAY_HOST=127.0.0.1 IB_GATEWAY_PORT=4002 \\
      uv run python -m research.skew_snapshot

launchd template: deploy/com.otb.skew-snapshot.plist.template (not installed
by ops/mini/install.sh).
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from research.config import load_thresholds
from research.db import DEFAULT_DB, DELTA_CONVENTION, has_ok_snapshot, insert_snapshot
from research.liquidity import quote_age_seconds
from research.models import QuotedChain
from research.skew import pick_expiries_near, rr25_for_expiry, strike_payload
from schemas.watchlist import load_watchlist
from utils.time_et import ET

DEFAULT_WATCHLIST = "strategies/watchlist.yaml"
DEFAULT_CLIENT_ID = 22


def _trade_date(as_of: datetime):
    if as_of.tzinfo is None:
        as_of = as_of.replace(tzinfo=timezone.utc)
    return as_of.astimezone(ET).date()


def _stale(chain: QuotedChain, max_age: float) -> str | None:
    now = chain.as_of
    ages = [quote_age_seconds(l, now) for l in chain.legs]
    known = [a for a in ages if a is not None]
    if not known:
        return "quote_time_unavailable"
    oldest = max(known)
    if oldest > max_age:
        return f"stale_quotes age={oldest:.0f}s > {max_age:.0f}s"
    return None


def snapshot_chain(
    chain: QuotedChain,
    *,
    db_path: str,
    max_quote_age_seconds: float,
    target_abs_delta: float = 0.25,
) -> list[dict]:
    """Persist one or more rows (ok or skipped). Used by the job and by tests."""
    as_of = chain.as_of
    trade_date = _trade_date(as_of).isoformat()
    ts = as_of.isoformat()
    recorded: list[dict] = []

    def skip(target_dte: int | None, reason: str, expiry: str | None = None, dte: int | None = None) -> dict:
        row = {
            "ts": ts,
            "trade_date": trade_date,
            "ticker": chain.ticker,
            "expiry": expiry,
            "dte": dte,
            "target_dte": target_dte,
            "data_source": chain.data_source,
            "delta_convention": DELTA_CONVENTION,
            "status": "skipped",
            "skip_reason": reason,
            "rr25": None,
            "put_iv_25d": None,
            "call_iv_25d": None,
            "underlying_price": chain.underlying_price,
            "payload": {"legs": []},
        }
        row["id"] = insert_snapshot(db_path, row)
        recorded.append(row)
        return row

    if chain.diagnostic_only or (chain.skip_reason and "non_live" in (chain.skip_reason or "")):
        skip(None, chain.skip_reason or f"delayed_or_non_live source={chain.data_source}")
        return recorded
    if chain.data_source.startswith("ib_delayed") or chain.data_source in ("ib_frozen", "cboe_delayed"):
        skip(None, f"delayed_or_non_live source={chain.data_source}")
        return recorded
    stale = _stale(chain, max_quote_age_seconds)
    if stale:
        skip(None, stale)
        return recorded

    today = _trade_date(as_of)
    picked = pick_expiries_near(chain, today=today)
    if not picked:
        skip(None, "no_expiry_near_30_or_45")
        return recorded

    wanted = {30, 45}
    for target, expiry, dte in picked:
        wanted.discard(target)
        if has_ok_snapshot(db_path, ticker=chain.ticker, trade_date=trade_date, target_dte=target):
            skip(target, "already_snapshotted", expiry=expiry, dte=dte)
            continue
        stats = rr25_for_expiry(chain, expiry, target_abs_delta=target_abs_delta)
        if stats["rr25"] is None:
            skip(target, "missing_greeks_or_iv_for_rr25", expiry=expiry, dte=dte)
            continue
        row = {
            "ts": ts,
            "trade_date": trade_date,
            "ticker": chain.ticker,
            "expiry": expiry,
            "dte": dte,
            "target_dte": target,
            "data_source": chain.data_source,
            "delta_convention": DELTA_CONVENTION,
            "status": "ok",
            "skip_reason": None,
            "rr25": stats["rr25"],
            "put_iv_25d": stats["put_iv_25d"],
            "call_iv_25d": stats["call_iv_25d"],
            "underlying_price": chain.underlying_price,
            "payload": {
                "rr25_note": {"put": stats["put_note"], "call": stats["call_note"]},
                "delta_convention": DELTA_CONVENTION,
                "legs": strike_payload(chain, expiry),
            },
        }
        row["id"] = insert_snapshot(db_path, row)
        recorded.append(row)
    for missing in sorted(wanted):
        skip(missing, f"no_distinct_expiry_near_{missing}")
    return recorded


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="research.skew_snapshot", description=__doc__)
    p.add_argument("--watchlist", default=DEFAULT_WATCHLIST)
    p.add_argument("--db", default=os.environ.get("RESEARCH_DB", DEFAULT_DB))
    p.add_argument("--strategy", default=None)
    p.add_argument("--config", default=None)
    p.add_argument("--fixture", default=None, help="QuotedChain JSON list; skip IB")
    p.add_argument("--host", default=os.environ.get("IB_GATEWAY_HOST", "127.0.0.1"))
    p.add_argument("--port", type=int, default=int(os.environ.get("IB_GATEWAY_PORT", "4002")))
    p.add_argument("--client-id", type=int, default=int(os.environ.get("IB_SKEW_CLIENT_ID", str(DEFAULT_CLIENT_ID))))
    p.add_argument("--timeout", type=float, default=12.0)
    args = p.parse_args(argv)

    thresholds = load_thresholds(strategy_path=args.strategy, config_path=args.config)

    if args.fixture:
        import json
        from research.models import QuotedChain as QC

        raw = json.loads(Path(args.fixture).read_text())
        items = raw["tickers"] if isinstance(raw, dict) and "tickers" in raw else raw
        if isinstance(items, dict):
            items = [items]
        chains = [QC.model_validate(x) for x in items]
        rows = []
        for chain in chains:
            rows.extend(
                snapshot_chain(
                    chain, db_path=args.db,
                    max_quote_age_seconds=thresholds.max_quote_age_seconds,
                    target_abs_delta=thresholds.target_abs_delta,
                )
            )
    else:
        from research.ib_fetch import connect_paper_readonly, fetch_quoted_chain, refuse_live_port

        refuse_live_port(args.port)
        names = [n.ticker for n in load_watchlist(args.watchlist).names]
        ib = connect_paper_readonly(host=args.host, port=args.port, client_id=args.client_id)
        rows = []
        try:
            for ticker in names:
                chain = fetch_quoted_chain(ib, ticker, thresholds, quote_timeout=args.timeout)
                rows.extend(
                    snapshot_chain(
                        chain, db_path=args.db,
                        max_quote_age_seconds=thresholds.max_quote_age_seconds,
                        target_abs_delta=thresholds.target_abs_delta,
                    )
                )
        finally:
            ib.disconnect()

    for r in rows:
        mark = r["status"]
        extra = r.get("skip_reason") or f"rr25={r.get('rr25')}"
        print(f"{r['ticker']} target={r.get('target_dte')} {mark} {extra} source={r['data_source']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
