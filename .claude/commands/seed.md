You are the queue initialization engine for the options trading knowledge vault at `knowledge/`.

## Mission

Register a source document for processing. Validate the source, check for duplicates against already-processed sources, copy to inbox, and create a queue entry.

## Target: $ARGUMENTS

Parse:
- If target is a file path: register that file as a new source
- If target is empty: list current queue state from `knowledge/ops/tasks.md`

## Workflow

1. **Validate source exists** and is readable
2. **Check for duplicates** — has this file (or a very similar one) already been processed?
   ```bash
   ls knowledge/archive/
   rg "$(basename "$target")" knowledge/ops/tasks.md
   ```
3. **Copy source to inbox** (or symlink if it should stay in place)
4. **Add queue entry** to `knowledge/ops/tasks.md`:
   ```
   | ID | Source | Phase | Status | Notes |
   | N  | filename | reduce | pending | Brief description |
   ```
5. **Estimate extraction scope** — how many atomic claims might this source yield?
6. **Report:** Source registered, queue position, estimated claims

## After Seeding

Suggest running `/project:reduce [source-path]` to begin extraction.
