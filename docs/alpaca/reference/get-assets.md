# Get Assets

> **Source:** https://docs.alpaca.markets/reference/get-v2-assets-1
> **Last scraped:** 2026-03-06
> **Relevance:** Asset master list with tradability flags. Use to check if a ticker is options-eligible (`has_options`), fractional-eligible, or overnight-tradable. Useful before strategy initialization.

---

## Endpoints

```
GET /v2/assets              — list assets with filters
GET /v2/assets/{symbol_or_id}  — single asset by symbol or UUID
```

Base URL: `https://api.alpaca.markets` (or `https://paper-api.alpaca.markets`)

---

## Query Parameters (List)

| Parameter | Type | Default | Description |
| --- | --- | --- | --- |
| `status` | string | `active` | Asset status: `active` or `inactive` |
| `asset_class` | string | `us_equity` | Asset class: `us_equity`, `crypto`, `us_option` |
| `exchange` | string | — | Filter by exchange: `AMEX`, `ARCA`, `BATS`, `NYSE`, `NASDAQ`, `NYSEARCA`, `OTC` |
| `attributes` | string | — | Comma-separated attribute filters (see below) |

### Attribute Filters

| Attribute | Description |
| --- | --- |
| `has_options` | Asset has listed options contracts |
| `options_late_close` | Options close late (some index products) |
| `fractional_eh_enabled` | Fractional shares available in extended hours |
| `overnight_tradable` | Can be traded overnight |
| `overnight_halted` | Currently halted overnight |
| `ipo` | Upcoming IPO |
| `ptp_no_exception` | Passive foreign investment company (tax flag) |
| `ptp_with_exception` | PTP with K-1 reporting exception |

---

## Response (Asset Object)

```json
{
  "id": "b0b6dd9d-8b9b-48a9-ba46-b9d54906e415",
  "class": "us_equity",
  "exchange": "NASDAQ",
  "symbol": "AAPL",
  "name": "Apple Inc. Common Stock",
  "status": "active",
  "tradable": true,
  "marginable": true,
  "shortable": true,
  "easy_to_borrow": true,
  "fractionable": true,
  "attributes": ["has_options", "fractional_eh_enabled", "overnight_tradable"]
}
```

### Key Response Fields

| Field | Description |
| --- | --- |
| `tradable` | Whether the asset can be traded right now |
| `marginable` | Whether the asset can be bought on margin |
| `shortable` | Whether short selling is allowed |
| `easy_to_borrow` | Whether shares are easy to borrow for short selling |
| `fractionable` | Whether fractional shares are supported |
| `attributes` | List of special attributes |

---

## Python SDK

```python
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import GetAssetsRequest
from alpaca.trading.enums import AssetClass, AssetStatus

trading_client = TradingClient('api-key', 'secret-key', paper=True)

# Get all active equity assets with options
request = GetAssetsRequest(
    asset_class=AssetClass.US_EQUITY,
    status=AssetStatus.ACTIVE,
    attributes='has_options'
)
assets = trading_client.get_all_assets(request)

# Check single asset
aapl = trading_client.get_asset('AAPL')
has_options = 'has_options' in aapl.attributes
```

---

## Bot Usage Notes

- Use `attributes=has_options` to filter to options-eligible tickers
- `tradable: false` means the asset is currently halted or delisted — skip it
- `shortable: false` means you cannot take a short position (but you can still buy puts)
- `marginable: false` affects buying power calculation for spreads
- Wrapped in `integrations/alpaca/assets.py`
- Check asset eligibility once at strategy initialization, not on every loop iteration
