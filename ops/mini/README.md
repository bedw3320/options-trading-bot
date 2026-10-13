# Mac Mini runtime (primary)

The Mini runs IB Gateway (Colima + docker compose, paper) on its own, without the Grok Bot app.

Install / re-install (idempotent), from the repo on the Mini:

    cd ~/"Documents/GitHub Repos/options-trading-bot" && git pull && bash ops/mini/install.sh

What it sets up (user LaunchAgents in ~/Library/LaunchAgents):
- `com.otb.start` (RunAtLoad): `colima start` if needed, `docker compose up -d ib-gateway` (restart: unless-stopped).
- `com.otb.watchdog` (every 120s): Colima up, container running, port 4002 answers, then a real
  ib_insync API check (readonly, clientId 97) that `managedAccounts()` contains DUT116016.
  Port dead → restart. Three consecutive API-check failures past startup (stuck login) → restart.
  Log: `~/Library/Logs/otb-watchdog.log`. Status: `~/Library/Application Support/otb/status.json`.
- `com.otb.heartbeat` (every 600s): pushes that status JSON with `gh api` to branch `heartbeat`,
  file `heartbeat/status.json`. Read it from anywhere:

      gh api 'repos/bedw3320/options-trading-bot/contents/heartbeat/status.json?ref=heartbeat' --jq .content | base64 -d

  The commit time on the `heartbeat` branch is the Mini's last sign of life.
- `pmset`: no system/disk sleep, autorestart after power loss, wake on LAN.

Manual prerequisites (can't be scripted safely):
- Automatic login for this user (System Settings > Users & Groups), which requires FileVault off.
  Without it, after a reboot nothing runs until someone logs in.
- `gh auth login` done on the Mini (the heartbeat uses it), and `uv` installed (`uv sync` once in the repo).
- `.env` with TWS_USERID / TWS_PASSWORD present in the repo root (gitignored).
