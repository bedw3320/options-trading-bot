"""Canonical OCC option symbols (OSI compact, 6-digit yymmdd).

Emit: ``SPY261023C00778000``
Accept: compact, space-padded OSI, or 8-digit YYYYMMDD (normalized).
IB ``lastTradeDateOrContractMonth`` stays YYYYMMDD.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from ib_insync import Option

_OCC_BODY = re.compile(
    r"^([A-Z]{1,6})(\d{6}|\d{8})([CP])(\d{8})$"
)


@dataclass(frozen=True)
class OccParts:
    underlying: str
    expiry_yyyymmdd: str
    right: str
    strike: float

    @property
    def expiry_yymmdd(self) -> str:
        return self.expiry_yyyymmdd[2:]

    @property
    def occ_symbol(self) -> str:
        return format_occ_symbol(
            self.underlying,
            self.expiry_yyyymmdd,
            self.right,
            self.strike,
        )


def _as_yyyymmdd(value: str | date | datetime) -> str:
    if isinstance(value, datetime):
        return value.date().strftime("%Y%m%d")
    if isinstance(value, date):
        return value.strftime("%Y%m%d")
    raw = str(value).strip().replace("-", "")
    if len(raw) == 6 and raw.isdigit():
        return "20" + raw
    if len(raw) == 8 and raw.isdigit():
        return raw
    raise ValueError(f"unrecognized expiry: {value!r}")


def format_occ_symbol(
    underlying: str,
    expiry: str | date | datetime,
    right: str,
    strike: float,
) -> str:
    """Compact OSI: underlying + yymmdd + C/P + 8-digit strike*1000."""
    und = underlying.strip().upper()
    expiry8 = _as_yyyymmdd(expiry)
    cp = right.strip().upper()
    if cp in ("CALL",):
        cp = "C"
    elif cp in ("PUT",):
        cp = "P"
    if cp not in ("C", "P"):
        raise ValueError(f"right must be C/P, got {right!r}")
    strike_int = int(round(float(strike) * 1000))
    if strike_int < 0 or strike_int > 99_999_999:
        raise ValueError(f"strike out of OCC range: {strike}")
    return f"{und}{expiry8[2:]}{cp}{strike_int:08d}"


def parse_occ_symbol(symbol: str) -> OccParts:
    """Parse compact or padded OCC. 8-digit YYYYMMDD is accepted and normalized."""
    compact = symbol.strip().upper().replace(" ", "")
    match = _OCC_BODY.fullmatch(compact)
    if not match:
        raise ValueError(f"not an OCC option symbol: {symbol!r}")
    und, date_part, right, strike_s = match.groups()
    expiry = _as_yyyymmdd(date_part)
    return OccParts(
        underlying=und,
        expiry_yyyymmdd=expiry,
        right=right,
        strike=int(strike_s) / 1000.0,
    )


def make_option(
    underlying: str,
    expiry: str | date | datetime,
    strike: float,
    right: str,
    *,
    exchange: str = "SMART",
    currency: str = "USD",
    multiplier: str = "100",
    trading_class: str | None = None,
    local_symbol: str | None = None,
) -> Option:
    """Qualified-shape Option: SMART / USD / 100 / tradingClass."""
    cp = right.strip().upper()
    if cp in ("CALL",):
        cp = "C"
    elif cp in ("PUT",):
        cp = "P"
    kwargs: dict[str, Any] = {
        "tradingClass": (trading_class or underlying).strip().upper(),
    }
    if local_symbol:
        kwargs["localSymbol"] = local_symbol
    return Option(
        underlying.strip().upper(),
        _as_yyyymmdd(expiry),
        float(strike),
        cp,
        exchange,
        multiplier,
        currency,
        **kwargs,
    )


def option_from_occ(symbol: str, *, trading_class: str | None = None) -> Option:
    parts = parse_occ_symbol(symbol)
    return make_option(
        parts.underlying,
        parts.expiry_yyyymmdd,
        parts.strike,
        parts.right,
        trading_class=trading_class or parts.underlying,
    )
