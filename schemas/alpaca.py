from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class AlpacaOrderResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str | None = None
    client_order_id: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    submitted_at: str | None = None
    filled_at: str | None = None

    symbol: str | None = None
    side: Literal["buy", "sell"] | None = None
    type: str | None = None
    time_in_force: str | None = None

    qty: str | None = None
    notional: str | None = None
    filled_qty: str | None = None
    filled_avg_price: str | None = None

    status: str | None = None


class AlpacaAsset(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str
    class_: str = Field(alias="class")
    exchange: str | None = None
    symbol: str
    name: str | None = None
    status: str | None = None
    tradable: bool | None = None
    fractionable: bool | None = None


class AlpacaAccount(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str
    account_number: str | None = None
    status: str | None = None
    crypto_status: str | None = None
    currency: str | None = None

    buying_power: str | None = None
    cash: str | None = None
    portfolio_value: str | None = None
    non_marginable_buying_power: str | None = None

    equity: str | None = None
    last_equity: str | None = None

    trading_blocked: bool | None = None
    account_blocked: bool | None = None
    created_at: str | None = None


class AlpacaPosition(BaseModel):
    model_config = ConfigDict(extra="allow")

    asset_id: str | None = None
    symbol: str
    asset_class: str | None = None
    exchange: str | None = None

    qty: str | None = None
    avg_entry_price: str | None = None
    current_price: str | None = None
    market_value: str | None = None

    unrealized_pl: str | None = None
    unrealized_plpc: str | None = None

    side: Literal["long", "short"] | None = None
