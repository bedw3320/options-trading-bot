# Optional Mini jobs

Templates here are **not** loaded by `ops/mini/install.sh`. Copy and bootstrap
them yourself if you want the job.

## `com.otb.skew-snapshot`

Weekday 15:50 America/New_York (Mac Mini local time should be ET). Runs
`research.skew_snapshot` against IB Gateway paper **4002**, readonly, into
`state/research.db`. Delayed/stale quotes are skipped with a recorded reason.

Install (from the repo root on the Mini):

```bash
chmod +x deploy/skew-snapshot.sh
sed -e "s#__DIR__#$PWD/deploy#g" -e "s#__HOME__#$HOME#g" -e "s#__REPO__#$PWD#g" \
  deploy/com.otb.skew-snapshot.plist.template \
  > ~/Library/LaunchAgents/com.otb.skew-snapshot.plist
plutil -lint ~/Library/LaunchAgents/com.otb.skew-snapshot.plist
launchctl bootout "gui/$(id -u)/com.otb.skew-snapshot" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" ~/Library/LaunchAgents/com.otb.skew-snapshot.plist
```

Force one run: `bash deploy/skew-snapshot.sh --force`

Unload: `launchctl bootout "gui/$(id -u)/com.otb.skew-snapshot"`

This is not assumed to be installed.
