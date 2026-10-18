# Deterministic cycle v0 — SPY defined-risk risk reversal

Strategy: `strategies/active/spy-defined-risk-rr.yaml` (the `rules:` block executes; no LLM in the decision path).
Code: `core/cycle.py` (orchestration), `core/signals.py`, `core/rr_rules.py`, `core/market_state.py`,
`core/brokers.py`, `core/reconcile.py`, `utils/lineage.py`, `integrations/ibkr/combo.py`, CLI `core/cli.py`.

## One cycle (run once, then stop)

1. Start `cycle_id`, record inputs (strategy path + sha256, version, git sha, mode, rules).
2. Kill switch latched? → abstain.
3. Paper mode: identity gate (`assert_paper_identity`, account must be `DU*`, `TRADING_MODE=paper`); failure latches the kill switch. RTH only.
4. Reconcile IB option positions / working orders on SPY vs SQLite. Drift → latch + abstain.
5. Daily realized loss ≥ $1,500 → latch + abstain.
6. Market snapshot (IB or fixture). Any data failure (10197, 162, not subscribed, timeout, exception) → `status=unavailable` → abstain with the reason. Never guesses.
7. Open position → exit rules (time stop 21 DTE, SPY ≤ short put −3%, −$1,250, +$1,000). Else entry: signals → construction → caps.
8. Intent → `GuardedBroker.preview_combo` → token → revalidate (kill, one position, max-loss cap) → BAG limit at mid, DAY.
   Without `--allow-trading` the preview refuses and the cycle ends `proposed_not_sent` (journal only).
9. Wait `fill_wait_seconds` (30); unfilled → cancel. Record fills, open/close the position row, reconcile again.

Outcomes: `entered`, `exited`, `held`, `abstained`, `proposed_not_sent`, `error`. 3 consecutive `error`s latch the kill switch.

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

Paper cycles use clientId 11 (`IB_CYCLE_CLIENT_ID` overrides), readonly unless `--allow-trading`.
A file lock (`state/cycle.lock`) prevents overlapping cycles.

## Known limits (v0)

- Needs IB option quotes + model Greeks + open interest. Until the 10197 competing-session issue is fixed, every paper cycle abstains with `market_data_unavailable: ib_10197_competing_live_session`.
- Open interest arrives on generic tick 101 and may lag; a missing OI fails the liquidity check (abstain, by design).
- Fixtures are SYNTHETIC (Black-Scholes + skew curve, `tests/fixtures/make_spy_fixtures.py`), not market data.
- rr25 percentile is informational until 60 stored observations; then set `skew_percentile_required: true`.
- No rolls; the 21-DTE review is a hard close. A latched kill switch also stops exits (manual review).
- Not scheduled yet: add a launchd job on the Mini once data works (journal-only first).
- Live is not armed and the schema cannot express it (`paper_only: true`, `required_account_prefix: DU`).
