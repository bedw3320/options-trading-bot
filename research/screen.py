"""Liquidity screen CLI.

Run on the Mini against IB Gateway paper port 4002 (readonly):

    TRADING_MODE=paper IB_GATEWAY_HOST=127.0.0.1 IB_GATEWAY_PORT=4002 \\
      uv run python -m research.screen

Does not place orders. Delayed quotes are labelled and marked diagnostic_only.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from research.artifacts import write_artifacts
from research.config import load_thresholds
from research.liquidity import screen_chain
from research.models import QuotedChain, TickerScreen
from schemas.watchlist import load_watchlist
from utils.time_et import ET

DEFAULT_WATCHLIST = "strategies/watchlist.yaml"
DEFAULT_OUT = "research/screens"
DEFAULT_CLIENT_ID = 21


def _trade_date(as_of: datetime):
    if as_of.tzinfo is None:
        as_of = as_of.replace(tzinfo=timezone.utc)
    return as_of.astimezone(ET).date()


def _tickers(args) -> list[str]:
    if args.tickers:
        return [t.strip().upper() for t in args.tickers.split(",") if t.strip()]
    wl = load_watchlist(args.watchlist)
    return [n.ticker for n in wl.names]


def _load_fixture(path: Path) -> list[QuotedChain]:
    raw = json.loads(path.read_text())
    if isinstance(raw, dict) and "tickers" in raw:
        items = raw["tickers"]
    elif isinstance(raw, list):
        items = raw
    else:
        items = [raw]
    return [QuotedChain.model_validate(x) for x in items]


def run_fixture(args) -> list[TickerScreen]:
    thresholds = load_thresholds(strategy_path=args.strategy, config_path=args.config)
    chains = _load_fixture(Path(args.fixture))
    wanted = {t.strip().upper() for t in args.tickers.split(",")} if args.tickers else None
    if wanted:
        chains = [c for c in chains if c.ticker.upper() in wanted]
    return [screen_chain(c, thresholds) for c in chains]


def run_ib(args) -> list[TickerScreen]:
    from research.ib_fetch import connect_paper_readonly, fetch_quoted_chain, refuse_live_port

    refuse_live_port(args.port)
    thresholds = load_thresholds(strategy_path=args.strategy, config_path=args.config)
    names = _tickers(args)
    ib = connect_paper_readonly(host=args.host, port=args.port, client_id=args.client_id)
    try:
        screens: list[TickerScreen] = []
        for ticker in names:
            chain = fetch_quoted_chain(ib, ticker, thresholds, quote_timeout=args.timeout)
            screens.append(screen_chain(chain, thresholds))
        return screens
    finally:
        ib.disconnect()


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="research.screen", description=__doc__)
    p.add_argument("--watchlist", default=DEFAULT_WATCHLIST)
    p.add_argument("--tickers", default=None, help="Comma-separated override (default: all watchlist names)")
    p.add_argument("--strategy", default=None, help="Strategy YAML to inherit liquidity thresholds from")
    p.add_argument("--config", default=None, help="research/config.yaml overrides")
    p.add_argument("--output-dir", default=DEFAULT_OUT)
    p.add_argument("--fixture", default=None, help="QuotedChain JSON; skip IB")
    p.add_argument("--host", default=os.environ.get("IB_GATEWAY_HOST", "127.0.0.1"))
    p.add_argument("--port", type=int, default=int(os.environ.get("IB_GATEWAY_PORT", "4002")))
    p.add_argument("--client-id", type=int, default=int(os.environ.get("IB_RESEARCH_CLIENT_ID", str(DEFAULT_CLIENT_ID))))
    p.add_argument("--timeout", type=float, default=12.0)
    args = p.parse_args(argv)

    screens = run_fixture(args) if args.fixture else run_ib(args)
    as_of = screens[0].as_of if screens else datetime.now(timezone.utc)
    trade_date = _trade_date(as_of)
    json_path, md_path = write_artifacts(
        screens, output_dir=args.output_dir, trade_date=trade_date, as_of=as_of,
    )
    print(f"wrote {json_path}")
    print(f"wrote {md_path}")
    for s in screens:
        print(f"  {s.ticker} {s.result} source={s.data_source} diagnostic_only={s.diagnostic_only}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
