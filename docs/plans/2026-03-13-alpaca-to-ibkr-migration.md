# Migration Plan: Alpaca → Interactive Brokers Canada
**Date:** 2026-03-13

## Context

Alpaca does not support Canadian residents. The user needs to migrate to Interactive Brokers Canada (IBKR), which is regulated by CIRO, is CIPF-member, and fully supports Canadian accounts. The migration must preserve all existing bot behavior (paper/live toggle, risk controls, PydanticAI agent tools, strategy YAML execution) while swapping out the broker integration layer.

---

## Recommended Approach: `ib_async` (TWS API)

Use **`ib_async`** — the actively-maintained 2025 community successor to `ib_insync` — wrapping IBKR's Trader Workstation (TWS) API.

**Why `ib_async` over IBKR Web API:**
- Full feature coverage: historical bars, live quotes, options chains, order management, account data
- Native `asyncio` — matches PydanticAI's async architecture
- Built-in paper/live toggle via Gateway config (no code change needed)
- Battle-tested for algo trading
- Web API requires OAuth 2.0 + running a Java gateway anyway; TWS API is simpler to run via IB Gateway (headless Docker-friendly)

**IB Gateway requirement:** IBKR's IB Gateway app must be running (locally or in Docker) for the TWS API to connect. This is the main operational difference from Alpaca. A `docker-compose.yml` for `ghcr.io/gnzsnz/ib-gateway` will be added.

---

## Scope Note

**Primary focus: Options trading** (user confirmed). US stocks are supported as option underlyings. Crypto support is kept as a stub but de-prioritized.

---

## Key Technical Differences to Resolve

| Alpaca | IBKR (`ib_async`) |
|--------|-------------------|
| Auth via API Key/Secret env vars | Auth via IB Gateway login (username/password in gateway config) |
| `paper=True` flag on client | Separate paper username in IB Gateway |
| `notional`-based orders (dollars) | `quantity`-based orders; must compute `qty = notional / current_price` |
| Simple string symbols (`"AAPL"`) | `Contract` objects (`Stock("AAPL", "SMART", "USD")`) |
| Crypto symbols: `"BTC/USD"` | `Crypto("BTC", "PAXOS", "USD")` (stub only) |
| Options: OCC symbol strings | `Option(symbol, expiry, strike, right, "SMART")` |
| Options chain: `get_option_contracts()` | `ib.reqSecDefOptParams()` + qualify contracts + `ib.reqContractDetails()` |
| Option quotes: OptionHistoricalDataClient | `ib.reqTickers()` on each Option contract for Greeks + bid/ask |
| News: Alpaca REST API | No direct equivalent → drop Alpaca news, keep Tavily only |
| `ALPACA_KEY` / `ALPACA_SECRET` | `IB_USERNAME` / `IB_PASSWORD` / `IB_GATEWAY_PORT` |

---

## Alpaca Integration Inventory (What Must Be Replaced)

The codebase has **9 Alpaca integration modules** across ~600 lines:

| Module | Alpaca APIs Used | Replacement |
|--------|-----------------|-------------|
| `integrations/alpaca/client.py` | `TradingClient(api_key, secret_key, paper=bool)` | `ib_async.IB().connectAsync(host, port)` |
| `integrations/alpaca/account.py` | `client.get_account()` → equity, cash, buying_power | `ib.accountValues()` keyed on `NetLiquidation`, `CashBalance`, `BuyingPower` |
| `integrations/alpaca/positions.py` | `client.get_all_positions()`, `client.close_position(ClosePositionRequest)` | `ib.positions()`, `ib.placeOrder(contract, MarketOrder("SELL", qty))` |
| `integrations/alpaca/orders.py` | `client.submit_order(MarketOrderRequest / LimitOrderRequest)`, `client.get_order_by_id()`, `client.get_orders()` | `ib.placeOrder()`, `ib.trades()` filtered by orderId/status |
| `integrations/alpaca/assets.py` | `client.get_all_assets(GetAssetsRequest)` | `ib.reqContractDetails(Stock("", "SMART", "USD"))` (or drop — agent tool rarely used) |
| `integrations/alpaca/market_data.py` | `StockHistoricalDataClient.get_stock_bars()`, `CryptoHistoricalDataClient.get_crypto_bars()`, `get_stock_latest_quote()` | `ib.reqHistoricalDataAsync(contract, ...)`, `ib.reqTickers(contract)` |
| `integrations/alpaca/options_data.py` | `client.get_option_contracts(GetOptionContractsRequest)`, `OptionHistoricalDataClient` | `ib.reqSecDefOptParams()` + `ib.reqContractDetails()` + `ib.reqTickers()` |
| `integrations/data/options_flow.py` | Calls `alpaca.options_data.get_options_chain(client, ...)` | Same function signature, swap client type to `IB` |
| `integrations/data/news.py` | Direct HTTP to `data.alpaca.markets/v1beta1/news` | Remove entirely; Tavily remains |

**Files outside `integrations/` that reference Alpaca:**
- `schemas/deps.py` — `alpaca: TradingClient` field
- `core/agent.py` — all 8 tools import from `integrations.alpaca.*` and access `ctx.deps.alpaca`
- `core/runner.py` — `deps.alpaca` used throughout execution loop
- `main.py` — `create_trading_client()` factory call

---

## Files to Create / Modify

### New: `integrations/ibkr/` directory (replaces `integrations/alpaca/`)

| New File | Replaces | Responsibility |
|----------|----------|----------------|
| `integrations/ibkr/__init__.py` | — | Package marker |
| `integrations/ibkr/client.py` | `integrations/alpaca/client.py` | IB async connection factory; connects to IB Gateway; paper/live via port |
| `integrations/ibkr/account.py` | `integrations/alpaca/account.py` | `get_account()` → `ib.accountValues()` + `ib.accountSummary()` |
| `integrations/ibkr/positions.py` | `integrations/alpaca/positions.py` | `list_positions()` → `ib.positions()`; `close_position()` → market sell order |
| `integrations/ibkr/orders.py` | `integrations/alpaca/orders.py` | `create_order()`, `get_order()`, `list_orders()` via `ib.placeOrder()` / `ib.trades()` |
| `integrations/ibkr/market_data.py` | `integrations/alpaca/market_data.py` | `get_stock_bars()`, `get_crypto_bars()`, `get_stock_quote()` via `ib.reqHistoricalDataAsync()` / `ib.reqTickers()` |
| `integrations/ibkr/options_data.py` | `integrations/alpaca/options_data.py` | `get_options_chain()`, `get_option_contracts()` via `ib.reqSecDefOptParams()` + `ib.reqContractDetails()` |
| `integrations/ibkr/contracts.py` | *(new helper)* | `to_stock_contract()`, `to_crypto_contract()`, `to_option_contract()` — converts symbols/params to IB `Contract` objects |

### Modified Files

| File | Change |
|------|--------|
| `schemas/deps.py` | Rename `alpaca: TradingClient` → `ib: IB`; update type import |
| `core/agent.py` | Update all 8 tool imports: `from integrations.alpaca.*` → `from integrations.ibkr.*`; update `ctx.deps.alpaca` → `ctx.deps.ib` |
| `core/runner.py` | Update imports + `deps.alpaca` → `deps.ib` references; adapt `snapshot_positions()`, `reconcile_order_and_positions()`, `_fetch_data_for_strategy()` |
| `main.py` | Replace `create_trading_client()` → `create_ib_client()`; update env vars read; update `Deps` instantiation; wrap in `asyncio.run()` if not already async |
| `integrations/data/options_flow.py` | Update import from `alpaca.options_data` → `ibkr.options_data`; update client type annotation |
| `integrations/data/news.py` | Remove `search_alpaca_news()` and its HTTP call; `aggregate_news()` falls back to Tavily only |
| `.env.example` | Replace `ALPACA_KEY/SECRET` with `IB_USERNAME`, `IB_PASSWORD`, `IB_GATEWAY_HOST`, `IB_GATEWAY_PORT` |
| `pyproject.toml` | Remove `alpaca-py`; add `ib_async` |
| `tests/test_agent.py` | Replace Alpaca mocks with `ib_async.IB` mocks |
| `tests/test_runner.py` | Replace Alpaca mocks with `ib_async.IB` mocks |

### New: Infrastructure

| File | Purpose |
|------|---------|
| `docker-compose.yml` (update existing) | Add `ib-gateway` service via `ghcr.io/gnzsnz/ib-gateway:stable` image |
| `.env.example` (updated) | IB env vars documented with comments |

---

## Implementation Steps

### Step 1 — Add `ib_async` dependency, remove `alpaca-py`
- Edit `pyproject.toml`: remove `alpaca-py >= 0.35.1`, add `ib_async >= 2.1.0`
- Run `uv sync`

### Step 2 — Create `integrations/ibkr/contracts.py`

Helper to convert string symbols → IB `Contract` objects. This is the foundation that all other IBKR modules depend on.

```python
from ib_async import Stock, Crypto, Option, Contract

def to_stock_contract(symbol: str, currency: str = "USD") -> Stock:
    return Stock(symbol, "SMART", currency)

def to_crypto_contract(symbol: str) -> Crypto:
    # "BTC/USD" -> Crypto("BTC", "PAXOS", "USD")
    base = symbol.split("/")[0]
    return Crypto(base, "PAXOS", "USD")

def to_option_contract(
    symbol: str, expiry: str, strike: float, right: str  # right: "C" or "P"
) -> Option:
    # expiry: "YYYYMMDD"
    return Option(symbol, expiry, strike, right, "SMART")
```

### Step 3 — Create `integrations/ibkr/client.py`

```python
import os
from ib_async import IB

async def create_ib_client(trading_mode: str | None = None) -> IB:
    ib = IB()
    port = int(os.environ.get(
        "IB_GATEWAY_PORT",
        4002 if trading_mode != "live" else 4001
    ))
    host = os.environ.get("IB_GATEWAY_HOST", "localhost")
    await ib.connectAsync(host, port, clientId=1)
    return ib
```

Port convention (matches IB Gateway defaults):
- `4002` → paper trading
- `4001` → live trading

### Step 4 — Create `integrations/ibkr/account.py`

Map `ib.accountValues()` to the same dict schema as current `account.py`:

```python
from ib_async import IB

def get_account(ib: IB) -> dict:
    values = {v.tag: v.value for v in ib.accountValues() if v.currency in ("USD", "CAD", "")}
    return {
        "equity":        float(values.get("NetLiquidation", 0)),
        "cash":          float(values.get("CashBalance", 0)),
        "buying_power":  float(values.get("BuyingPower", 0)),
        "currency":      values.get("Currency", "USD"),
        "trading_blocked": False,   # IB doesn't expose this flag directly
        "account_blocked": False,
    }
```

### Step 5 — Create `integrations/ibkr/positions.py`

```python
from ib_async import IB, MarketOrder
from .contracts import to_stock_contract

def list_positions(ib: IB) -> list[dict]:
    return [
        {
            "symbol":           p.contract.symbol,
            "asset_class":      "us_equity",
            "qty":              p.position,
            "avg_entry_price":  p.avgCost,
            "current_price":    None,  # fetch separately if needed
            "market_value":     p.position * p.avgCost,
            "side":             "long" if p.position > 0 else "short",
        }
        for p in ib.positions()
        if p.position != 0
    ]

async def close_position(
    ib: IB, *, symbol_or_asset_id: str,
    qty: float | None = None, percentage: float | None = None
) -> dict:
    positions = ib.positions()
    pos = next((p for p in positions if p.contract.symbol == symbol_or_asset_id), None)
    if not pos:
        raise ValueError(f"No open position for {symbol_or_asset_id}")
    close_qty = qty or (abs(pos.position) * (percentage or 100) / 100)
    action = "SELL" if pos.position > 0 else "BUY"
    trade = ib.placeOrder(pos.contract, MarketOrder(action, close_qty))
    return {"symbol": symbol_or_asset_id, "qty": close_qty, "trade_id": trade.order.orderId}
```

### Step 6 — Create `integrations/ibkr/orders.py`

Key challenge: Alpaca uses `notional` (dollar amount); IB requires `quantity`. Resolution:

```python
async def create_order(
    ib: IB, *, symbol: str, notional: float,
    side: Literal["buy", "sell"],
    order_type: Literal["market", "limit", "stop_limit"] = "market",
    time_in_force: Literal["gtc", "ioc", "day"] = "ioc",
    limit_price: float | None = None,
    stop_price: float | None = None,
) -> dict:
    contract = to_stock_contract(symbol)
    await ib.qualifyContractsAsync(contract)

    # Convert notional → quantity
    tickers = await ib.reqTickersAsync(contract)
    price = tickers[0].marketPrice() if tickers else None
    if not price:
        raise ValueError(f"Cannot get price for {symbol}")
    qty = round(notional / price, 0)

    # Build IB order
    action = side.upper()
    tif_map = {"gtc": "GTC", "ioc": "IOC", "day": "DAY"}
    if order_type == "market":
        order = MarketOrder(action, qty, tif=tif_map[time_in_force])
    elif order_type == "limit":
        order = LimitOrder(action, qty, limit_price, tif=tif_map[time_in_force])
    elif order_type == "stop_limit":
        order = StopLimitOrder(action, qty, limit_price, stop_price, tif=tif_map[time_in_force])

    trade = ib.placeOrder(contract, order)
    return _trade_to_dict(trade)
```

IB order status mapping:
- `Submitted` / `PreSubmitted` → `"pending_new"`
- `Filled` → `"filled"`
- `PartiallyFilled` → `"partially_filled"`
- `Cancelled` → `"canceled"`

### Step 7 — Create `integrations/ibkr/market_data.py`

```python
from ib_async import IB
from datetime import datetime, timedelta
import pandas as pd
from .contracts import to_stock_contract, to_crypto_contract

TIMEFRAME_MAP = {
    "1Min": ("1 min", "1 D"),   "5Min":  ("5 mins", "2 D"),
    "15Min": ("15 mins", "5 D"), "1H":   ("1 hour", "10 D"),
    "4H":   ("4 hours", "20 D"), "1D":   ("1 day",  "1 Y"),
    "1W":   ("1 week",  "5 Y"),
}

async def get_stock_bars(ib: IB, symbol: str, timeframe: str = "1D", bars: int = 60) -> pd.DataFrame:
    contract = to_stock_contract(symbol)
    await ib.qualifyContractsAsync(contract)
    bar_size, duration = TIMEFRAME_MAP.get(timeframe, ("1 day", "1 Y"))
    bars_data = await ib.reqHistoricalDataAsync(
        contract, endDateTime="", durationStr=duration,
        barSizeSetting=bar_size, whatToShow="TRADES", useRTH=True
    )
    df = pd.DataFrame([{
        "timestamp": b.date, "open": b.open, "high": b.high,
        "low": b.low, "close": b.close, "volume": b.volume,
    } for b in bars_data])
    return df.tail(bars)

async def get_stock_quote(ib: IB, symbol: str) -> dict:
    contract = to_stock_contract(symbol)
    await ib.qualifyContractsAsync(contract)
    [ticker] = await ib.reqTickersAsync(contract)
    return {
        "symbol": symbol, "ask_price": ticker.ask, "bid_price": ticker.bid,
        "ask_size": ticker.askSize, "bid_size": ticker.bidSize,
        "timestamp": datetime.now(),
    }
```

### Step 8 — Create `integrations/ibkr/options_data.py` *(highest priority given options focus)*

This is the most complex module. IB options data requires two steps: (1) get the option parameter space, (2) qualify/fetch individual contracts.

```python
from ib_async import IB, Option
from datetime import date, timedelta

async def get_option_contracts(
    ib: IB, underlying_symbol: str, *,
    expiration_date_gte: str | None = None,
    expiration_date_lte: str | None = None,
    strike_price_gte: float | None = None,
    strike_price_lte: float | None = None,
    option_type: str | None = None,  # "call" or "put"
    limit: int = 100,
) -> list[dict]:
    # Step 1: Get available expirations + strikes
    chains = await ib.reqSecDefOptParamsAsync(
        underlyingSymbol=underlying_symbol,
        futFopExchange="",
        underlyingSecType="STK",
        underlyingConId=0,
    )
    chain = next((c for c in chains if c.exchange == "SMART"), chains[0] if chains else None)
    if not chain:
        return []

    # Step 2: Filter expirations + strikes
    today = date.today()
    expirations = [
        exp for exp in chain.expirations
        if (not expiration_date_gte or exp >= expiration_date_gte)
        and (not expiration_date_lte or exp <= expiration_date_lte)
    ]
    strikes = [
        s for s in chain.strikes
        if (not strike_price_gte or s >= strike_price_gte)
        and (not strike_price_lte or s <= strike_price_lte)
    ]

    # Step 3: Build contracts
    rights = []
    if option_type in (None, "call"):
        rights.append("C")
    if option_type in (None, "put"):
        rights.append("P")

    contracts = [
        Option(underlying_symbol, exp, strike, right, "SMART")
        for exp in expirations[:10]   # cap to avoid flooding
        for strike in strikes[:20]
        for right in rights
    ][:limit]

    await ib.qualifyContractsAsync(*contracts)

    # Step 4: Fetch tickers for open interest + bid/ask
    tickers = await ib.reqTickersAsync(*contracts)

    return [
        {
            "symbol":             t.contract.localSymbol,
            "underlying_symbol":  underlying_symbol,
            "expiration_date":    t.contract.lastTradeDateOrContractMonth,
            "strike_price":       t.contract.strike,
            "type":               "call" if t.contract.right == "C" else "put",
            "open_interest":      t.openInterest or 0,
            "bid":                t.bid,
            "ask":                t.ask,
            "tradable":           True,
        }
        for t in tickers
        if t.contract.conId
    ]

async def get_options_chain(
    ib: IB, underlying_symbol: str, *,
    min_dte: int = 0, max_dte: int = 45, limit: int = 100
) -> list[dict]:
    today = date.today()
    gte = (today + timedelta(days=min_dte)).strftime("%Y-%m-%d")
    lte = (today + timedelta(days=max_dte)).strftime("%Y-%m-%d")
    return await get_option_contracts(
        ib, underlying_symbol,
        expiration_date_gte=gte, expiration_date_lte=lte,
        limit=limit,
    )
```

### Step 9 — Update `integrations/data/options_flow.py`

Change `TradingClient` → `IB` in type hints and import:

```python
from ib_async import IB
from integrations.ibkr.options_data import get_options_chain   # was alpaca

async def analyze_options_flow(ib: IB, symbol: str, ...) -> dict:
    contracts = await get_options_chain(ib, symbol, ...)
    ...
```

### Step 10 — Update `integrations/data/news.py`

Remove `search_alpaca_news()`. Update `aggregate_news()` to Tavily-only:

```python
# Remove: search_alpaca_news(), ALPACA_KEY/SECRET references, HTTP call to data.alpaca.markets
# Keep: search_tavily_news(), aggregate_news() simplified to just call Tavily
async def aggregate_news(symbols: list[str], keywords: list[str], ...) -> list[dict]:
    return await search_tavily_news(symbols, keywords, ...)
```

### Step 11 — Update `schemas/deps.py`

```python
from ib_async import IB   # was: from alpaca.trading.client import TradingClient

@dataclass
class Deps:
    ib: IB                           # was: alpaca: TradingClient
    tavily: TavilyClient | None = None
    allow_trading: bool = False
```

### Step 12 — Update `core/agent.py`

- All 8 tool functions: replace `from integrations.alpaca.X import Y` → `from integrations.ibkr.X import Y`
- Replace `ctx.deps.alpaca` → `ctx.deps.ib` everywhere
- Since IBKR functions are `async`, ensure tools are defined as `async def` (PydanticAI supports async tools natively)

### Step 13 — Update `core/runner.py`

- Replace all `deps.alpaca` → `deps.ib`
- Update all imports
- `reconcile_order_and_positions()`: IB order IDs are `int` not UUID strings — adapt parsing
- `_fetch_data_for_strategy()`: `get_stock_bars` / `get_crypto_bars` are now async — `await` them
- `snapshot_positions()`: already returns same dict schema, just `await` the call

### Step 14 — Update `main.py`

```python
import asyncio
from integrations.ibkr.client import create_ib_client  # was: create_trading_client

async def main():
    trading_mode = os.environ.get("TRADING_MODE", "paper")
    ib = await create_ib_client(trading_mode)
    deps = Deps(ib=ib, tavily=..., allow_trading=args.allow_trading)
    try:
        await run_loop(strategy, deps)
    finally:
        ib.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
```

### Step 15 — Update `docker-compose.yml`

Add `ib-gateway` service to the existing `docker-compose.yml`:

```yaml
services:
  ib-gateway:
    image: ghcr.io/gnzsnz/ib-gateway:stable
    restart: unless-stopped
    environment:
      TWS_USERID: ${IB_USERNAME}
      TWS_PASSWORD: ${IB_PASSWORD}
      TRADING_MODE: ${TRADING_MODE:-paper}
      TWS_SETTINGS_PATH: /home/ibgateway/tws-settings
    ports:
      - "4001:4001"   # live TWS API
      - "4002:4002"   # paper TWS API
    volumes:
      - ib-gateway-settings:/home/ibgateway/tws-settings

volumes:
  ib-gateway-settings:
```

### Step 16 — Update `.env.example`

```bash
# Interactive Brokers (replaces ALPACA_KEY / ALPACA_SECRET)
IB_USERNAME=your_ibkr_username
IB_PASSWORD=your_ibkr_password
IB_GATEWAY_HOST=localhost
IB_GATEWAY_PORT=4002        # 4002=paper, 4001=live (set automatically by TRADING_MODE)

# Trading mode
TRADING_MODE=paper           # paper | live

# AI & data
ANTHROPIC_API_KEY=your_anthropic_api_key
TAVILY_API_KEY=your_tavily_api_key
REDDIT_CLIENT_ID=optional
REDDIT_CLIENT_SECRET=optional
```

### Step 17 — Update tests

**`tests/test_agent.py`:**
```python
# Replace: from unittest.mock import patch, MagicMock; patch("integrations.alpaca.account.get_account", ...)
# With:    patch on ib_async.IB methods or inject a mock IB instance into Deps

from unittest.mock import AsyncMock, MagicMock
from ib_async import IB

def make_mock_ib() -> IB:
    ib = MagicMock(spec=IB)
    ib.accountValues.return_value = [
        MagicMock(tag="NetLiquidation", value="100000", currency="USD"),
        MagicMock(tag="BuyingPower", value="50000", currency="USD"),
        MagicMock(tag="CashBalance", value="25000", currency="USD"),
    ]
    ib.positions.return_value = []
    ib.reqTickersAsync = AsyncMock(return_value=[MagicMock(ask=100.0, bid=99.9)])
    ib.placeOrder = MagicMock(return_value=MagicMock(order=MagicMock(orderId=42)))
    return ib
```

### Step 18 — Delete `integrations/alpaca/` after all tests pass

Once `uv run pytest tests/ -v` is green, remove the old directory and confirm no remaining imports:

```bash
rm -rf integrations/alpaca/
grep -r "from integrations.alpaca" . --include="*.py"  # should return nothing
grep -r "alpaca-py" pyproject.toml                      # should return nothing
```

---

## Verification Checklist

1. `uv run pytest tests/ -v` — all tests pass
2. `docker compose up ib-gateway -d` — gateway starts, log shows "IB Gateway started"
3. `python -c "import asyncio; from integrations.ibkr.client import create_ib_client; asyncio.run(create_ib_client('paper'))"` — connects without error
4. Account fetch returns dict with `equity`, `cash`, `buying_power` keys
5. `get_stock_bars("AAPL", "1D", 10)` returns a 10-row DataFrame with OHLCV columns
6. `get_options_chain("SPY", min_dte=0, max_dte=30)` returns list of option contracts
7. Paper order: run `TRADING_MODE=paper uv run python main.py --strategy strategies/examples/sol-momentum.yaml --allow-trading`, verify order appears in IB paper account
8. No Alpaca imports remain: `grep -r "alpaca" . --include="*.py"` returns zero results (outside deleted dir and git history)

---

## Risk & Notes

- **IB Gateway must be running** before the bot starts. Add this to `README.md` as a prerequisite.
- **Canadian accounts:** TSX stocks use `Stock("AC", "SMART", "CAD")`. Strategy YAMLs targeting US stocks work as-is; add CAD currency support to `to_stock_contract()` via optional `currency` param.
- **Options market data subscription:** IB requires a paid market data subscription for live options quotes (Greeks, real-time bid/ask). Paper accounts may have delayed/limited data. Handle `reqTickers()` returning `nan` gracefully.
- **Options chain size:** `reqSecDefOptParams()` returns hundreds of strikes/expiries; always cap queries (e.g., top 10 expirations, ±10% strikes) to avoid overwhelming the TWS API.
- **Notional → Qty conversion:** Requires a live price lookup before placing each order. If price fetch fails, abort the order rather than guessing quantity.
- **Order ID type:** Alpaca uses UUID strings; IB uses `int` order IDs. The SQLite event log stores as text — cast `int` to `str` at write time.
- **Single session limit:** IB only allows one active brokerage session per username. If TWS is also open, the bot's IB Gateway session will conflict. Use a dedicated paper username for the bot.
- **News:** Alpaca News API is removed. Tavily + Reddit/StockTwits remain. This is an acceptable trade-off since Tavily covers the same news sources.
- **Git history:** Keep `integrations/alpaca/` in git history — do not use `git filter-repo` to scrub it. The directory is simply removed in a commit.
- **`ibapi` vs `ib_async`:** Do not use the raw `ibapi` (IB's official Python client). It is callback-based and not asyncio-native. `ib_async` wraps it cleanly and is the de-facto standard for Python algo trading on IBKR.
