# Research pipeline v0

Deliberately small. Will approved: **1 theme, 3 candidate names, all `record_only`**.
No multi-name trading, no auto event calendars, no runner changes to place orders
on new names. Paper only. The LLM proposes; code decides.

The runner still does **not** read `strategies/watchlist.yaml` (Epic 5 — do not
start it). This folder is observational: schema, CI lint, a liquidity screen,
and a daily skew snapshot.

## Steps (v0)

1. **Theme intake** — one theme. CI fails if `record_only` names span more than
   one `theme:` (cap: 3 names).
2. **Three candidates with sources** — each non-SPY row needs `sources:` (>=1),
   a written `thesis`, and a structured `falsifier` `{metric, threshold, source, expires}`.
   Pre-register `forecast_horizon` + `registered_at` (and `probability` when a
   human writes one — do not invent) **before** looking at outcomes.
3. **Code liquidity screen** — `python -m research.screen` against IB Gateway
   paper **4002**. Finds the ~25-delta put and call at 30–45 DTE plus the put/call
   wings (`wing_width` from the SPY strategy YAML). Reports OI, volume, bid/ask
   spread (abs and % of mid), quote age, and `data_source`. Delayed data is
   labelled and marked `diagnostic_only`.
4. **Pre-registered thesis + falsifier → `record_only`** — a tripped or expired
   falsifier means no new entries (`schemas.watchlist.falsifier_blocks_new_entries`).
   Thesis direction and skew direction must agree before a name can be active
   (`thesis_agrees_with_skew`; skew data comes later). Missing or stale evidence
   blocks promotion (`evidence_blocks_promotion`). Only Will may set
   `approved_by: will` + `approved_on`.
5. **Later (not this slice):** skew fit vs each name's own history; controls vs
   SPY-only and vs random liquid names with mid±slippage fills; **12-week stop
   rule** on the experiment.

## Thresholds — PROPOSALS for Will

Liquidity numbers are **not** re-stated in strategy YAML. The screen reads them
from `strategies/active/spy-defined-risk-rr.yaml` `rules.structure`:

| Field | Current YAML | Note |
|---|---|---|
| `min_open_interest` | 500 | inherited |
| `max_spread_pct_of_mid` | 10 | inherited |
| DTE window | 30–45 (target 38) | inherited |
| `wing_width` | $20 | SPY dollar width; applying it to single names is a proposal |
| `max_quote_age_seconds` | 60 | in `research/config.yaml` |
| evidence stale after | 30 days | `EVIDENCE_STALE_AFTER_DAYS` |
| exits `dte_close` | 21 | per-name `exits:` in the watchlist; copied from SPY YAML |

Override in `research/config.yaml` only. Do not edit the strategy YAML from here.

## Commands

Watchlist lint (also run in CI):

```bash
uv run python scripts/validate_watchlist.py
```

Liquidity screen on the Mini (Gateway paper 4002, readonly, no orders):

```bash
cd ~/"Documents/GitHub Repos/options-trading-bot"   # or $OTB_REPO
TRADING_MODE=paper IB_GATEWAY_HOST=127.0.0.1 IB_GATEWAY_PORT=4002 \
  uv run python -m research.screen
# optional: --tickers CRWV --client-id 21
```

Writes `research/screens/<YYYY-MM-DD>.{json,md}` (gitignored). If IB
`marketDataType` is delayed/frozen, every ticker is `diagnostic_only`.

Offline (fixtures):

```bash
uv run python -m research.screen --fixture tests/fixtures/research/liquid_chain.json --output-dir /tmp/screens
```

Daily skew snapshot (same Gateway; separate SQLite file):

```bash
TRADING_MODE=paper IB_GATEWAY_HOST=127.0.0.1 IB_GATEWAY_PORT=4002 \
  uv run python -m research.skew_snapshot
```

Persists to `state/research.db` (not `state.db`). Delta convention:
`ib_model_signed` (IB model Greeks, puts negative). Delayed or stale quotes
are skipped with a recorded `skip_reason`.

## Why `state/research.db` and not `state.db`

Trading lineage (cycles, fills, kill switch, decision records) is the Epic 1
product and has its own schema/migrations. Skew snapshots are observational
and must not share those migrations. Keeping a second file under `state/`
means a Mini backup of that directory still captures both; both are gitignored.

## Install the snapshot job on the Mini (optional)

**Not installed by `ops/mini/install.sh`. Do not assume it is loaded.**

See [`deploy/README.md`](../deploy/README.md). Short form:

```bash
chmod +x deploy/skew-snapshot.sh
sed -e "s#__DIR__#$PWD/deploy#g" -e "s#__HOME__#$HOME#g" -e "s#__REPO__#$PWD#g" \
  deploy/com.otb.skew-snapshot.plist.template \
  > ~/Library/LaunchAgents/com.otb.skew-snapshot.plist
launchctl bootout "gui/$(id -u)/com.otb.skew-snapshot" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" ~/Library/LaunchAgents/com.otb.skew-snapshot.plist
```

Weekday 15:50 ET. Force: `bash deploy/skew-snapshot.sh --force`.

## Current watchlist (v0)

- **SPY** — `active` / bullish / index baseline. Already the paper strategy.
  `approved_by: will`. No issuer falsifier (TODO; do not invent).
- **CRWV** — `record_only` / bearish / theme `ai-neocloud-financing`. One of
  three candidate slots. Two slots empty until Will writes theses with sources.

## Deferred

- Wiring the watchlist into `core/cycle.py` / the runner (Epic 5).
- Per-name wing width, borrow/short-interest for call-rich names, 10y block.
- Auto event calendars.
- Skew-percentile history per name (needs this snapshot job to accumulate).
- Controls vs SPY-only and random liquid names; 12-week stop as code, not a comment.
- Live IBKR data (still CBOE delayed on the Mini until the share is unlocked).
