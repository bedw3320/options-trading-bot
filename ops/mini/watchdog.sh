#!/bin/bash
# Every 120s: Colima up, ib-gateway up, port 4002 answers, and a real API login check
# (managedAccounts must contain $EXPECTED_ACCOUNT). Writes status.json for heartbeat.sh.
source "$(dirname "$0")/common.sh"
cd "$REPO" || exit 1
exec 9>/tmp/otb-watchdog.lock; /usr/bin/lockf -t 0 9 2>/dev/null || true
write_status(){ # logged_in account error
  printf '{"host":"%s","gateway_logged_in":%s,"account":"%s","expected_account":"%s","last_check":"%s","last_error":"%s"}\n' \
    "$(hostname -s)" "$1" "$2" "$EXPECTED_ACCOUNT" "$(date -u +%FT%TZ)" "$(echo "$3" | tr '"\n' "' " | cut -c1-300)" >"$STATUS"
}
ensure_colima wd || { write_status false "" "colima down"; exit 1; }
state=$(docker inspect -f '{{.State.Status}}' ib-gateway 2>/dev/null) || state=missing
if [ "$state" != running ]; then
  log wd "ib-gateway $state; compose up"; docker compose up -d ib-gateway >>"$LOG" 2>&1
  write_status false "" "gateway was $state; started"; exit 0
fi
started=$(docker inspect -f '{{.State.StartedAt}}' ib-gateway)
age=$(( $(date -u +%s) - $(date -j -u -f '%Y-%m-%dT%H:%M:%S' "${started%%.*}" +%s 2>/dev/null || echo 0) ))
if ! nc -z -G 5 127.0.0.1 4002 >/dev/null 2>&1; then
  if [ "$age" -lt 180 ]; then write_status false "" "starting (age ${age}s)"; exit 0; fi
  log wd "port 4002 dead; restart"; docker restart ib-gateway >>"$LOG" 2>&1
  write_status false "" "port 4002 dead; restarted"; exit 0
fi
out=$(IB_GATEWAY_HOST=127.0.0.1 IB_GATEWAY_PORT=4002 timeout 40 uv run --quiet python - 2>&1 <<'PY'
import os
from ib_insync import IB
ib = IB()
try:
    ib.connect("127.0.0.1", 4002, clientId=97, timeout=20, readonly=True)
    print("ACCOUNTS=" + ",".join(ib.managedAccounts()))
finally:
    ib.disconnect()
PY
)
accts=$(echo "$out" | sed -n 's/^ACCOUNTS=//p')
if echo ",$accts," | grep -q ",$EXPECTED_ACCOUNT,"; then
  write_status true "$accts" ""; rm -f /tmp/otb-api-fail
else
  n=$(( $(cat /tmp/otb-api-fail 2>/dev/null || echo 0) + 1 )); echo $n >/tmp/otb-api-fail
  err=$(echo "$out" | tail -3); log wd "API check failed ($n): accounts='$accts' $err"
  write_status false "$accts" "api check failed x$n: $err"
  # Stuck login: restart after 3 consecutive failures (~6 min), once past startup.
  if [ "$n" -ge 3 ] && [ "$age" -gt 300 ]; then log wd "stuck login; restart"; docker restart ib-gateway >>"$LOG" 2>&1; rm -f /tmp/otb-api-fail; fi
fi
