"""Streaming IB option/stock quotes and model Greeks.

Uses reqMktData streams (generic ticks are illegal on snapshots).
Fail closed: NaN/missing bid-ask is a status, not a silent number.
"""

from __future__ import annotations

import math
import os
import time
from collections.abc import Callable, Iterable
from contextlib import contextmanager
from typing import Any, Iterator

from ib_insync import IB, Contract
from pydantic import BaseModel, Field

from integrations.ibkr.occ import format_occ_symbol
from utils.logging import get_logger

log = get_logger(__name__)

STOCK_GENERIC_TICKS = "100,101,104,106"
OPTION_GENERIC_TICKS = "101"

WATCHED_ERROR_CODES = frozenset({10197, 354, 10090, 162, 10167})

DEFAULT_MARKET_DATA_TYPE = 1
DEFAULT_QUOTE_TIMEOUT = 10.0
DEFAULT_POLL_INTERVAL = 0.25

STATUS_OK = "ok"
STATUS_TIMEOUT = "timeout"
STATUS_NO_BID_ASK = "no_bid_ask"
STATUS_NO_GREEKS = "no_greeks"
STATUS_COMPETING_LIVE_SESSION = "competing_live_session"
STATUS_NOT_SUBSCRIBED = "not_subscribed"
STATUS_HISTORICAL_SESSION_CONFLICT = "historical_session_conflict"
STATUS_ERROR = "error"


class OptionGreeks(BaseModel):
    delta: float | None = None
    gamma: float | None = None
    vega: float | None = None
    theta: float | None = None
    implied_vol: float | None = None
    und_price: float | None = None


class IbError(BaseModel):
    code: int
    message: str


class MarketQuote(BaseModel):
    symbol: str
    sec_type: str = "STK"
    bid: float | None = None
    ask: float | None = None
    mid: float | None = None
    last: float | None = None
    close: float | None = None
    bid_size: float | None = None
    ask_size: float | None = None
    market_data_type: int | None = None
    model_greeks: OptionGreeks | None = None
    bid_greeks: OptionGreeks | None = None
    ask_greeks: OptionGreeks | None = None
    open_interest: float | None = None
    implied_vol: float | None = None
    errors: list[IbError] = Field(default_factory=list)
    status: str = STATUS_OK


def is_finite_number(value: Any) -> bool:
    if value is None:
        return False
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def is_finite_price(value: Any) -> bool:
    return is_finite_number(value) and float(value) > 0


def finite_or_none(value: Any) -> float | None:
    if not is_finite_number(value):
        return None
    return float(value)


def mid_price(bid: Any, ask: Any) -> float | None:
    if is_finite_price(bid) and is_finite_price(ask):
        return (float(bid) + float(ask)) / 2.0
    return None


def resolve_order_price(ticker: Any, *, is_option: bool) -> float:
    """Price used to convert notional → qty. Options: mid only. Else last/close/mid."""
    if is_option:
        mid = mid_price(getattr(ticker, "bid", None), getattr(ticker, "ask", None))
        if mid is None:
            raise ValueError("Cannot determine price: no finite option bid/ask")
        return mid
    last = getattr(ticker, "last", None)
    if is_finite_price(last):
        return float(last)
    close = getattr(ticker, "close", None)
    if is_finite_price(close):
        return float(close)
    mid = mid_price(getattr(ticker, "bid", None), getattr(ticker, "ask", None))
    if mid is None:
        raise ValueError("Cannot determine price: no finite last/close/bid-ask")
    return mid


def ticker_ready_for_order(ticker: Any, *, is_option: bool) -> bool:
    if is_option:
        return is_finite_price(getattr(ticker, "bid", None)) and is_finite_price(
            getattr(ticker, "ask", None)
        )
    return (
        is_finite_price(getattr(ticker, "last", None))
        or is_finite_price(getattr(ticker, "close", None))
        or (
            is_finite_price(getattr(ticker, "bid", None))
            and is_finite_price(getattr(ticker, "ask", None))
        )
    )


def ticker_has_bid_ask(ticker: Any) -> bool:
    return is_finite_price(getattr(ticker, "bid", None)) and is_finite_price(
        getattr(ticker, "ask", None)
    )


def configured_market_data_type(override: int | None = None) -> int:
    if override is not None:
        return int(override)
    return int(os.environ.get("IB_MARKET_DATA_TYPE", str(DEFAULT_MARKET_DATA_TYPE)))


def ensure_market_data_type(ib: IB, market_data_type: int | None = None) -> int:
    mdt = configured_market_data_type(market_data_type)
    ib.reqMarketDataType(mdt)
    return mdt


def generic_ticks_for(contract: Any) -> str:
    sec = (getattr(contract, "secType", "") or "").upper()
    if sec == "OPT":
        return OPTION_GENERIC_TICKS
    return STOCK_GENERIC_TICKS


def wait_until(
    predicate: Callable[[], bool],
    *,
    timeout: float,
    interval: float = DEFAULT_POLL_INTERVAL,
    sleep: Callable[[float], None],
    clock: Callable[[], float],
) -> bool:
    """Poll predicate until true or timeout. Uses ib.sleep in production (processes IB events)."""
    start = clock()
    while True:
        if predicate():
            return True
        if clock() - start >= timeout:
            return False
        sleep(interval)


def _greeks(comp: Any) -> OptionGreeks | None:
    if comp is None:
        return None
    greeks = OptionGreeks(
        delta=finite_or_none(getattr(comp, "delta", None)),
        gamma=finite_or_none(getattr(comp, "gamma", None)),
        vega=finite_or_none(getattr(comp, "vega", None)),
        theta=finite_or_none(getattr(comp, "theta", None)),
        implied_vol=finite_or_none(getattr(comp, "impliedVol", None)),
        und_price=finite_or_none(getattr(comp, "undPrice", None)),
    )
    if all(v is None for v in greeks.model_dump().values()):
        return None
    return greeks


def _option_open_interest(ticker: Any, right: str | None) -> float | None:
    call_oi = finite_or_none(getattr(ticker, "callOpenInterest", None))
    put_oi = finite_or_none(getattr(ticker, "putOpenInterest", None))
    if call_oi is not None and call_oi < 0:
        call_oi = None
    if put_oi is not None and put_oi < 0:
        put_oi = None
    right_u = (right or "").upper()
    if right_u in ("C", "CALL"):
        return call_oi
    if right_u in ("P", "PUT"):
        return put_oi
    if call_oi is not None and put_oi is not None:
        return call_oi + put_oi
    return call_oi if call_oi is not None else put_oi


def _quote_symbol(contract: Any) -> str:
    sec = (getattr(contract, "secType", "") or "").upper()
    if sec == "OPT":
        try:
            return format_occ_symbol(
                contract.symbol,
                contract.lastTradeDateOrContractMonth,
                contract.right,
                contract.strike,
            )
        except Exception:
            return getattr(contract, "localSymbol", None) or str(contract.symbol)
    return str(getattr(contract, "symbol", "") or "")


def status_from_errors(
    errors: Iterable[IbError],
    *,
    has_bid_ask: bool,
    has_greeks: bool,
    require_greeks: bool,
    timed_out: bool,
) -> str:
    codes = {e.code for e in errors}
    if 10197 in codes:
        return STATUS_COMPETING_LIVE_SESSION
    if 162 in codes:
        return STATUS_HISTORICAL_SESSION_CONFLICT
    if codes & {354, 10090, 10167}:
        return STATUS_NOT_SUBSCRIBED
    if not has_bid_ask:
        if timed_out:
            return STATUS_TIMEOUT
        return STATUS_NO_BID_ASK
    if require_greeks and not has_greeks:
        return STATUS_NO_GREEKS if not timed_out else STATUS_TIMEOUT
    if codes:
        return STATUS_ERROR
    return STATUS_OK


@contextmanager
def capture_ib_errors(ib: IB) -> Iterator[list[IbError]]:
    captured: list[IbError] = []

    def on_error(req_id: Any, error_code: Any, error_string: Any, *rest: Any) -> None:
        try:
            code = int(error_code)
        except (TypeError, ValueError):
            return
        if code not in WATCHED_ERROR_CODES:
            return
        captured.append(IbError(code=code, message=str(error_string)))

    event = getattr(ib, "errorEvent", None)
    subscribed = False
    if event is not None:
        try:
            event += on_error
            subscribed = True
        except TypeError:
            subscribed = False
    try:
        yield captured
    finally:
        if subscribed:
            try:
                event -= on_error
            except Exception:
                pass


def _ticker_ready(ticker: Any, *, require_bid_ask: bool, require_greeks: bool) -> bool:
    if require_bid_ask and not ticker_has_bid_ask(ticker):
        return False
    if require_greeks and getattr(ticker, "modelGreeks", None) is None:
        return False
    if not require_bid_ask and not require_greeks:
        return ticker_has_bid_ask(ticker) or is_finite_price(getattr(ticker, "last", None))
    return True


def extract_quote(
    contract: Any,
    ticker: Any,
    *,
    errors: list[IbError] | None = None,
    require_greeks: bool = False,
    timed_out: bool = False,
    requested_mdt: int | None = None,
) -> MarketQuote:
    errors = list(errors or [])
    bid = finite_or_none(getattr(ticker, "bid", None))
    ask = finite_or_none(getattr(ticker, "ask", None))
    if bid is not None and bid <= 0:
        bid = None
    if ask is not None and ask <= 0:
        ask = None
    last = finite_or_none(getattr(ticker, "last", None))
    if last is not None and last <= 0:
        last = None
    bid_size = finite_or_none(getattr(ticker, "bidSize", None))
    ask_size = finite_or_none(getattr(ticker, "askSize", None))
    close = finite_or_none(getattr(ticker, "close", None))
    if close is not None and close <= 0:
        close = None
    model = _greeks(getattr(ticker, "modelGreeks", None))
    bid_g = _greeks(getattr(ticker, "bidGreeks", None))
    ask_g = _greeks(getattr(ticker, "askGreeks", None))
    iv = None
    if model and model.implied_vol is not None:
        iv = model.implied_vol
    else:
        iv = finite_or_none(getattr(ticker, "impliedVolatility", None))
    right = getattr(contract, "right", None)
    has_bid_ask = bid is not None and ask is not None
    status = status_from_errors(
        errors,
        has_bid_ask=has_bid_ask,
        has_greeks=model is not None,
        require_greeks=require_greeks,
        timed_out=timed_out,
    )
    mdt = getattr(ticker, "marketDataType", None)
    if not is_finite_number(mdt):
        mdt = requested_mdt
    else:
        mdt = int(mdt)
    return MarketQuote(
        symbol=_quote_symbol(contract),
        sec_type=(getattr(contract, "secType", "") or "STK").upper() or "STK",
        bid=bid,
        ask=ask,
        mid=mid_price(bid, ask),
        last=last,
        close=close,
        bid_size=bid_size,
        ask_size=ask_size,
        market_data_type=mdt,
        model_greeks=model,
        bid_greeks=bid_g,
        ask_greeks=ask_g,
        open_interest=_option_open_interest(ticker, right),
        implied_vol=iv,
        errors=errors,
        status=status,
    )


def request_quotes(
    ib: IB,
    contracts: list[Any],
    *,
    timeout: float = DEFAULT_QUOTE_TIMEOUT,
    require_greeks: bool = False,
    require_bid_ask: bool = True,
    market_data_type: int | None = None,
    generic_ticks: str | None = None,
    sleep: Callable[[float], None] | None = None,
    clock: Callable[[], float] | None = None,
) -> list[MarketQuote]:
    """Subscribe, wait until bid/ask (and modelGreeks if requested), cancel."""
    if not contracts:
        return []
    mdt = ensure_market_data_type(ib, market_data_type)
    sleeper = sleep or ib.sleep
    clk = clock or time.monotonic
    tickers: list[Any] = []
    with capture_ib_errors(ib) as errors:
        try:
            for contract in contracts:
                ticks = generic_ticks if generic_ticks is not None else generic_ticks_for(contract)
                tickers.append(ib.reqMktData(contract, ticks, False, False))
            ready = wait_until(
                lambda: all(
                    _ticker_ready(t, require_bid_ask=require_bid_ask, require_greeks=require_greeks)
                    for t in tickers
                ),
                timeout=timeout,
                sleep=sleeper,
                clock=clk,
            )
            timed_out = not ready
            return [
                extract_quote(
                    contract,
                    ticker,
                    errors=errors,
                    require_greeks=require_greeks,
                    timed_out=timed_out,
                    requested_mdt=mdt,
                )
                for contract, ticker in zip(contracts, tickers)
            ]
        finally:
            for contract in contracts:
                try:
                    ib.cancelMktData(contract)
                except Exception as exc:
                    log.debug("cancelMktData failed: %s", exc)


def request_quote(
    ib: IB,
    contract: Contract,
    *,
    timeout: float = DEFAULT_QUOTE_TIMEOUT,
    require_greeks: bool = False,
    require_bid_ask: bool = True,
    market_data_type: int | None = None,
    generic_ticks: str | None = None,
    sleep: Callable[[float], None] | None = None,
    clock: Callable[[], float] | None = None,
) -> MarketQuote:
    quotes = request_quotes(
        ib,
        [contract],
        timeout=timeout,
        require_greeks=require_greeks,
        require_bid_ask=require_bid_ask,
        market_data_type=market_data_type,
        generic_ticks=generic_ticks,
        sleep=sleep,
        clock=clock,
    )
    return quotes[0]
