"""Unit tests for OCC symbols, chain selection, quotes, and fill times.

Mocked ib_insync objects only — no Gateway.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from integrations.ibkr.occ import format_occ_symbol, make_option, parse_occ_symbol
from integrations.ibkr.option_quotes import (
    STATUS_COMPETING_LIVE_SESSION,
    STATUS_TIMEOUT,
    extract_quote,
    request_quotes,
    resolve_order_price,
    status_from_errors,
    wait_until,
    IbError,
)
from integrations.ibkr.options_data import (
    expiries_in_window,
    get_option_contracts,
    nearest_strikes,
    select_option_chain,
)
from integrations.ibkr.orders import _build_contract, create_order, fill_to_record
from utils.time_et import ib_exec_time_to_et


class FakeClock:
    def __init__(self, t: float = 0.0) -> None:
        self.t = t

    def now(self) -> float:
        return self.t

    def sleep(self, dt: float) -> None:
        self.t += dt


class FakeEvent:
    def __init__(self) -> None:
        self._subs: list = []

    def __iadd__(self, fn):
        self._subs.append(fn)
        return self

    def __isub__(self, fn):
        self._subs.remove(fn)
        return self

    def emit(self, *args) -> None:
        for fn in list(self._subs):
            fn(*args)


class FakeTicker:
    def __init__(self, **kwargs) -> None:
        self.bid = float("nan")
        self.ask = float("nan")
        self.last = float("nan")
        self.close = float("nan")
        self.bidSize = float("nan")
        self.askSize = float("nan")
        self.modelGreeks = None
        self.bidGreeks = None
        self.askGreeks = None
        self.callOpenInterest = float("nan")
        self.putOpenInterest = float("nan")
        self.impliedVolatility = float("nan")
        self.marketDataType = 1
        for key, value in kwargs.items():
            setattr(self, key, value)


class FakeIB:
    def __init__(self) -> None:
        self.errorEvent = FakeEvent()
        self.chains: list = []
        self.details_by_expiry: dict[str, list] = {}
        self.mdt = None
        self.req_calls: list = []
        self.cancelled: list = []
        self.ticker_factory = lambda contract: FakeTicker()

    def qualifyContracts(self, *contracts):
        for contract in contracts:
            if not getattr(contract, "conId", 0):
                contract.conId = 42
        return list(contracts)

    def reqSecDefOptParams(self, *args):
        return self.chains

    def reqContractDetails(self, probe):
        return self.details_by_expiry.get(probe.lastTradeDateOrContractMonth, [])

    def reqMarketDataType(self, mdt):
        self.mdt = mdt

    def reqMktData(self, contract, genericTickList="", snapshot=False, regulatorySnapshot=False):
        assert snapshot is False
        self.req_calls.append((contract, genericTickList, snapshot))
        return self.ticker_factory(contract)

    def cancelMktData(self, contract):
        self.cancelled.append(contract)

    def sleep(self, _dt):
        return None


def _details(underlying, expiry, strike, right, trading_class=None):
    contract = make_option(underlying, expiry, strike, right, trading_class=trading_class)
    contract.conId = int(strike * 10)
    return SimpleNamespace(contract=contract)


class TestOccRoundTrip:
    def test_compact_yymmdd(self):
        symbol = format_occ_symbol("SPY", "2026-10-23", "C", 778)
        assert symbol == "SPY261023C00778000"
        parts = parse_occ_symbol(symbol)
        assert parts.underlying == "SPY"
        assert parts.expiry_yyyymmdd == "20261023"
        assert parts.right == "C"
        assert parts.strike == 778.0
        assert parts.occ_symbol == symbol

    def test_padded_osi(self):
        parts = parse_occ_symbol("SPY   261023C00778000")
        assert parts.underlying == "SPY"
        assert parts.occ_symbol == "SPY261023C00778000"

    def test_eight_digit_date_is_not_spy20(self):
        parts = parse_occ_symbol("SPY20261023C00778000")
        assert parts.underlying == "SPY"
        assert parts.expiry_yyyymmdd == "20261023"
        assert parts.occ_symbol == "SPY261023C00778000"

    def test_orders_parser_agrees(self):
        contract = _build_contract("SPY", "SPY261023C00778000")
        assert contract.symbol == "SPY"
        assert contract.lastTradeDateOrContractMonth == "20261023"
        assert contract.strike == 778.0
        assert contract.right == "C"
        assert contract.exchange == "SMART"
        assert contract.currency == "USD"
        assert contract.multiplier == "100"
        assert contract.tradingClass == "SPY"

    def test_make_option_fields(self):
        opt = make_option("SPY", "20261023", 778, "P")
        assert opt.secType == "OPT"
        assert opt.exchange == "SMART"
        assert opt.currency == "USD"
        assert opt.multiplier == "100"
        assert opt.tradingClass == "SPY"

    def test_fallback_sets_exchange(self):
        opt = _build_contract("SPY", "not-an-occ-symbol")
        assert opt.localSymbol == "not-an-occ-symbol"
        assert opt.exchange == "SMART"
        assert opt.currency == "USD"


class TestChainSelection:
    def test_filters_trading_class(self):
        spy = SimpleNamespace(exchange="SMART", tradingClass="SPY", expirations=["20261023"], strikes=[100.0])
        weekly = SimpleNamespace(exchange="SMART", tradingClass="2SPY", expirations=["20261023"], strikes=[100.0])
        chosen = select_option_chain([weekly, spy], trading_class="SPY")
        assert chosen is spy

    def test_spx_not_spxw(self):
        spx = SimpleNamespace(exchange="SMART", tradingClass="SPX", expirations=[], strikes=[])
        spxw = SimpleNamespace(exchange="CBOE", tradingClass="SPXW", expirations=[], strikes=[])
        assert select_option_chain([spxw, spx], trading_class="SPX") is spx
        assert select_option_chain([spxw], trading_class="SPX") is None

    def test_dte_window_and_nearest_strikes(self):
        picked = expiries_in_window(
            ["20261009", "20261023", "20261120", "20270115"],
            expiration_date_gte="2026-10-17",
            expiration_date_lte="2026-11-07",
            max_expiries=2,
            today=date(2026, 10, 10),
        )
        assert picked == ["20261023"]
        assert nearest_strikes([100, 770, 778, 780, 900], 778.0, 3) == [770.0, 778.0, 780.0]

    def test_real_expiry_strikes_not_union(self):
        ib = FakeIB()
        ib.chains = [
            SimpleNamespace(
                exchange="SMART",
                tradingClass="SPY",
                expirations=["20261023", "20261120"],
                strikes=[100.0, 200.0, 770.0, 778.0, 900.0],
            )
        ]
        ib.details_by_expiry = {
            "20261023": [
                _details("SPY", "20261023", 770, "C"),
                _details("SPY", "20261023", 778, "C"),
                _details("SPY", "20261023", 778, "P"),
                _details("SPY", "20261023", 780, "C"),
            ]
        }
        rows = get_option_contracts(
            ib,
            "SPY",
            expiration_date_gte="2026-10-17",
            expiration_date_lte="2026-11-07",
            n_strikes=2,
            max_expiries=2,
            underlying_price=778.0,
            today=date(2026, 10, 10),
            include_quotes=False,
        )
        symbols = {r["symbol"] for r in rows}
        assert "SPY261023C00778000" in symbols
        assert not any("C00100000" in s for s in symbols)
        assert all(r["expiration_date"] == "2026-10-23" for r in rows)


class TestNanFailClosed:
    def test_nan_last_and_close_does_not_pass(self):
        ticker = FakeTicker()
        with pytest.raises(ValueError, match="no finite"):
            resolve_order_price(ticker, is_option=False)

    def test_option_uses_mid_only(self):
        ticker = FakeTicker(bid=1.5, ask=1.7, last=9.9, close=9.8)
        assert resolve_order_price(ticker, is_option=True) == pytest.approx(1.6)

    def test_create_order_nan_does_not_place(self):
        ib = MagicMock()
        ib.reqMktData.return_value = FakeTicker()
        ib.qualifyContracts.side_effect = lambda c: [c]
        with pytest.raises(ValueError, match="Cannot determine price"):
            create_order(
                ib,
                symbol="SPY",
                notional=1000,
                side="buy",
                contract_symbol="SPY261023C00778000",
                quote_timeout=0,
            )
        ib.placeOrder.assert_not_called()
        ib.cancelMktData.assert_called()


class TestErrorCodesAndTimeout:
    def test_status_10197(self):
        status = status_from_errors(
            [IbError(code=10197, message="No market data during competing live session")],
            has_bid_ask=False,
            has_greeks=False,
            require_greeks=True,
            timed_out=True,
        )
        assert status == STATUS_COMPETING_LIVE_SESSION

    def test_timeout_without_errors(self):
        clock = FakeClock()
        assert wait_until(lambda: False, timeout=1.0, interval=0.5, sleep=clock.sleep, clock=clock.now) is False
        assert clock.t >= 1.0

    def test_request_quotes_surfaces_10197(self):
        ib = FakeIB()
        clock = FakeClock()

        def sleep(dt):
            clock.sleep(dt)
            ib.errorEvent.emit(1, 10197, "No market data during competing live session", None)

        contract = make_option("SPY", "20261023", 778, "C")
        quotes = request_quotes(
            ib,
            [contract],
            timeout=1.0,
            require_greeks=True,
            sleep=sleep,
            clock=clock.now,
        )
        assert quotes[0].status == STATUS_COMPETING_LIVE_SESSION
        assert quotes[0].errors[0].code == 10197
        assert ib.cancelled
        assert ib.req_calls[0][1] == "101"
        assert ib.req_calls[0][2] is False

    def test_wait_succeeds_when_bid_ask_arrive(self):
        ticker = FakeTicker()
        clock = FakeClock()

        def sleep(dt):
            clock.sleep(dt)
            ticker.bid = 2.0
            ticker.ask = 2.2

        assert wait_until(
            lambda: ticker.bid == 2.0,
            timeout=2.0,
            interval=0.25,
            sleep=sleep,
            clock=clock.now,
        )

    def test_extract_quote_timeout_status(self):
        quote = extract_quote(
            make_option("SPY", "20261023", 778, "C"),
            FakeTicker(),
            timed_out=True,
            require_greeks=True,
        )
        assert quote.status == STATUS_TIMEOUT
        assert quote.bid is None


class TestFillTimeEt:
    def test_utc_datetime_to_et(self):
        et = ib_exec_time_to_et(datetime(2026, 10, 6, 13, 35, 19, tzinfo=timezone.utc))
        assert et is not None
        assert et.isoformat().startswith("2026-10-06T09:35:19")

    def test_naive_ib_string_is_utc(self):
        et = ib_exec_time_to_et("20261006 13:35:19")
        assert et is not None
        assert et.hour == 9
        assert et.minute == 35

    def test_fill_to_record(self):
        fill = SimpleNamespace(
            contract=SimpleNamespace(symbol="SPY"),
            execution=SimpleNamespace(
                execId="00025b49.6ac58ef0.01.01",
                orderId=4,
                time=datetime(2026, 10, 6, 13, 35, 19, tzinfo=timezone.utc),
                side="BOT",
                shares=1.0,
                price=778.25,
                exchange="ARCA",
            ),
            time=datetime(2026, 10, 6, 13, 35, 19, tzinfo=timezone.utc),
        )
        rec = fill_to_record(fill)
        assert rec["time_et"].startswith("2026-10-06T09:35:19")
        assert rec["exec_id"] == "00025b49.6ac58ef0.01.01"


class TestClientReadonly:
    def test_connect_passes_client_id_and_readonly(self, monkeypatch):
        import integrations.ibkr.client as client_mod

        fake = MagicMock()
        monkeypatch.setattr(client_mod, "IB", lambda: fake)
        client_mod._ib = None
        client_mod._conn_params = None
        client_mod.create_ib_client("paper", client_id=7, readonly=True)
        assert fake.connect.call_args.kwargs["clientId"] == 7
        assert fake.connect.call_args.kwargs["readonly"] is True
        assert client_mod._ib is None


class TestOptionsFlowOi:
    def test_uses_real_oi_and_iv(self, monkeypatch):
        from integrations.data.options_flow import analyze_options_flow

        monkeypatch.setattr(
            "integrations.data.options_flow.get_options_chain",
            lambda *a, **k: [
                {"type": "call", "open_interest": 120, "implied_vol": 0.18, "quote_status": "ok"},
                {"type": "put", "open_interest": 80, "implied_vol": 0.22, "quote_status": "ok"},
            ],
        )
        out = analyze_options_flow(MagicMock(), "SPY")
        assert out["call_open_interest"] == 120
        assert out["put_open_interest"] == 80
        assert out["put_call_ratio"] == 0.667
        assert out["avg_implied_vol"] == 0.2
        assert out["quote_status"] == "ok"
