#!/bin/bash
# Every 10 min: PUT status.json to branch `heartbeat` (file heartbeat/status.json) via gh api.
# Read it from anywhere: gh api repos/bedw3320/options-trading-bot/contents/heartbeat/status.json?ref=heartbeat --jq .content | base64 -d
source "$(dirname "$0")/common.sh"
R=bedw3320/options-trading-bot; B=heartbeat; P=heartbeat/status.json
[ -f "$STATUS" ] || echo '{"gateway_logged_in":false,"last_error":"no watchdog run yet"}' >"$STATUS"
if ! gh api "repos/$R/branches/$B" >/dev/null 2>&1; then
  sha=$(gh api "repos/$R/git/ref/heads/main" --jq .object.sha) &&
  gh api -X POST "repos/$R/git/refs" -f ref="refs/heads/$B" -f sha="$sha" >/dev/null || { log hb "create branch failed"; exit 1; }
fi
# Merge watchdog status + last cycle (cycle_id, outcome, first reason) into the pushed JSON.
OUT="$STATUS.hb"
cd "$REPO" && uv run --quiet python - "$STATUS" "$LAST_CYCLE" >"$OUT" 2>>"$LOG" <<'PY' || cp "$STATUS" "$OUT"
import json, sys
s = json.load(open(sys.argv[1]))
try:
    c = (json.load(open(sys.argv[2])) or [None])[0]
except Exception:
    c = None
s["last_cycle"] = None if not c else {"cycle_id": c["cycle_id"], "started_at": c["started_at"], "mode": c["mode"],
                                      "decision": c["outcome"], "reason": (c.get("reasons") or [None])[0]}
print(json.dumps(s))
PY
cur=$(gh api "repos/$R/contents/$P?ref=$B" --jq .sha 2>/dev/null || true)
args=(-X PUT "repos/$R/contents/$P" -f message="heartbeat $(date -u +%FT%TZ)" -f branch="$B" -f content="$(base64 <"$OUT" | tr -d '\n')")
[ -n "$cur" ] && args+=(-f sha="$cur")
gh api "${args[@]}" >/dev/null 2>>"$LOG" || log hb "push failed"
