#!/bin/bash
# Idempotent Mini setup: launchd agents (start at login, watchdog 120s, heartbeat 600s) + power settings.
# Run from the repo:  bash ops/mini/install.sh
set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
LA="$HOME/Library/LaunchAgents"; mkdir -p "$LA" "$HOME/Library/Logs"
chmod +x "$DIR"/*.sh
for t in colima docker gh uv; do command -v $t >/dev/null || PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"; command -v $t >/dev/null || echo "WARN: $t not found in PATH"; done
mk(){ # label script extra-xml
  cat >"$LA/$1.plist" <<PL
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>$1</string>
  <key>ProgramArguments</key><array><string>/bin/bash</string><string>$DIR/$2</string></array>
  $3
  <key>StandardOutPath</key><string>$HOME/Library/Logs/$1.out.log</string>
  <key>StandardErrorPath</key><string>$HOME/Library/Logs/$1.out.log</string>
</dict></plist>
PL
  launchctl bootout "gui/$(id -u)/$1" 2>/dev/null || true
  launchctl bootstrap "gui/$(id -u)" "$LA/$1.plist"
  echo "loaded $1"
}
mk com.otb.start     start.sh     '<key>RunAtLoad</key><true/>'
mk com.otb.watchdog  watchdog.sh  '<key>RunAtLoad</key><true/><key>StartInterval</key><integer>120</integer>'
mk com.otb.heartbeat heartbeat.sh '<key>RunAtLoad</key><true/><key>StartInterval</key><integer>600</integer>'

# Power: never sleep, restart after power loss, wake on network. Needs sudo (asks once).
if sudo -v; then
  sudo pmset -a sleep 0 disksleep 0 displaysleep 10 autorestart 1 womp 1 powernap 0 || true
  sudo pmset -a tcpkeepalive 1 2>/dev/null || true
  echo "pmset applied:"; pmset -g | grep -E ' sleep|autorestart|womp' || true
fi
# Colima should come back too (start.sh also does this); brew service is optional.
command -v brew >/dev/null && brew services list 2>/dev/null | grep -q colima || true

al=$(defaults read /Library/Preferences/com.apple.loginwindow autoLoginUser 2>/dev/null || echo "")
fv=$(fdesetup status 2>/dev/null || echo unknown)
echo
echo "Auto-login user: ${al:-NOT SET}   FileVault: $fv"
[ -z "$al" ] && echo "MANUAL: System Settings > Users & Groups > Automatically log in as $(whoami) (FileVault must be Off). LaunchAgents only run after login."
echo "Status: $HOME/Library/Logs/otb-watchdog.log ; branch 'heartbeat' heartbeat/status.json on GitHub."
