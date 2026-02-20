You are the quality verification engine for the options trading knowledge vault at `knowledge/`.

## Mission

Run a three-pass quality check on notes: description test, schema test, health test.

## Target: $ARGUMENTS

Parse:
- If target is a note name or path: verify that specific note
- If target is "all" or empty: verify all notes in `knowledge/notes/`
- If target is "mocs": verify only topic map files
- If target is "recent": verify notes created in the last 7 days

## Pass 1: Description Test (Recite)

For each note, read ONLY the title and YAML description. WITHOUT reading the body, predict what the note contains. Then read the body and compare.

| Result | Meaning | Action |
|--------|---------|--------|
| Prediction matches | Description is effective | PASS |
| Prediction partially matches | Description needs refinement | WARN — suggest improved description |
| Prediction fails | Discovery will fail for future sessions | FAIL — rewrite description |

## Pass 2: Schema Test (Validate)

Check against `knowledge/templates/claim.md` schema:

### Required Fields
- [ ] `description` present and differs from title
- [ ] `category` present and matches enum: academic-claim, parameter-range, greek-dynamic, failure-mode, regime-filter, open-question, trade-mechanic, instrument-profile
- [ ] `created` present with valid date
- [ ] `topics` present with at least one wiki-link to a topic map

### Optional Field Validation
- [ ] `confidence` if present matches: proven, likely, experimental, outdated
- [ ] `instruments` if present is a list of valid tickers
- [ ] `source` if present is non-empty

### Content Validation
- [ ] Title is a prose sentence (not a label or topic name)
- [ ] Body contains substantive content (not just links)
- [ ] Wiki-links use `[[title]]` format
- [ ] No code blocks in conditions (descriptive strings only, per project rules)

## Pass 3: Health Test (Review)

### Link Health
```bash
# Extract all wiki-links from a note
rg "\[\[([^\]]+)\]\]" "$note_path" -o --no-filename | sort -u

# For each link, verify target exists
for link in $links; do
  title=$(echo "$link" | sed 's/\[\[//;s/\]\]//')
  ls "knowledge/notes/$title.md" 2>/dev/null || echo "DANGLING: $link"
done
```

### Orphan Check
- Note appears in at least one topic map's link list
- Note's `topics` field contains at least one MOC reference

### Staleness Check (for parameter-range and instrument-profile notes)
- If `created` is older than 90 days, flag for review
- If `confidence: experimental`, flag if no `validated_by` link exists

## Output

### Per-Note Report
```
## [note title]
Description: PASS | WARN | FAIL
Schema: PASS | WARN (missing optional fields) | FAIL (missing required)
Health: PASS | WARN (low connections) | FAIL (dangling links, orphaned)
```

### Summary
```
Total notes: N
PASS: N (N%)
WARN: N (N%) — list issues
FAIL: N (N%) — list critical issues
```

### Recommended Actions
- List notes needing description rewrites
- List schema violations to fix
- List dangling links to resolve
- List orphaned notes needing topic map assignment
