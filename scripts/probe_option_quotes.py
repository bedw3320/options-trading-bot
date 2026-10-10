#!/usr/bin/env python3
"""Read-only RTH probe: SPY + near-ATM call/put (~1-4 weeks out).

On the Mini, Gateway paper on 4002, no competing live TWS/mobile session:

    cd "$HOME/Documents/GitHub Repos/options-trading-bot"
    TRADING_MODE=paper IB_GATEWAY_HOST=127.0.0.1 IB_GATEWAY_PORT=4002 \\
      uv run python scripts/probe_option_quotes.py --host 127.0.0.1 --port 4002

Optional: --save writes a quotes_probe event via utils.state.append_event.
Does not place orders (readonly=True, distinct clientId).
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from integrations.ibkr.client import create_ib_client
from integrations.ibkr.market_data import get_stock_quote
from integrations.ibkr.occ import make_option
from integrations.ibkr.option_quotes import request_quote
from integrations.ibkr.options_data import get_options_chain
from utils.state import append_event


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Read-only IB option quote + Greeks probe")
    parser.add_argument("--host", default=os.environ.get("IB_GATEWAY_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("IB_GATEWAY_PORT", "4002")))
    parser.add_argument(
        "--client-id",
        type=int,
        default=int(os.environ.get("IB_DATA_CLIENT_ID", "7")),
        help="Must differ from the trading IB_CLIENT_ID (default 7)",
    )
    parser.add_argument("--underlying", default="SPY")
    parser.add_argument("--min-dte", type=int, default=7)
    parser.add_argument("--max-dte", type=int, default=28)
    parser.add_argument(
        "--market-data-type",
        type=int,
        default=int(os.environ.get("IB_MARKET_DATA_TYPE", "1")),
        help="1=live 2=frozen 3=delayed 4=delayed-frozen",
    )
    parser.add_argument("--timeout", type=float, default=15.0)
    parser.add_argument("--save", action="store_true", help="append_event to state.db")
    parser.add_argument("--db-path", default="state/state.db")
    parser.add_argument("--state-key", default="quotes-probe")
    return parser.parse_args()


def _print_quote(label: str, quote) -> None:
    g = quote.model_greeks
    errors = ", ".join(f"{e.code}:{e.message}" for e in quote.errors) or "-"
    print(
        f"{label} symbol={quote.symbol} bid={quote.bid} ask={quote.ask} mid={quote.mid} "
        f"last={quote.last} mdt={quote.market_data_type} oi={quote.open_interest} "
        f"iv={quote.implied_vol} status={quote.status} errors=[{errors}]"
    )
    if g:
        print(
            f"  modelGreeks delta={g.delta} gamma={g.gamma} vega={g.vega} "
            f"theta={g.theta} iv={g.implied_vol} undPrice={g.und_price}"
        )
        if quote.bid_greeks:
            print(f"  bidGreeks delta={quote.bid_greeks.delta} iv={quote.bid_greeks.implied_vol}")
        if quote.ask_greeks:
            print(f"  askGreeks delta={quote.ask_greeks.delta} iv={quote.ask_greeks.implied_vol}")


def main() -> int:
    load_dotenv()
    args = _parse_args()
    os.environ["IB_GATEWAY_HOST"] = str(args.host)
    os.environ["IB_GATEWAY_PORT"] = str(args.port)
    os.environ["IB_MARKET_DATA_TYPE"] = str(args.market_data_type)

    print(
        f"probe host={args.host} port={args.port} clientId={args.client_id} "
        f"readonly=True marketDataType={args.market_data_type}"
    )

    payload: dict = {
        "host": args.host,
        "port": args.port,
        "client_id": args.client_id,
        "market_data_type": args.market_data_type,
        "underlying": args.underlying,
    }
    ib = None
    try:
        ib = create_ib_client("paper", client_id=args.client_id, readonly=True)
        managed = []
        getter = getattr(ib, "managedAccounts", None)
        if callable(getter):
            managed = list(getter() or [])
        print(f"managedAccounts={managed}")
        payload["managed_accounts"] = [str(a) for a in managed]

        stock = get_stock_quote(ib, args.underlying)
        print(
            f"STOCK {args.underlying} bid={stock.get('bid_price')} ask={stock.get('ask_price')} "
            f"last={stock.get('last')} status={stock.get('status')} errors={stock.get('errors')}"
        )
        payload["stock"] = stock

        chain = get_options_chain(
            ib,
            args.underlying,
            min_dte=args.min_dte,
            max_dte=args.max_dte,
            n_strikes=1,
            max_expiries=1,
            include_quotes=False,
            limit=4,
        )
        if not chain:
            print("No option contracts in DTE window (defs).")
            payload["error"] = "no_option_contracts"
            return 1

        quotes = []
        for row in chain:
            contract = make_option(
                row["underlying_symbol"],
                row["expiration_date"],
                float(row["strike_price"]),
                "C" if row["type"] == "call" else "P",
                trading_class=row.get("trading_class") or args.underlying,
            )
            qualified = ib.qualifyContracts(contract)
            use = qualified[0] if qualified else contract
            quote = request_quote(
                ib,
                use,
                timeout=args.timeout,
                require_greeks=True,
                market_data_type=args.market_data_type,
            )
            label = f"{row['type'].upper()} {row['expiration_date']} {row['strike_price']}"
            _print_quote(label, quote)
            quotes.append(quote.model_dump())

        payload["options"] = quotes
        return 0
    finally:
        if args.save:
            append_event(args.db_path, args.state_key, "quotes_probe", payload)
            print(f"saved quotes_probe → {args.db_path} key={args.state_key}")
        if ib is not None:
            ib.disconnect()


if __name__ == "__main__":
    raise SystemExit(main())
