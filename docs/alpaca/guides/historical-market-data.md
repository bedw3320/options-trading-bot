# Historical Market Data

> **Source:** https://docs.alpaca.markets/docs/historical-option-data
> **Last scraped:** 2026-03-06
> **Relevance:** Data availability, feed types (OPRA vs. indicative), and which endpoints to use for backtesting and strategy signal generation.

---

## Historical Options Data

> **⚠️ Data availability:** Historical option data is only available **since February 2024**.

### Data Feed Sources

| Source | Description | Cost |
| --- | --- | --- |
| **Indicative** | Free derivative of OPRA — quotes are indicative (not official OPRA), trades are **delayed 15 minutes** | Free |
| **OPRA** | Official consolidated BBO (best bid/offer) from Options Price Reporting Authority | Subscription required |

**Default behavior:** If subscribed to OPRA, you get OPRA. Otherwise, you get indicative.

**For strategy development / paper trading:** Indicative feed is sufficient. For production execution, OPRA subscription is recommended for accurate fills.

---

## Available Endpoints

| Endpoint | Use Case |
| --- | --- |
| `GET /v1beta1/options/bars` | Historical OHLCV bars for specific contracts |
| `GET /v1beta1/options/trades/latest` | Latest trade for one or more contracts |
| `GET /v1beta1/options/snapshots/{underlying}` | Option chain — latest trade + quote + Greeks for all contracts of an underlying |
| `GET /v2/options/contracts` | Contract master list with metadata (strike, expiry, OI) |

See `reference/option-historical-bars.md`, `reference/option-chain.md`, and `reference/get-option-contracts.md` for full parameter details.

---

## Historical Stock Data

Available via `GET /v2/stocks/{symbol}/bars` (alpaca-py: `StockHistoricalDataClient`).

Timeframes supported:
- `1Min`, `5Min`, `15Min`, `1Hour`, `4Hour`, `1Day`, `1Week`, `1Month`

Data available: 6+ years of historical data.

---

## Historical Crypto Data

Available via `GET /v1beta3/crypto/{loc}/bars`.

Same timeframe options as stocks.

---

## Existing Bot Integration

The bot already wraps these in `integrations/alpaca/market_data.py`:
- `get_stock_bars(symbol, timeframe, bars)` — OHLCV with configurable timeframe
- `get_crypto_bars(symbol, timeframe, bars)` — same for crypto

Options bar data is in `integrations/alpaca/options_data.py` via `get_options_chain()`.
