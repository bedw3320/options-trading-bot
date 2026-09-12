# Options-trading-bot architecture

Source of truth for planes, tools, and boundaries. Amended with Zishan 2026-09-12.

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
    LIV["Live U28048141 — non-target"]
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

## Gaps not to draw as shipped

- strategies/active empty
- identity abort + preview-token not in code
- Epic 0 fill pending
