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
cur=$(gh api "repos/$R/contents/$P?ref=$B" --jq .sha 2>/dev/null || true)
args=(-X PUT "repos/$R/contents/$P" -f message="heartbeat $(date -u +%FT%TZ)" -f branch="$B" -f content="$(base64 <"$STATUS" | tr -d '\n')")
[ -n "$cur" ] && args+=(-f sha="$cur")
gh api "${args[@]}" >/dev/null 2>>"$LOG" || log hb "push failed"
