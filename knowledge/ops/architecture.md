# Options-trading-bot architecture

Source of truth for planes, tools, and boundaries. Amended with Zishan 2026-09-12.
Product-in-force (structure / closes) locked with Will 2026-11-11: see
[`exit-strategy.md`](exit-strategy.md) and [`STATUS.md`](../../STATUS.md)
walking-slice Epic 6. This diagram is harness planes, not the strategy YAML.

## Diagram

```mermaid
flowchart TB
  subgraph Ops["1 · Ops — Burry chat"]
    O1[Research wakes · joust · Epic status]
    O2[No TWS_* · no orders · no state.db writes]
  end

  subgraph Source["2 · Source — GitHub artifact"]
    L[LOOP.md]
    RM[ROADMAP]
    CORE[core/]
    STRAT[strategies/]
    KNOW[knowledge/]
    IBKRMOD[integrations/ibkr/]
  end

  subgraph Decision["3 · Decision — Intent only"]
    YAML[Strategy YAML + PydanticAI agent]
    INTENT[TradeIntent / OrderIntent]
    YAML --> INTENT
  end

  subgraph Harness["4 · Harness — fence"]
    G1[Validate schema]
    G2[Identity abort]
    G3[Risk · arm · audit]
    G4[Preview → token → place]
    G1 --> G2 --> G3 --> G4
  end

  subgraph Hands["5 · Hands — Mac Mini"]
    COL[Colima]
    GW["gnzsnz/ib-gateway 4002→socat 4004"]
    ENV[".env paper secrets"]
    EXEC[ib_insync adapter]
    DB[(state.db)]
    UV[uv runtime]
  end

  subgraph Venue["6 · Venue — IBKR"]
    PAP["Paper DUT116016"]
    LIV["Live U****8141 — non-target"]
  end

  Cloud["Cursor Cloud — edits Source only"] -.-> Source
  Ops -.->|ops / open PRs| Cloud
  Ops -.->|status / kill intent| Hands
  Source -->|pull| Hands
  Source --> Decision
  INTENT -->|never imports ib_insync| Harness
  Harness --> EXEC
  UV --> EXEC
  COL --> GW
  ENV --> GW
  EXEC --> GW
  GW --> PAP
  EXEC --> DB
  PAP -->|fills| DB
  LIV -.->|abort if seen| G2
```

Paper **DUT116016** is the testing-period risk cap (equity/margin). Mask any
live account id as `U****8141`. Never copy TWS secrets or `.env`.

## Tool opinions (Zishan)

| Tool | Verdict | Notes |
|---|---|---|
| Colima + Docker | Keep | Isolates Gateway; Mini only |
| gnzsnz/ib-gateway | Keep (pin digest) | Paper 4002→4004; no live in same compose |
| ib_insync | Keep | Execution adapter only; strategies never import |
| uv | Keep | Mini toolchain + lockfile |
| SQLite state.db | Keep | Mini only |
| PydanticAI | Keep, scope-lock | Decision → intents; not harness gates |
| Strategy YAML | Keep | Cloud edits; Mini loads |

## In force vs as-built (2026-11-11)

- **In force:** standard RR (short put + long call), no protective put, no
  defined max loss, no automated yellow-zone exits, manual flatten only.
- **As-built:** `strategies/active/us-large-cap-rr.yaml` is the loaded
  standard RR. `spy-defined-risk-rr.yaml` remains as superseded/historical.
- Watchlist (`strategies/watchlist.yaml`) exists for Epic 5 research intake.
  The runner does not load it.

## Gaps not to draw as shipped

These are remaining harness gaps, not a Day-1 snapshot:

- Epic 0 paper fill: **done** (2026-10-06, DUT116016). See
  [`2026-10-06-epic0-paper-fill.md`](2026-10-06-epic0-paper-fill.md).
- Identity + GuardedBroker + mock broker + idempotency + paper flatten: **done**.
- Still open: stale-quote reject, constraint 3 autonomy latch, live arming.
- Walking-slice Epic 4 Mini paper demo (reconcile / debrief / manual flatten)
  is remaining evidence. Automated 21-DTE / −$1,250 / +$1,000 exits are
  **not** that demo — they are deferred to Epic 6.
