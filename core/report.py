"""Summarize recorded cycles: decision, reason, strikes / credit / Greeks.

    uv run python -m core.report --db state/state.db --limit 20
    uv run python -m core.cli report --limit 20
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from utils.lineage import Lineage, to_et


def _art(cycle: dict, kind: str) -> dict[str, Any] | None:
    for a in cycle.get("artifacts") or []:
        if a.get("kind") == kind:
            return a.get("payload") or {}
    return None


def _data_source(cycle: dict) -> str:
    for kind in ("decision", "inputs", "market_snapshot", "order"):
        p = _art(cycle, kind)
        if p and p.get("data_source"):
            return str(p["data_source"])
    snap = _art(cycle, "market_snapshot")
    if snap and snap.get("source"):
        return str(snap["source"])
    return cycle.get("mode") or "?"


def _greeks(row: dict[str, Any]) -> str:
    parts = []
    if row.get("delta") is not None:
        parts.append(f"d={row['delta']:+.3f}")
    if row.get("iv") is not None:
        parts.append(f"iv={row['iv']:.4f}")
    if row.get("gamma") is not None:
        parts.append(f"γ={row['gamma']}")
    if row.get("vega") is not None:
        parts.append(f"v={row['vega']}")
    if row.get("theta") is not None:
        parts.append(f"θ={row['theta']}")
    return " ".join(parts)


def summarize(cycle: dict[str, Any]) -> str:
    src = _data_source(cycle)
    reasons = cycle.get("reasons") or []
    first = reasons[0] if reasons else ""
    lines = [
        f"{cycle['cycle_id']}  {to_et(cycle.get('started_at'))}  {cycle.get('mode')}  "
        f"{cycle.get('outcome') or 'running'}  data_source={src}",
    ]
    dec = _art(cycle, "decision")
    if dec:
        extra = f" ({dec['exit_trigger']})" if dec.get("exit_trigger") else ""
        lines.append(f"  decision: {dec.get('action')}{extra}")
    for r in reasons[:6]:
        lines.append(f"  reason: {r}")
    snap = _art(cycle, "market_snapshot")
    if snap:
        lines.append(
            f"  snapshot: source={snap.get('source')} status={snap.get('status')} "
            f"{snap.get('underlying')}={snap.get('underlying_price')} expiry={snap.get('expiry')} "
            f"options={len(snap.get('options') or [])}"
        )
    by_occ = {o.get("occ"): o for o in (snap or {}).get("options") or [] if o.get("occ")}
    intent = _art(cycle, "intent")
    if intent:
        credit = intent.get("limit_price")
        lines.append(
            f"  combo: {intent.get('action')} {intent.get('quantity')}x @ {credit:+.2f}/sh "
            f"max_loss={intent.get('max_loss_usd')}" if isinstance(credit, (int, float))
            else f"  combo: {intent.get('action')} {intent.get('quantity')}x"
        )
        for leg in intent.get("legs") or []:
            row = {**by_occ.get(leg.get("occ"), {}), **leg}
            g = _greeks(row)
            lines.append(
                f"    {leg.get('action')} {leg.get('occ')} {g} bid={leg.get('bid')} ask={leg.get('ask')}"
            )
    return "\n".join(lines)


def render(cycles: list[dict[str, Any]], *, as_json: bool = False) -> str:
    if as_json:
        out = []
        for c in cycles:
            dec = _art(c, "decision") or {}
            intent = _art(c, "intent")
            snap = _art(c, "market_snapshot") or {}
            out.append({
                "cycle_id": c.get("cycle_id"),
                "started_at": c.get("started_at"),
                "mode": c.get("mode"),
                "outcome": c.get("outcome"),
                "data_source": _data_source(c),
                "decision": dec.get("action"),
                "reasons": c.get("reasons") or [],
                "underlying_price": snap.get("underlying_price"),
                "expiry": snap.get("expiry"),
                "limit_price": None if not intent else intent.get("limit_price"),
                "legs": None if not intent else [
                    {"action": l.get("action"), "occ": l.get("occ"), "delta": l.get("delta"),
                     "bid": l.get("bid"), "ask": l.get("ask")}
                    for l in intent.get("legs") or []
                ],
            })
        return json.dumps(out, indent=2, default=str)
    if not cycles:
        return "no cycles"
    return "\n\n".join(summarize(c) for c in cycles)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--db", default="state/state.db")
    p.add_argument("--limit", type=int, default=20)
    p.add_argument("--json", action="store_true")
    p.add_argument("--cycle", default=None, help="one cycle_id (default: last N)")
    args = p.parse_args(argv)
    lin = Lineage(args.db)
    if args.cycle:
        c = lin.get_cycle(args.cycle)
        cycles = [] if c is None else [c]
        if c is None:
            print(f"no cycle {args.cycle}", file=sys.stderr)
            return 2
    else:
        cycles = [lin.get_cycle(c["cycle_id"]) for c in lin.list_cycles(args.limit)]
        cycles = [c for c in cycles if c is not None]
    print(render(cycles, as_json=args.json))
    return 0


if __name__ == "__main__":
    sys.exit(main())
