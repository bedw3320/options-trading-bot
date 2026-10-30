# Getting Started with Trading API

> **Source:** https://docs.alpaca.markets/docs/getting-started-with-trading-api
> **Last scraped:** 2026-03-06
> **Relevance:** API endpoints, authentication, request IDs for debugging.

---

## API Endpoints

| Environment | Base URL |
| --- | --- |
| Paper Trading | `https://paper-api.alpaca.markets` |
| Live Trading | `https://api.alpaca.markets` |
| Market Data | `https://data.alpaca.markets` |
| Options Data | `https://data.alpaca.markets/v1beta1/options/...` |

---

## Authentication

All requests require API key headers:

```
APCA-API-KEY-ID: {your_key_id}
APCA-API-SECRET-KEY: {your_secret_key}
```

---

## Python SDK (alpaca-py)

```bash
pip install alpaca-py
```

```python
from alpaca.trading.client import TradingClient
from alpaca.data.historical import StockHistoricalDataClient, OptionHistoricalDataClient

# Trading (paper)
trading_client = TradingClient('APCA-API-KEY-ID', 'APCA-API-SECRET-KEY', paper=True)

# Historical market data
stock_client = StockHistoricalDataClient('APCA-API-KEY-ID', 'APCA-API-SECRET-KEY')
options_client = OptionHistoricalDataClient('APCA-API-KEY-ID', 'APCA-API-SECRET-KEY')
```

---

## Request IDs

Every API response includes `X-Request-ID` in the response header. Include this in all support requests. Persist recent request IDs locally for debugging.

```bash
curl -v https://paper-api.alpaca.markets/v2/account \
  -H "APCA-API-KEY-ID: {key}" \
  -H "APCA-API-SECRET-KEY: {secret}"

# Response header:
# X-Request-ID: 649c5a79da1ab9cb20742ffdada0a7bb
```

---

## Environment Variables (this project)

```
ALPACA_KEY=your_api_key
ALPACA_SECRET=your_api_secret
TRADING_MODE=paper  # or live
```

See `.env.example` for all required variables.

---

## Bot Architecture Reference

The bot's Alpaca wrappers live in `integrations/alpaca/`:
- `client.py` — TradingClient factory (paper/live toggle)
- `market_data.py` — Stock/crypto OHLCV bars and quotes
- `options_data.py` — Options chain, contracts, quotes
- `orders.py` — Order placement and management
- `positions.py` — Position listing and closing
- `account.py` — Account info (buying power, equity)
- `assets.py` — Asset listing by class
