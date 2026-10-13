# Shared env for Mini launchd jobs (sourced). launchd has a minimal PATH.
export PATH="/opt/homebrew/bin:/usr/local/bin:$HOME/.local/bin:$HOME/.cargo/bin:/usr/bin:/bin:/usr/sbin:/sbin"
REPO="${OTB_REPO:-$HOME/Documents/GitHub Repos/options-trading-bot}"
LOG="$HOME/Library/Logs/otb-watchdog.log"
STATUS="$HOME/Library/Application Support/otb/status.json"
EXPECTED_ACCOUNT="${OTB_EXPECTED_ACCOUNT:-DUT116016}"
mkdir -p "$(dirname "$STATUS")" "$(dirname "$LOG")"
log(){ echo "$(date '+%F %T %Z') [$1] ${*:2}" >>"$LOG"; }
ensure_colima(){
  if ! docker info >/dev/null 2>&1; then
    log "$1" "docker not reachable; colima start"
    colima start >>"$LOG" 2>&1 || { log "$1" "colima start failed"; return 1; }
  fi
}
