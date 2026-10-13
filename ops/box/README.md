# Box runtime: NOT VIABLE

**The box is not a viable runtime for IB Gateway.** Its egress only allows proxied traffic (443 works);
IBKR login ports 4000/4001 are blocked, so the Gateway never logs in. The Mac Mini is the runtime
(see `ops/mini/`). The box cron watchdog lines were removed on 2026-10-12. Notes below are kept for history.

## Original plan (superseded)

The plan was for the Grok Bot box (Debian 13, always on) is the primary runtime
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

## Blocker found 2026-10-12
The box's network only lets outbound traffic through a proxy (every hostname resolves to
198.18.0.1). Port 443 connects, but IBKR's login servers on port 4000/4001
(`ndc1/cdc1/gdc1.ibllc.com`) can't be reached, so the Gateway sits at "Connecting to server"
and never logs in. Also tried `LocalServerPort=443` in jts.ini: same result. The watchdog cron
is paused until this is solved (need direct TCP to IBKR on 4000/4001, or another host such as a VPS).
Also: the bind dir must belong to uid 1000 (`sudo chown 1000:1000 tws_settings`) or the container crash-loops.
