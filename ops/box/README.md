# Box runtime (primary)

As of 2026-10-12 the Grok Bot box (Debian 13, always on) is the primary runtime
for IB Gateway + the bot, replacing the Mac Mini (whose Grok Bot app kept going offline).

- Repo: `/home/box/options-trading-bot`
- Install: `./ops/box/install.sh` (docker.io, docker-compose v2, cron, crontab entries)
- Supervisor: no systemd on the box (PID 1 is tini), so `ops/box/watchdog.sh` runs from
  cron `@reboot` and every 2 min: starts dockerd if needed, `docker-compose up -d ib-gateway`
  if the container is missing/exited, and restarts it if 127.0.0.1:4002 is dead or unhealthy.
  Log: `/home/box/ib-watchdog.log`.
- Secrets: gitignored `.env` with `TWS_USERID`, `TWS_PASSWORD` (paper), optional `TRADING_MODE`
  (defaults to paper). Never commit `.env`, `state/`, `tws_settings/`.
- Probe: `IB_GATEWAY_HOST=127.0.0.1 IB_GATEWAY_PORT=4002 uv run python scripts/probe_option_quotes.py`

Caveat: if the box restarts, cron itself must be running for `@reboot` to fire; if it isn't,
any agent can run `sudo service cron start && ops/box/watchdog.sh`.
