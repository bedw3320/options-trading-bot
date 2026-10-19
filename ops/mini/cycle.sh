#!/bin/bash
# launchd com.otb.cycle fires at :00/:15/:30/:45; this gates to weekdays 10:00-15:30 ET and runs
# ONE record-only paper cycle (journal only, never --allow-trading). Logs: ~/Library/Logs/otb-cycle.log
# Manual: bash ops/mini/cycle.sh --force   (skip the time gate)
source "$(dirname "$0")/common.sh"
cd "$REPO" || exit 1
clog(){ echo "$(date '+%F %T %Z') $*" >>"$CYCLE_LOG"; }
if [ "${1:-}" != "--force" ]; then
  dow=$(TZ=America/New_York date +%u); hm=$(TZ=America/New_York date +%H%M)
  { [ "$dow" -le 5 ] && [ "$hm" -ge 1000 ] && [ "$hm" -le 1530 ]; } || exit 0
fi
export TRADING_MODE=paper ALLOW_TRADING=false   # record-only lock; .env cannot override (dotenv doesn't overwrite)
export IB_GATEWAY_HOST="${IB_GATEWAY_HOST:-127.0.0.1}" IB_GATEWAY_PORT="${IB_GATEWAY_PORT:-4002}"
clog "run start source=${MARKET_DATA_SOURCE:-.env/ib} sha=$(git rev-parse --short HEAD 2>/dev/null)"
perl -e 'alarm 600; exec @ARGV' uv run --quiet python -m core.cli run >>"$CYCLE_LOG" 2>&1
rc=$?
clog "run end rc=$rc"
uv run --quiet python -m core.cli list --limit 1 --json 2>/dev/null >"$LAST_CYCLE.tmp" && mv "$LAST_CYCLE.tmp" "$LAST_CYCLE"
exit $rc
