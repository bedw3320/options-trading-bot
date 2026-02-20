# Options Trading Knowledge Vault

This is an arscontexta-generated knowledge system for options trading strategy research. If it won't exist next session, write it down now.

## Philosophy

This vault decomposes options trading research into atomic, linkable, refinable claims. Every note captures one insight — a Greek dynamic, a parameter range, a failure mode, an academic finding. The value compounds through connections: when a new claim about vanna links to existing notes on skew and EM risk, the graph becomes more than the sum of its parts.

**Discovery-first design:** Before creating any note, ask: how will a future session find this? Every note needs a descriptive title (prose sentence expressing the claim), a YAML description, topic map membership, and wiki-links to related concepts. If an agent can't find it, it doesn't exist.

## Session Rhythm

Every session follows three phases:

### Orient
1. Read `ops/goals.md` for current threads
2. Check `ops/tasks.md` and `ops/queue/` for pending work
3. Scan `ops/observations/` and `ops/tensions/` for accumulated signals
4. Review `ops/reminders.md` for time-bound items

### Work
Execute the session's purpose. During work:
- Create notes following the claim template in `templates/claim.md`
- Use `[[wiki links]]` to connect related concepts
- Capture observations in `ops/observations/` when something surprising happens
- Capture tensions in `ops/tensions/` when new content contradicts existing claims

### Persist
1. Update `ops/goals.md` with current state
2. Commit changes to git

## Atomic Notes

Every note in `notes/` captures one claim, titled as a complete sentence:

**Good:** `the skew risk premium is real and persistent with approximately half of implied skew representing compensatable risk premium.md`
**Bad:** `skew premium.md` or `section 4.1 notes.md`

### Composability Test
Before writing, verify:
- **Standalone sense:** Does the title convey the insight without opening the file?
- **Specificity:** Is this one claim, not three bundled together?
- **Clean linking:** Can other notes reference this via `[[title]]` and have it read as prose?

### YAML Frontmatter
Every note requires:
```yaml
---
description: "~150 char summary adding info beyond the title"
category: ""  # academic-claim | parameter-range | greek-dynamic | failure-mode | regime-filter | open-question | trade-mechanic | instrument-profile
created: YYYY-MM-DD
topics: []  # wiki-links to parent MOCs
---
```

Optional fields: `source`, `confidence` (proven/likely/experimental/outdated), `instruments`, `parameters`, `superseded_by`, `validated_by`

## Wiki Links

`[[wiki links]]` are the invariant reference form. Every connection between notes uses this syntax.

### Link Philosophy
Connections are propositional — they make arguments, not citations. When linking, articulate HOW the notes relate:
- "Since [[vanna is the dominant second-order Greek in risk reversals]], the position gets longer delta as vol rises"
- "This contradicts [[zero-cost risk reversals are approximately theta-neutral]] when the underlying moves significantly"

### Link Types
- **Inline links:** Preferred. Weave into the body text as prose arguments.
- **Footer links:** In the `## Connections` section for relationships that don't fit inline.

All links must resolve to existing files. No dangling links.

## Topic Maps (MOCs)

Topic maps organize notes into navigable clusters. Three levels:

| Level | Purpose | Example |
|-------|---------|---------|
| Hub | Workspace entry point | `index.md` |
| Domain | Major knowledge area | `greeks-and-volatility.md`, `risk-reversals.md` |
| Topic | Focused sub-area | `screening-and-filters.md`, `execution-parameters.md` |

### When to Create
- **New topic map:** When 5+ notes cluster around an unlisted theme
- **Split:** When a topic map exceeds 40 entries with distinct sub-communities
- **Merge:** When two topic maps share 50%+ of their notes

Every non-MOC note declares its topic map membership in the `topics` YAML field.

## Processing Pipeline

### Phase 1 — Capture (Record)
Drop raw material into `inbox/`. Zero friction. Sources, rough notes, links to investigate.

### Phase 2 — Extract (Reduce)
Process inbox items into atomic claims in `notes/`. For each source:
1. Read the full source
2. Identify distinct claims, parameter ranges, dynamics, failure modes
3. For each: create an atomic note using `templates/claim.md`
4. Assign appropriate category and confidence level
5. Add wiki-links to related existing notes
6. Register in relevant topic maps
7. Move processed source to `archive/`

### Phase 3 — Connect (Reflect)
Find relationships between notes:
1. Pick a note or topic area
2. Search for semantic relatives (shared instruments, overlapping parameters, contradicting claims)
3. Add wiki-links between related notes
4. Update topic maps with new entries
5. Identify gaps — claims that reference concepts without supporting notes

### Phase 4 — Verify
Quality check:
1. **Description test:** Can you predict the note's content from title + description alone?
2. **Schema test:** Required fields present? Enum values valid?
3. **Health test:** Links resolve? Topic map membership declared? Not orphaned?

### Backward Pass (Reweave)
After adding new notes, revisit older notes that might benefit:
- Sharpen claims with new evidence
- Add links to newly created related notes
- Split notes that have grown beyond one claim
- Mark outdated claims with `superseded_by`

## Schema

### Extraction Categories
| Category | Description |
|----------|-------------|
| `academic-claim` | Published research findings with citations |
| `parameter-range` | Quantitative thresholds: deltas, DTE, sizing |
| `greek-dynamic` | How Greeks behave under specific conditions |
| `failure-mode` | Scenarios where the strategy breaks |
| `regime-filter` | Market conditions gating entry/exit |
| `open-question` | Unresolved items needing research or backtests |
| `trade-mechanic` | Execution details: strike selection, rolls, orders |
| `instrument-profile` | Characteristics of specific tickers/ETFs |

### Confidence Levels
| Level | Meaning |
|-------|---------|
| `proven` | Multiple academic studies or extensive backtesting |
| `likely` | Single study or strong practitioner consensus |
| `experimental` | Untested hypothesis or single-source claim |
| `outdated` | Superseded by newer evidence |

### Query Patterns (ripgrep)
```bash
# Find all parameter ranges
rg "category: parameter-range" knowledge/notes/ -l

# Find notes about a specific instrument
rg "instruments:.*EWZ" knowledge/notes/ -l

# Find experimental claims needing validation
rg "confidence: experimental" knowledge/notes/ -l

# Find orphan notes (no topic map membership)
rg "topics: \[\]" knowledge/notes/ -l

# Count notes by category
rg "category:" knowledge/notes/ -o | sort | uniq -c | sort -rn
```

## Templates

Templates live in `knowledge/templates/`. They define the required structure for each note type.

- `claim.md` — The primary template for all atomic notes
- `moc.md` — Template for topic maps

The `_schema` block in each template is the single source of truth for validation. When creating new note types, create a template first, then validate against it.

## Maintenance

### Condition-Based Triggers
| Condition | Threshold | Action |
|-----------|-----------|--------|
| Orphan notes (no topic map) | 5+ | Run reflect to categorize |
| Pending observations | 10+ | Run rethink to review |
| Pending tensions | 3+ | Resolve contradictions |
| Unprocessed inbox items | 5+ | Run reduce on oldest |
| Dangling wiki-links | Any | Create target notes or remove links |

### Health Metrics
Track these periodically:
- Total note count, growth rate
- Connection density (links per note)
- Orphan percentage
- Dangling link count
- Category distribution

## Self-Evolution

This system evolves through three feedback loops:

1. **Observations** (`ops/observations/`): Capture friction, surprises, methodology insights during work. When 10+ accumulate, review and promote durable ones to `notes/` or `ops/methodology/`.

2. **Tensions** (`ops/tensions/`): Capture contradictions between notes. When new evidence conflicts with existing claims, create a tension. Resolve by updating the weaker claim or adding nuance to both.

3. **Methodology** (`ops/methodology/`): The vault's self-knowledge. Why it's configured this way, what processing patterns work, how the system has evolved.

## Graph Analysis

The vault is a graph database on the filesystem. Notes are nodes, wiki-links are edges, YAML is the property store, ripgrep is the query engine.

### Analysis Scripts
Located in `ops/scripts/graph/`:
- Orphan detection: notes with no inbound links
- Dangling link detection: links pointing to non-existent notes
- Backlink counting: most-referenced notes (knowledge hubs)
- Link density: average connections per note
- Cluster detection: groups of densely connected notes
- Synthesis opportunities: note pairs with many shared neighbors but no direct link

## Common Pitfalls

### Collector's Fallacy (HIGH RISK)
Options research is abundant. Resist the urge to extract everything. Apply the selectivity gate: does this claim add genuine insight beyond what's already captured?

### Orphan Drift (HIGH RISK)
High creation volume during a reduce session can leave notes unconnected. Always run a reflect pass after reducing a source document.

### Verbatim Risk (HIGH RISK)
Parameter tables from research documents tempt verbatim reproduction. Transform every extraction into your own framing. The note title should express the insight, not label the source section.

### Parameter Staleness (MEDIUM RISK)
Market conditions change. Quantitative parameters (IV levels, skew readings, current opportunity assessments) need freshness dates. Use the `created` field and mark outdated claims.

## Directory Structure

```
knowledge/
├── CLAUDE.md                    # This file — vault methodology
├── .arscontexta                 # Vault marker
├── notes/                       # Knowledge graph
│   ├── index.md                 # Hub MOC
│   ├── [domain-mocs].md         # Domain/topic MOCs
│   └── [prose-titled-notes].md  # Atomic claims
├── inbox/                       # Raw capture — zero friction
├── archive/                     # Processed sources
├── templates/                   # Note templates
│   ├── claim.md
│   └── moc.md
└── ops/
    ├── derivation.md            # Configuration rationale
    ├── derivation-manifest.md   # Machine-readable config
    ├── config.yaml              # Human-editable settings
    ├── goals.md                 # Current threads
    ├── tasks.md                 # Task queue
    ├── reminders.md             # Time-bound actions
    ├── methodology/             # Vault self-knowledge
    ├── observations/            # Friction signals
    ├── tensions/                # Contradictions
    ├── queue/                   # Processing pipeline state
    ├── sessions/                # Session logs
    ├── health/                  # Validation reports
    └── scripts/graph/           # Graph analysis scripts
```
