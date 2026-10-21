"""Shadow / delayed-data rules.

CBOE delayed quotes are unofficial and ~15 minutes old. They may be used to
record what the strategy *would* do. They must never be used to place orders.
"""

from __future__ import annotations

from typing import Any

from utils.lineage import Lineage

# MARKET_DATA_SOURCE value -> lineage tag. Default source stays `ib` (untagged).
SHADOW_TAGS = {"cboe": "cboe_delayed"}


def normalize_source(source: str | None) -> str:
    return (source or "ib").strip().lower() or "ib"


def shadow_tag(source: str | None) -> str | None:
    return SHADOW_TAGS.get(normalize_source(source))


def shadow_refusal(tag: str) -> str:
    return f"shadow_record_only: data_source={tag} cannot place orders"


def stamp(payload: Any, tag: str | None) -> Any:
    if tag and isinstance(payload, dict):
        return {**payload, "data_source": tag}
    return payload


class TaggedLineage:
    """Proxy that stamps data_source onto every artifact payload."""

    def __init__(self, inner: Lineage, tag: str) -> None:
        self._inner = inner
        self.tag = tag

    def record(self, cycle_id: str, kind: str, payload: Any) -> None:
        self._inner.record(cycle_id, kind, stamp(payload, self.tag))

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)
