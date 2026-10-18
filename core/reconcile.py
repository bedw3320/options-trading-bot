"""Reconcile broker state (authoritative, LOOP principle 3) with the lineage store.

Scope: option positions and orders on the strategy's underlying. Anything else in
the account (e.g. the pre-existing 1 SPY share) is reported as out of scope.
"""

from __future__ import annotations

from typing import Any

from core.brokers import ExecutionBroker
from utils.lineage import Lineage


def expected_option_positions(open_positions: list[dict[str, Any]]) -> dict[str, float]:
    exp: dict[str, float] = {}
    for pos in open_positions:
        for leg in pos["legs"]:
            sign = 1.0 if leg["action"] == "BUY" else -1.0
            exp[leg["occ"]] = exp.get(leg["occ"], 0.0) + sign * pos["quantity"] * leg.get("ratio", 1)
    return {k: v for k, v in exp.items() if v != 0}


def reconcile(
    broker: ExecutionBroker, lineage: Lineage, *, strategy: str, mode: str, underlying: str,
    cycle_id: str | None = None,
) -> dict[str, Any]:
    drift: list[str] = []
    expected = expected_option_positions(lineage.open_positions(strategy, mode))
    actual = broker.option_positions(underlying)
    for occ in sorted(set(expected) | set(actual)):
        e, a = expected.get(occ, 0.0), actual.get(occ, 0.0)
        if e != a:
            drift.append(f"position {occ}: expected {e:+g}, broker {a:+g}")

    known = lineage.known_broker_order_ids(strategy, mode)
    for oid in sorted(broker.open_order_ids(underlying)):
        if oid not in known:
            drift.append(f"unknown open order {oid} on {underlying}")
        else:
            drift.append(f"own order {oid} still working (cycle should have cancelled it)")

    for order in lineage.orders_by_status(strategy, mode, ("proposed", "submitted")):
        drift.append(f"order {order['idempotency_key']} left in state {order['status']}")

    # Catch up executions for our own orders that were not recorded yet.
    seen = lineage.fill_exec_ids(mode)
    caught_up = 0
    for ex in broker.executions():
        exec_id, oid = ex.get("exec_id"), str(ex.get("order_id") or "")
        if ex.get("symbol") not in (None, underlying):
            continue
        if exec_id and oid in known and exec_id not in seen:
            if lineage.record_fill(exec_id=exec_id, idempotency_key=None, broker_order_id=oid,
                                   cycle_id=cycle_id, mode=mode, payload=ex):
                caught_up += 1
    return {"ok": not drift, "drift": drift, "expected": expected, "broker": actual,
            "caught_up_fills": caught_up}
