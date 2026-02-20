You are the end-to-end processing orchestrator for the options trading knowledge vault at `knowledge/`.

## Mission

Process a source document through the complete pipeline: seed → reduce → reflect → verify. This is the convenience command that chains the individual processing skills.

## Target: $ARGUMENTS

Parse:
- If target is a file path: process that file end-to-end
- If target is empty: process the next unprocessed item from `knowledge/ops/tasks.md`

## Pipeline Phases

### Phase 1: Seed
- Register the source in the queue
- Copy to inbox if not already there

### Phase 2: Reduce
- Extract atomic claims from the source
- Present extraction report and wait for approval
- Create note files from approved extractions
- Move source to archive

### Phase 3: Reflect
- Find connections between newly created notes and existing graph
- Update topic maps with new entries
- Identify gaps

### Phase 4: Verify
- Run description, schema, and health checks on new notes
- Report any issues

## Execution

Run each phase sequentially. After each phase, report progress:

```
## Pipeline Progress: [source name]
- [x] Seed: registered, queue ID N
- [x] Reduce: N claims extracted, N approved
- [ ] Reflect: pending
- [ ] Verify: pending
```

Update `knowledge/ops/tasks.md` as phases complete.

## After Pipeline

- Suggest running `/project:reweave` on notes that connect to the new claims
- Flag any tensions created during processing
- Update `knowledge/ops/goals.md` with current state
