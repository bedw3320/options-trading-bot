"""CBOE delayed-quotes adapter (unofficial CDN JSON, ~15-min delayed).

Primary: https://cdn-api.cboe.com/api/global/delayed_quotes/options/{SYM}.json
  — underlying print + full chain with bid/ask/iv/delta/gamma/vega/theta/OI
    per OCC symbol (e.g. SPY261130P00740000). No key.

Daily closes: that JSON has no history. RV needs lookback closes, so this
adapter also pulls CBOE's public daily bars
(`https://cdn-api.cboe.com/api/global/delayed_quotes/charts/historical/SPY.json`,
JSON `{"data": [{"date", "close", ...}]}`). A CSV body (Date,...,Close,...) is
still parsed if the response is not that JSON — Stooq is not fetched (it now
serves a JS challenge). Missing/undated/stale bars abstain.

Never fabricates: missing or unusable fields stay None; stale/missing
timestamps or prices return status=unavailable with an explicit reason.

Snapshot source is always `cboe_delayed`. The cycle treats that tag as
shadow / record-only (see core.shadow).
"""

from __future__ import annotations

import json

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

SOURCE = "cboe_delayed"
OPTIONS_URL = "https://cdn-api.cboe.com/api/global/delayed_quotes/options/{symbol}.json"
BARS_URL = "https://cdn-api.cboe.com/api/global/delayed_quotes/charts/historical/{symbol}.json"
MAX_AGE = timedelta(minutes=45)
MAX_BAR_LAG_DAYS = 10  # last completed daily bar vs snapshot date (weekends/holidays)
_UA = {"User-Agent": "options-trading-bot/cboe-shadow"}


def _f(x: Any) -> float | None:
    try:
        return None if x is None or x == "" else float(x)
    except (TypeError, ValueError):
        return None


def iv_decimal(raw: Any) -> float | None:
    """CBOE `iv` is usually percent (18.5); keep values already in 0-1 as decimals.

    Values <= 0 are missing. Values > 1 are treated as percent. This never
    invents IV when the field is absent.
    """
    iv = _f(raw)
    if iv is None or iv <= 0:
        return None
    return round(iv / 100.0 if iv > 1.0 else iv, 6)


def parse_cboe_ts(raw: Any) -> datetime | None:
    """Parse a CBOE timestamp. Naive strings are America/New_York (quote page)."""
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    dt: datetime | None
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        dt = None
        for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
            try:
                dt = datetime.strptime(s[:19], fmt)
                break
            except ValueError:
                continue
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ET)
    return dt.astimezone(timezone.utc)


def parse_bar_date(raw: Any) -> date | None:
    """Parse a daily-bar date. Unparseable values are missing, not guessed."""
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    if "T" in s:
        s = s.split("T", 1)[0]
    for fmt in ("%Y-%m-%d", "%Y%m%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(s[:10] if fmt != "%Y%m%d" else s[:8], fmt).date()
        except ValueError:
            continue
    return None


def closes_from_bars_text(text: str, *, today: date, n: int) -> tuple[list[float], str | None]:
    """Parse CBOE historical JSON or a Date/OHLCV CSV. Never invents closes.

    Drops today/future (incomplete session). Last bar older than MAX_BAR_LAG_DAYS
    returns a stale reason. Rows without a parseable date or a positive close
    are skipped so they cannot scramble the RV series.
    """
    pairs = _pairs_from_json(text)
    if pairs is None:
        pairs = _pairs_from_csv(text)
    by_date: dict[date, float] = {}
    for d, px in pairs:
        if d < today:
            by_date[d] = px
    ordered = sorted(by_date.items())
    if not ordered:
        return [], None
    last = ordered[-1][0]
    if (today - last).days > MAX_BAR_LAG_DAYS:
        return [], (f"historical_bars_stale last={last.isoformat()} today={today.isoformat()}"
                    f" max_lag_d={MAX_BAR_LAG_DAYS}")
    return [px for _, px in ordered[-n:]], None


def _pairs_from_json(text: str) -> list[tuple[date, float]] | None:
    try:
        raw = json.loads(text)
    except ValueError:
        return None
    if not (isinstance(raw, dict) and isinstance(raw.get("data"), list)):
        return None
    out: list[tuple[date, float]] = []
    for r in raw["data"]:
        if not isinstance(r, dict):
            continue
        d, px = parse_bar_date(r.get("date")), _f(r.get("close"))
        if d is not None and px is not None and px > 0:
            out.append((d, px))
    return out


def _pairs_from_csv(text: str) -> list[tuple[date, float]]:
    out: list[tuple[date, float]] = []
    for line in text.splitlines()[1:]:
        parts = line.split(",")
        if len(parts) < 5:
            continue
        d, px = parse_bar_date(parts[0]), _f(parts[4])
        if d is not None and px is not None and px > 0:
            out.append((d, px))
    return out


class VendorError(RuntimeError):
    pass


class CboeMarketState:
    def __init__(
        self,
        *,
        client: httpx.Client | None = None,
        today: date | None = None,
        now: Any = None,
        max_age: timedelta = MAX_AGE,
        options_url: str = OPTIONS_URL,
        bars_url: str = BARS_URL,
    ) -> None:
        self.client = client or httpx.Client(timeout=20.0, headers=_UA, follow_redirects=True)
        self._today = today
        self._now = now or (lambda: datetime.now(timezone.utc))
        self.max_age = max_age
        self.options_url = options_url
        self.bars_url = bars_url
        self.source = SOURCE

    def _get(self, url: str) -> httpx.Response:
        r = self.client.get(url)
        if r.status_code != 200:
            raise VendorError(f"http_{r.status_code} {url.split('://', 1)[-1][:80]}: {r.text[:200]}")
        return r

    def snapshot(self, rules: DeterministicRules, *, held_legs: list[dict[str, Any]]) -> MarketSnapshot:
        try:
            return self._snapshot(rules, held_legs)
        except VendorError as exc:
            return unavailable(rules.underlying, self.source, f"cboe_error: {exc}")
        except Exception as exc:
            log.warning("CBOE snapshot failed: %s", exc)
            return unavailable(rules.underlying, self.source, f"cboe_exception: {type(exc).__name__}: {exc}")

    def _snapshot(self, rules: DeterministicRules, held_legs: list[dict[str, Any]]) -> MarketSnapshot:
        und = rules.underlying
        today = self._today or datetime.now(ET).date()
        now = self._now()
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)

        raw = self._get(self.options_url.format(symbol=und)).json()
        data = raw.get("data") if isinstance(raw, dict) else None
        if not isinstance(data, dict):
            return unavailable(und, self.source, "cboe_malformed: missing data object")

        quote_ts = parse_cboe_ts(data.get("last_trade_time")) or parse_cboe_ts(raw.get("timestamp"))
        if quote_ts is None:
            return unavailable(und, self.source, "cboe_timestamp_missing")
        age = now - quote_ts
        if age < timedelta(seconds=-60):
            return unavailable(und, self.source, f"cboe_timestamp_in_future age_s={age.total_seconds():.0f}",
                               [], quote_ts.isoformat(timespec="seconds"))
        if age > self.max_age:
            return unavailable(
                und, self.source,
                f"cboe_stale_quotes age_s={int(age.total_seconds())} max_s={int(self.max_age.total_seconds())}",
                [], quote_ts.isoformat(timespec="seconds"),
            )
        as_of = quote_ts.isoformat(timespec="seconds")

        price = _f(data.get("current_price"))
        if price is None or price <= 0:
            bid, ask = _f(data.get("bid")), _f(data.get("ask"))
            if bid and ask and bid > 0 and ask > 0:
                price = (bid + ask) / 2.0
        if price is None or price <= 0:
            return unavailable(und, self.source, "no_underlying_price", [], as_of)

        closes, bars_err = self._daily_closes(und, rules.signals.rv_lookback_days + 5, today)
        if bars_err:
            return unavailable(und, self.source, bars_err, [], as_of)
        if len(closes) < rules.signals.rv_lookback_days + 1:
            return unavailable(und, self.source, f"historical_bars_unavailable n={len(closes)}", [], as_of)

        options = data.get("options")
        if not isinstance(options, list) or not options:
            return unavailable(und, self.source, "cboe_malformed: missing options array", [], as_of)

        contracts, quotes = _map_chain(options, und)
        if not contracts:
            return unavailable(und, self.source, "no_option_contracts_in_window", [], as_of)

        # Restrict to the DTE window before pick_expiry (CBOE dumps every expiry).
        w = window(rules, price, today)
        lo, hi = w["exp_gte"].strftime("%Y%m%d"), w["exp_lte"].strftime("%Y%m%d")
        in_window = [c for c in contracts if lo <= c.expiry <= hi]
        expiry = pick_expiry(in_window, rules, today)
        if expiry is None:
            return unavailable(und, self.source, "no_option_contracts_in_window", [], as_of)
        chain = grid(in_window, expiry, price, rules.structure.strike_step)

        held_occ = {l["occ"] for l in held_legs if l.get("occ")}
        held_quotes = {occ: quotes[occ] for occ in held_occ if occ in quotes}

        snap = assemble(rules=rules, source=self.source, price=price, closes=closes, expiry=expiry,
                        chain=chain, quotes=quotes, held_quotes=held_quotes, as_of=as_of)
        if not any(o.delta is not None and o.mid is not None for o in snap.options):
            return unavailable(und, self.source, "no_option_greeks_or_bid_ask", [], as_of)
        return snap

    def _daily_closes(self, symbol: str, n: int, today: date) -> tuple[list[float], str | None]:
        url = self.bars_url.format(symbol=symbol.upper() if "cboe.com" in self.bars_url else symbol.lower())
        return closes_from_bars_text(self._get(url).text, today=today, n=n)


def _map_chain(options: list[dict], underlying: str) -> tuple[list[Contract], dict[str, Quote]]:
    contracts: list[Contract] = []
    quotes: dict[str, Quote] = {}
    for raw in options:
        if not isinstance(raw, dict):
            continue
        occ = str(raw.get("option") or "").strip()
        if len(occ) < 16:
            continue
        try:
            root, expiry, right, strike = parse_occ(occ)
        except (ValueError, IndexError):
            continue
        if root != underlying or right not in ("C", "P"):
            continue
        contracts.append(Contract(occ=occ, expiry=expiry, right=right, strike=strike,
                                  open_interest=_f(raw.get("open_interest"))))
        quotes[occ] = Quote(
            bid=_f(raw.get("bid")), ask=_f(raw.get("ask")),
            delta=_f(raw.get("delta")), iv=iv_decimal(raw.get("iv")),
            gamma=_f(raw.get("gamma")), vega=_f(raw.get("vega")), theta=_f(raw.get("theta")),
        )
    return contracts, quotes


def probe_line(snap: MarketSnapshot) -> str:
    """One-line summary for a live fetch (or a recorded snapshot)."""
    n_ok = sum(1 for o in snap.options if o.delta is not None and o.mid is not None)
    return (
        f"source={snap.source} status={snap.status} reason={snap.reason} "
        f"as_of={snap.as_of} {snap.underlying}={snap.underlying_price} "
        f"expiry={snap.expiry} options={len(snap.options)} usable={n_ok} "
        f"closes={len(snap.daily_closes)}"
    )


if __name__ == "__main__":
    from core.strategy_loader import load

    rules = load("strategies/active/spy-defined-risk-rr.yaml").rules
    snap = CboeMarketState().snapshot(rules, held_legs=[])
    print(probe_line(snap))
