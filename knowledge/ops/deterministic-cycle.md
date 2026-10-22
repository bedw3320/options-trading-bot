# Deterministic cycle v0 — SPY defined-risk risk reversal

Strategy: `strategies/active/spy-defined-risk-rr.yaml` (the `rules:` block executes; no LLM in the decision path).
Code: `core/cycle.py` (orchestration), `core/signals.py`, `core/rr_rules.py`, `core/market_state.py`,
`core/brokers.py`, `core/reconcile.py`, `utils/lineage.py`, `integrations/ibkr/combo.py`, CLI `core/cli.py`.

## One cycle (run once, then stop)

1. Start `cycle_id`, record inputs (strategy path + sha256, version, git sha, mode, rules).
2. Kill switch state is read (it blocks new entries only; see below).
3. Paper mode: identity gate (`assert_paper_identity`, account must be `DU*`, `TRADING_MODE=paper`); failure latches the kill switch. RTH only.
4. Reconcile IB option positions / working orders on SPY vs SQLite. Drift → latch + abstain.
5. Daily realized loss ≥ $1,500 → latch (no new entries; exits still run).
6. Market snapshot (IB or fixture). Any data failure (10197, 162, not subscribed, timeout, exception) → `status=unavailable` → abstain with the reason. Never guesses.
7. Open position → exit rules (time stop 21 DTE, SPY ≤ max(short put −3%, long put + 25% of wing), −$1,250, +$1,000), or `flatten` forces trigger `manual_flatten`.
   No position: kill latched → abstain `new entries blocked`; else entry: signals → construction → caps.
8. Intent → `GuardedBroker.preview_combo` → token → revalidate → BAG limit at mid, DAY. Revalidate: opens need kill not latched, no open
   position, max loss ≤ cap; closes must exactly offset an open strategy position (same legs, SELL, same quantity), else rejected.
   Without `--allow-trading` the preview refuses and the cycle ends `proposed_not_sent` (journal only).
9. Wait `fill_wait_seconds` (30); unfilled → cancel. Record fills, open/close the position row, reconcile again.

Outcomes: `entered`, `exited`, `held`, `abstained`, `proposed_not_sent`, `error`. 3 consecutive `error`s latch the kill switch.

## Kill switch

Latched by: identity failure, reconcile drift (pre or post trade), daily realized loss ≥ $1,500, 3 consecutive error cycles, or `kill`.
Stays latched until `rearm`. While latched:

- **New entries are blocked** (cycle check + GuardedBroker revalidate).
- **Risk-reducing exits still run**: rule exits on the open strategy position, and `flatten`. They use the same path as any order:
  paper identity gate (`DU*`, `TRADING_MODE=paper`, RTH), pre-trade reconcile, preview → token → revalidate, `--allow-trading` to send.
- The cycle record shows it: a `kill_switch` artifact `{"action": "exit_allowed_while_latched", "trigger": ..., "reason": ...}`,
  the decision reasons include the latch, and the cycle's terminal reasons end with `exit ran while kill switch latched`.
- Not allowed even for exits: a live/non-`DU` account (identity error, nothing sent) and reconcile drift (the position can't be verified, so nothing is closed; manual review).

## SQLite (state/state.db, gitignored)

`cycles`, `cycle_artifacts` (kind = inputs | reconcile | market_snapshot | signals | decision | intent | order | fill | error | kill_switch),
`strategy_positions`, `orders` (idempotency_key = `<cycle_id>:open|close`), `fills` (unique exec_id), `kill_switch`.
Dry-run and paper rows are separated by `mode`.

## Commands (Mini, repo root)

    uv run python -m core.cli run --dry-run                    # fixtures + SimBroker; no IB connection
    uv run python -m core.cli run --dry-run --fixture tests/fixtures/spy_snapshot_unavailable.json
    uv run python -m core.cli explain last                     # why it traded / abstained
    uv run python -m core.cli list
    TRADING_MODE=paper IB_GATEWAY_HOST=127.0.0.1 IB_GATEWAY_PORT=4002 uv run python -m core.cli run                  # paper, journal only
    TRADING_MODE=paper IB_GATEWAY_HOST=127.0.0.1 IB_GATEWAY_PORT=4002 uv run python -m core.cli run --allow-trading  # paper, sends
    uv run python -m core.cli reconcile                        # paper IB vs SQLite, no orders
    uv run python -m core.cli kill --reason "..."  /  rearm    # add --mode dry_run for dry-run rows
    TRADING_MODE=paper IB_GATEWAY_HOST=127.0.0.1 IB_GATEWAY_PORT=4002 uv run python -m core.cli flatten --allow-trading  # close now
    uv run python -m core.cli flatten --dry-run                # same on fixtures + SimBroker

Paper cycles use clientId 11 (`IB_CYCLE_CLIENT_ID` overrides), readonly unless `--allow-trading`.
A file lock (`state/cycle.lock`) prevents overlapping cycles.

## Known limits (v0)

- Needs IB option quotes + model Greeks + open interest. Until the 10197 competing-session issue is fixed, every paper cycle abstains with `market_data_unavailable: ib_10197_competing_live_session`.
- Open interest arrives on generic tick 101 and may lag; a missing OI fails the liquidity check (abstain, by design).
- Fixtures are SYNTHETIC (Black-Scholes + skew curve, `tests/fixtures/make_spy_fixtures.py`), not market data.
- rr25 percentile is informational until 60 stored trading days (latest rr25 per ET day); then set `skew_percentile_required: true`.
- 25-delta IVs for rr25 / put-call IV ratio are interpolated in |delta| between the bracketing strikes (nearest strike if a side cannot be bracketed).
- No rolls; the 21-DTE review is a hard close.
- Exits and `flatten` still need market data (leg marks) to price the limit; with 10197 they abstain like everything else.
- Not scheduled yet: add a launchd job on the Mini once data works (journal-only first).
- Live is not armed and the schema cannot express it (`paper_only: true`, `required_account_prefix: DU`).
