"""Deterministic cycle CLI.

    uv run python -m core.cli run --dry-run                 # full cycle on fixtures, SimBroker
    uv run python -m core.cli run                           # paper, journal only (no send)
    uv run python -m core.cli run --allow-trading           # paper, sends via GuardedBroker
    uv run python -m core.cli run --data-source alpaca      # quotes/Greeks from Alpaca, orders/identity on IB paper
    uv run python -m core.cli explain last                  # why it traded / abstained
    uv run python -m core.cli list --limit 1 --json         # last cycle summary (heartbeat)
    uv run python -m core.cli list
    uv run python -m core.cli reconcile                     # paper: IB vs SQLite, no orders
    uv run python -m core.cli kill --reason "manual"        # latch (blocks entries); `rearm` to clear
    uv run python -m core.cli flatten --allow-trading       # paper: close the open strategy position now
    uv run python -m core.cli flatten --dry-run             # same against fixtures + SimBroker
"""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

DEFAULT_STRATEGY = "strategies/active/spy-defined-risk-rr.yaml"
DEFAULT_FIXTURE = "tests/fixtures/spy_snapshot_entry.json"
DEFAULT_DB = "state/state.db"


@contextmanager
def cycle_lock(db_path: str) -> Iterator[bool]:
    lock_path = Path(db_path).parent / "cycle.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with open(lock_path, "w") as fh:
        try:
            fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            yield False
            return
        try:
            yield True
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)


def _strategy_name(path: str) -> str:
    from core.strategy_loader import load

    return load(path).name


def _connect_paper(rules, *, allow_trading: bool):
    from integrations.ibkr.client import create_ib_client

    if os.environ.get("TRADING_MODE", "paper").strip().lower() != "paper":
        raise SystemExit("REFUSED: TRADING_MODE is not paper; this strategy is paper-only")
    return create_ib_client("paper", client_id=int(os.environ.get("IB_CYCLE_CLIENT_ID", rules.execution.client_id)),
                            readonly=not allow_trading)


def cmd_flatten(args) -> int:
    args.flatten = True
    return cmd_run(args)


def cmd_run(args) -> int:
    from core.brokers import IBExecution, SimBroker
    from core.cycle import run_cycle
    from core.market_state import FixtureMarketState, make_provider
    from core.reconcile import expected_option_positions
    from core.strategy_loader import load
    from utils.lineage import Lineage

    lineage = Lineage(args.db)
    strategy = load(args.strategy)
    if strategy.rules is None:
        print(f"{args.strategy} has no deterministic rules block", file=sys.stderr)
        return 2
    with cycle_lock(args.db) as got:
        if not got:
            print("SKIP another cycle is running (state/cycle.lock)")
            return 3
        if args.dry_run:
            seeded = expected_option_positions(lineage.open_positions(strategy.name, "dry_run"))
            result = run_cycle(args.strategy, mode="dry_run", provider=FixtureMarketState(args.fixture),
                               broker=SimBroker(seeded), lineage=lineage, allow_trading=True,
                               flatten=getattr(args, "flatten", False))
        else:
            from core.identity import assert_paper_identity

            allow = args.allow_trading or os.environ.get("ALLOW_TRADING", "false").lower() == "true"
            ib = _connect_paper(strategy.rules, allow_trading=allow)
            try:
                result = run_cycle(
                    args.strategy, mode="paper", provider=make_provider(args.data_source, ib=ib),
                    broker=IBExecution(ib, allow_trading=allow), lineage=lineage, allow_trading=allow,
                    identity_check=lambda: assert_paper_identity(ib, trading_mode="paper").account_id,
                    flatten=getattr(args, "flatten", False),
                )
            finally:
                ib.disconnect()
    print(f"{result.cycle_id} {result.outcome}")
    for r in result.reasons:
        print(f"  - {r}")
    return 1 if result.outcome == "error" else 0


def _fmt_signals(payload: dict) -> list[str]:
    lines = []
    for s in payload.get("signals", []):
        mark = {True: "PASS", False: "FAIL", None: "n/a "}[s.get("passed")]
        req = "" if s.get("required", True) else " (info)"
        lines.append(f"    {mark} {s['name']} = {s.get('value')} (threshold {s.get('threshold')}){req}"
                     + (f"  [{s['note']}]" if s.get("note") else ""))
    if "exit_evaluation" in payload:
        e = payload["exit_evaluation"]
        lines.append(f"    exit trigger={e.get('trigger')} mark={e.get('mark')}: {'; '.join(e.get('reasons', []))}")
    return lines


def explain(cycle: dict) -> str:
    from utils.lineage import to_et

    out = [
        f"cycle {cycle['cycle_id']}  strategy={cycle['strategy']} v{cycle['strategy_version']}  mode={cycle['mode']}",
        f"  started {to_et(cycle['started_at'])}  ended {to_et(cycle['ended_at'])}  git={cycle.get('git_sha')}",
        f"  OUTCOME: {cycle['outcome']}",
    ]
    out += [f"    - {r}" for r in cycle["reasons"]]
    for a in cycle["artifacts"]:
        k, p = a["kind"], a["payload"]
        if k == "market_snapshot":
            out.append(f"  snapshot: source={p.get('source')} as_of={to_et(p.get('as_of'))} status={p.get('status')}"
                       f" reason={p.get('reason')} {p.get('underlying')}={p.get('underlying_price')}"
                       f" expiry={p.get('expiry')} options={len(p.get('options', []))}")
        elif k == "signals":
            out.append("  signals:")
            out += _fmt_signals(p)
        elif k == "decision":
            out.append(f"  decision: {p['action']}" + (f" ({p['exit_trigger']})" if p.get("exit_trigger") else ""))
        elif k == "intent":
            out.append(f"  intent: {p['action']} {p['quantity']}x combo @ {p['limit_price']:+.2f}/sh"
                       f" max_loss={p.get('max_loss_usd')} key={p['idempotency_key']}")
            out += [f"    {l['action']} {l['occ']} delta={l.get('delta')} bid={l.get('bid')} ask={l.get('ask')}"
                    for l in p["legs"]]
        elif k == "order":
            out.append(f"  order: sent={p.get('sent')} id={p.get('broker_order_id')} status={p.get('status')}"
                       + (f" reason={p['reason']}" if p.get("reason") else ""))
        elif k == "fill":
            out.append(f"  fill: status={p.get('status')} avg={p.get('avg_fill_price')} n_fills={len(p.get('fills', []))}")
        elif k == "reconcile":
            out.append(f"  reconcile[{p.get('phase')}]: ok={p.get('ok')} broker={p.get('broker')} drift={p.get('drift')}")
        elif k in ("error", "kill_switch"):
            out.append(f"  {k}: {p}")
    return "\n".join(out)


def cmd_explain(args) -> int:
    from utils.lineage import Lineage

    cycle = Lineage(args.db).get_cycle(args.cycle_id)
    if cycle is None:
        print(f"no cycle {args.cycle_id}", file=sys.stderr)
        return 2
    print(json.dumps(cycle, indent=2, default=str) if args.json else explain(cycle))
    return 0


def cmd_list(args) -> int:
    from utils.lineage import Lineage, to_et

    cycles = Lineage(args.db).list_cycles(args.limit)
    if args.json:
        print(json.dumps([{k: c.get(k) for k in ("cycle_id", "strategy", "mode", "started_at", "outcome", "reasons")}
                          for c in cycles], default=str))
        return 0
    for c in cycles:
        first = c["reasons"][0] if c["reasons"] else ""
        print(f"{c['cycle_id']}  {to_et(c['started_at'])}  {c['mode']:<7} {c['outcome'] or 'running':<17} {first}")
    return 0


def cmd_kill(args) -> int:
    from utils.lineage import Lineage

    Lineage(args.db).latch_kill(_strategy_name(args.strategy), args.mode, f"manual: {args.reason}")
    print(f"kill switch latched for {args.mode}")
    return 0


def cmd_rearm(args) -> int:
    from utils.lineage import Lineage

    ok = Lineage(args.db).rearm(_strategy_name(args.strategy), args.mode)
    print("rearmed" if ok else "kill switch was not latched")
    return 0


def cmd_reconcile(args) -> int:
    from core.brokers import IBExecution
    from core.reconcile import reconcile
    from core.strategy_loader import load
    from utils.lineage import Lineage

    strategy = load(args.strategy)
    ib = _connect_paper(strategy.rules, allow_trading=False)
    try:
        rec = reconcile(IBExecution(ib, allow_trading=False), Lineage(args.db), strategy=strategy.name,
                        mode="paper", underlying=strategy.rules.underlying)
    finally:
        ib.disconnect()
    print(json.dumps(rec, indent=2, default=str))
    return 0 if rec["ok"] else 1


def main(argv: list[str] | None = None) -> int:
    from dotenv import load_dotenv

    load_dotenv()
    p = argparse.ArgumentParser(prog="core.cli", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--db", default=os.environ.get("STATE_DB", DEFAULT_DB))
    sub = p.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run")
    r.add_argument("--strategy", default=DEFAULT_STRATEGY)
    r.add_argument("--dry-run", action="store_true", help="fixtures + SimBroker, no IB connection")
    r.add_argument("--fixture", default=DEFAULT_FIXTURE)
    r.add_argument("--allow-trading", action="store_true", help="paper only: send via GuardedBroker")
    r.add_argument("--data-source", default=os.environ.get("MARKET_DATA_SOURCE", "ib"),
                   help="quotes/Greeks provider: ib | alpaca (env MARKET_DATA_SOURCE)")
    r.set_defaults(fn=cmd_run)

    f = sub.add_parser("flatten", help="close the open strategy position now (allowed while kill switch is latched)")
    f.add_argument("--strategy", default=DEFAULT_STRATEGY)
    f.add_argument("--dry-run", action="store_true")
    f.add_argument("--fixture", default=DEFAULT_FIXTURE)
    f.add_argument("--allow-trading", action="store_true", help="paper only: send via GuardedBroker")
    f.add_argument("--data-source", default=os.environ.get("MARKET_DATA_SOURCE", "ib"))
    f.set_defaults(fn=cmd_flatten)

    e = sub.add_parser("explain")
    e.add_argument("cycle_id", nargs="?", default="last")
    e.add_argument("--json", action="store_true")
    e.set_defaults(fn=cmd_explain)

    l = sub.add_parser("list")
    l.add_argument("--limit", type=int, default=20)
    l.add_argument("--json", action="store_true")
    l.set_defaults(fn=cmd_list)

    for nm, fn in (("kill", cmd_kill), ("rearm", cmd_rearm)):
        k = sub.add_parser(nm)
        k.add_argument("--strategy", default=DEFAULT_STRATEGY)
        k.add_argument("--mode", choices=("paper", "dry_run"), default="paper")
        if nm == "kill":
            k.add_argument("--reason", default="manual")
        k.set_defaults(fn=fn)

    rc = sub.add_parser("reconcile")
    rc.add_argument("--strategy", default=DEFAULT_STRATEGY)
    rc.set_defaults(fn=cmd_reconcile)

    args = p.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
