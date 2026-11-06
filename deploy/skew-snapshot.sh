#!/bin/bash
# Optional launchd helper for com.otb.skew-snapshot. Paper / readonly only.
# Not installed by ops/mini/install.sh. See research/README.md.
set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
REPO="${OTB_REPO:-$(cd "$DIR/.." && pwd)}"
cd "$REPO" || exit 1
export PATH="/opt/homebrew/bin:/usr/local/bin:$HOME/.local/bin:$HOME/.cargo/bin:/usr/bin:/bin:/usr/sbin:/sbin"
export TRADING_MODE=paper ALLOW_TRADING=false
export IB_GATEWAY_HOST="${IB_GATEWAY_HOST:-127.0.0.1}"
export IB_GATEWAY_PORT="${IB_GATEWAY_PORT:-4002}"
LOG="${OTB_SKEW_LOG:-$HOME/Library/Logs/otb-skew-snapshot.log}"
mkdir -p "$(dirname "$LOG")"
clog(){ echo "$(date '+%F %T %Z') $*" >>"$LOG"; }
if [ "${1:-}" != "--force" ]; then
  dow=$(TZ=America/New_York date +%u)
  hm=$(TZ=America/New_York date +%H%M)
  { [ "$dow" -le 5 ] && [ "$hm" -ge 1540 ] && [ "$hm" -le 1610 ]; } || exit 0
fi
clog "skew-snapshot start sha=$(git rev-parse --short HEAD 2>/dev/null)"
perl -e 'alarm 600; exec @ARGV' uv run --quiet python -m research.skew_snapshot >>"$LOG" 2>&1
rc=$?
clog "skew-snapshot end rc=$rc"
exit $rc
