"""When a cycle may send a broker order.

Delayed / unofficial quotes never send. Paper auto-send additionally needs
live IBKR data on the paper account and one paper fill already reconciled
into SQLite. Dry-run SimBroker is not a broker send.
"""

from __future__ import annotations

from core.gates import source_class
from core.shadow import shadow_refusal, shadow_tag
from schemas.cycle import MarketSnapshot
from utils.lineage import Lineage

LIVE_IB_SOURCES = frozenset({"ib", "ib_live"})


def snapshot_source(snapshot: MarketSnapshot | None) -> str:
    if snapshot is None:
        return ""
    return (snapshot.source or "").strip()


def delayed_send_reason(data_source: str, snapshot: MarketSnapshot | None) -> str | None:
    tag = shadow_tag(data_source)
    if tag:
        return shadow_refusal(tag)
    src = snapshot_source(snapshot)
    if source_class(src) == "delayed" or source_class(data_source) == "delayed":
        label = tag or src or data_source or "delayed"
        return shadow_refusal(label)
    return None


def paper_send_reason(
    *,
    mode: str,
    data_source: str,
    snapshot: MarketSnapshot | None,
    lineage: Lineage,
) -> str | None:
    """None => may send (still subject to --allow-trading / GuardedBroker)."""
    delayed = delayed_send_reason(data_source, snapshot)
    if delayed:
        return delayed
    if mode != "paper":
        return None
    src = snapshot_source(snapshot)
    cls = source_class(src)
    if cls != "live" or src.split(":", 1)[0].lower() not in LIVE_IB_SOURCES:
        return "paper_send_blocked: market data is not live IBKR"
    if not lineage.has_reconciled_paper_fill():
        return "paper_send_blocked: no reconciled paper fill in SQLite yet"
    return None
