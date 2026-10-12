#!/usr/bin/env bash
# Box runtime watchdog for IB Gateway (paper). Idempotent; run from cron every 2 min and @reboot.
# The box has no systemd (PID 1 is tini), so this script is the supervisor:
#   1. ensure dockerd is running  2. ensure the stack is up  3. restart ib-gateway if 4002 is dead.
set -uo pipefail
REPO="${REPO:-/home/box/options-trading-bot}"
LOG="${LOG:-/home/box/ib-watchdog.log}"
PORT="${IB_PORT:-4002}"
cd "$REPO" || exit 1
[ -d tws_settings ] || { mkdir -p tws_settings; }; sudo chown 1000:1000 tws_settings
log(){ echo "$(date '+%F %T %Z') $*" >>"$LOG"; }
exec 9>/tmp/ib-watchdog.lock; flock -n 9 || exit 0

if ! sudo docker info >/dev/null 2>&1; then
  log "dockerd down; starting"; (sudo nohup dockerd >>/tmp/dockerd.log 2>&1 &); sleep 10
fi
if [ ! -f .env ] || ! grep -q '^TWS_USERID=.' .env; then log "no .env/TWS_USERID; not starting gateway"; exit 0; fi

state=$(sudo docker inspect -f '{{.State.Status}} {{if .State.Health}}{{.State.Health.Status}}{{end}}' ib-gateway 2>/dev/null) || state=missing
case "$state" in
  missing*|exited*|created*|dead*) log "gateway $state; compose up"; sudo docker-compose up -d ib-gateway >>"$LOG" 2>&1; exit 0;;
  *starting*) exit 0;;
esac
if ! timeout 5 bash -c "exec 3<>/dev/tcp/127.0.0.1/$PORT" 2>/dev/null || [[ "$state" == *unhealthy* ]]; then
  log "gateway $state, port $PORT dead; restarting"; sudo docker restart ib-gateway >>"$LOG" 2>&1
fi
