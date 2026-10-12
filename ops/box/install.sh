#!/usr/bin/env bash
# Install box runtime: docker, cron, and watchdog crontab (@reboot + every 2 min).
set -euo pipefail
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq docker.io docker-compose cron
W=/home/box/options-trading-bot/ops/box/watchdog.sh
( crontab -l 2>/dev/null | grep -v ib-watchdog || true
  echo "@reboot $W # ib-watchdog"
  echo "*/2 * * * * $W # ib-watchdog" ) | crontab -
sudo service cron start || true
$W
