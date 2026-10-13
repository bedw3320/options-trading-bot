#!/bin/bash
# RunAtLoad at login: start Colima and the gateway stack (restart: unless-stopped keeps it up).
source "$(dirname "$0")/common.sh"
cd "$REPO" || exit 1
ensure_colima start || exit 1
docker compose up -d ib-gateway >>"$LOG" 2>&1 && log start "compose up -d ib-gateway ok"
