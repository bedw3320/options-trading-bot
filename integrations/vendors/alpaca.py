"""Alpaca market-data adapter (SPY quotes, daily closes, option chain with Greeks/IV, OI).

Free with an Alpaca *paper-only* account (email signup, open to non-US residents):
options feed `indicative` (derived from OPRA, trades 15-min delayed), stocks feed `iex`.
A paid Algo Trader Plus plan switches to `opra`/`sip` via env, no code change.

Env (put in .env on the Mini, never commit):
  ALPACA_API_KEY_ID, ALPACA_API_SECRET_KEY        required
  ALPACA_OPTIONS_FEED=indicative|opra             default indicative
  ALPACA_STOCK_FEED=iex|sip                       default iex
  ALPACA_TRADING_BASE=https://paper-api.alpaca.markets   (contracts/OI endpoint)

Contract matches core.market_state: snapshot() never raises for data problems.
"""

from __future__ import annotations

import os
from datetime import date, datetime, timedelta, timezone
from typing import Any

import httpx

from core.market_state import unavailable
from integrations.vendors.chain import Contract, Quote, assemble, grid, parse_occ, pick_expiry, window
from schemas.cycle import MarketSnapshot
from schemas.strategy import DeterministicRules
from utils.logging import get_logger
from utils.time_et import ET

log = get_logger(__name__)
DATA_BASE = "https://data.alpaca.markets"


def _f(x: Any) -> float | None:
    try:
        return None if x is None or x == "" else float(x)
    except (TypeError, ValueError):
        return None


class AlpacaMarketState:
    def __init__(self, *, key_id: str | None = None, secret: str | None = None,
                 client: httpx.Client | None = None, today: date | None = None,
                 options_feed: str | None = None, stock_feed: str | None = None,
                 trading_base: str | None = None, now: Any = None) -> None:
        self.key_id = key_id or os.environ.get("ALPACA_API_KEY_ID", "")
        self.secret = secret or os.environ.get("ALPACA_API_SECRET_KEY", "")
        self.options_feed = options_feed or os.environ.get("ALPACA_OPTIONS_FEED", "indicative")
        self.stock_feed = stock_feed or os.environ.get("ALPACA_STOCK_FEED", "iex")
        self.trading_base = (trading_base or os.environ.get("ALPACA_TRADING_BASE",
                                                            "https://paper-api.alpaca.markets")).rstrip("/")
        self._today = today
        self._now = now or (lambda: datetime.now(timezone.utc))
        self.client = client or httpx.Client(timeout=20.0)
        self.source = f"alpaca:{self.options_feed}"

    # -- http ---------------------------------------------------------------
    def _get(self, url: str, params: dict[str, Any]) -> dict:
        r = self.client.get(url, params={k: v for k, v in params.items() if v is not None},
                            headers={"APCA-API-KEY-ID": self.key_id, "APCA-API-SECRET-KEY": self.secret})
        if r.status_code != 200:
            raise VendorError(f"http_{r.status_code} {url.split('.markets')[-1]}: {r.text[:200]}")
        return r.json()

    def _paged(self, url: str, params: dict[str, Any], key: str) -> list | dict:
        out: list | dict = {} if key == "snapshots" else []
        token = None
        for _ in range(50):
            data = self._get(url, {**params, "page_token": token})
            chunk = data.get(key) or ({} if isinstance(out, dict) else [])
            out.update(chunk) if isinstance(out, dict) else out.extend(chunk)
            token = data.get("next_page_token")
            if not token:
                break
        return out

    # -- provider -----------------------------------------------------------
    def snapshot(self, rules: DeterministicRules, *, held_legs: list[dict[str, Any]]) -> MarketSnapshot:
        if not (self.key_id and self.secret):
            return unavailable(rules.underlying, self.source, "alpaca_credentials_missing")
        try:
            return self._snapshot(rules, held_legs)
        except VendorError as exc:
            return unavailable(rules.underlying, self.source, f"alpaca_error: {exc}")
        except Exception as exc:
            log.warning("Alpaca snapshot failed: %s", exc)
            return unavailable(rules.underlying, self.source, f"alpaca_exception: {type(exc).__name__}: {exc}")

    def _snapshot(self, rules: DeterministicRules, held_legs: list[dict[str, Any]]) -> MarketSnapshot:
        und = rules.underlying
        today = self._today or datetime.now(ET).date()
        as_of = self._now().isoformat(timespec="seconds")

        trade = self._get(f"{DATA_BASE}/v2/stocks/{und}/trades/latest", {"feed": self.stock_feed}).get("trade") or {}
        price = _f(trade.get("p"))
        if price is None:
            return unavailable(und, self.source, "no_underlying_price", [], as_of)

        n = rules.signals.rv_lookback_days + 5
        bars = self._paged(f"{DATA_BASE}/v2/stocks/{und}/bars", {
            "timeframe": "1Day", "start": str(today - timedelta(days=int(n * 1.6) + 10)), "limit": 1000,
            "adjustment": "all", "feed": self.stock_feed}, "bars")
        closes = [float(b["c"]) for b in bars][-n:]
        if len(closes) < rules.signals.rv_lookback_days + 1:
            return unavailable(und, self.source, f"historical_bars_unavailable n={len(closes)}", [], as_of)

        w = window(rules, price, today)
        raw = self._paged(f"{self.trading_base}/v2/options/contracts", {
            "underlying_symbols": und, "expiration_date_gte": str(w["exp_gte"]),
            "expiration_date_lte": str(w["exp_lte"]), "strike_price_gte": w["strike_gte"],
            "strike_price_lte": w["strike_lte"], "limit": 10000}, "option_contracts")
        contracts = [Contract(occ=c["symbol"], expiry=c["expiration_date"].replace("-", ""),
                              right="C" if c["type"] == "call" else "P", strike=float(c["strike_price"]),
                              open_interest=_f(c.get("open_interest"))) for c in raw]
        expiry = pick_expiry(contracts, rules, today)
        if expiry is None:
            return unavailable(und, self.source, "no_option_contracts_in_window", [], as_of)
        chain = grid(contracts, expiry, price, rules.structure.strike_step)

        snaps = self._paged(f"{DATA_BASE}/v1beta1/options/snapshots/{und}", {
            "feed": self.options_feed, "expiration_date": f"{expiry[:4]}-{expiry[4:6]}-{expiry[6:]}",
            "strike_price_gte": w["strike_gte"], "strike_price_lte": w["strike_lte"], "limit": 1000}, "snapshots")
        quotes = {sym: _quote(s) for sym, s in snaps.items()}

        held: dict[str, Quote] = {}
        held_syms = [l["occ"] for l in held_legs if l.get("occ")]
        if held_syms:
            hs = self._paged(f"{DATA_BASE}/v1beta1/options/snapshots",
                             {"symbols": ",".join(held_syms), "feed": self.options_feed}, "snapshots")
            held = {sym: _quote(s) for sym, s in hs.items()}

        snap = assemble(rules=rules, source=self.source, price=price, closes=closes, expiry=expiry,
                        chain=chain, quotes=quotes, held_quotes=held, as_of=as_of)
        if not any(o.delta is not None and o.mid is not None for o in snap.options):
            return unavailable(und, self.source, "no_option_greeks_or_bid_ask", [], as_of)
        return snap


def _quote(s: dict) -> Quote:
    q = s.get("latestQuote") or {}
    g = s.get("greeks") or {}
    return Quote(bid=_f(q.get("bp")), ask=_f(q.get("ap")), delta=_f(g.get("delta")), iv=_f(s.get("impliedVolatility")))


class VendorError(RuntimeError):
    pass


__all__ = ["AlpacaMarketState", "VendorError", "parse_occ"]
