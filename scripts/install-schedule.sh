#!/usr/bin/env bash
# Install the 10:00 daily cycle as a launchd agent (section 28).
#
# launchd rather than cron on macOS: cron skips a run outright if the Mac was
# asleep at the time, while launchd runs a missed job once the machine wakes. For a
# daily brief that is the difference between a late mail and no mail.
#
#   ./scripts/install-schedule.sh            # install and load
#   ./scripts/install-schedule.sh --remove   # unload and delete
#
# The agent inherits no shell environment, so it loads .env itself. Credentials stay
# in .env (gitignored, chmod 600) and never reach the plist, which is world-readable.

set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LABEL="com.antier.content-intelligence.daily"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
HOUR="${DAILY_HOUR:-10}"
MINUTE="${DAILY_MINUTE:-0}"

if [[ "${1:-}" == "--remove" ]]; then
  launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
  rm -f "$PLIST"
  echo "removed $LABEL"
  exit 0
fi

[[ -x "$REPO/.venv/bin/python" ]] || { echo "no venv at $REPO/.venv" >&2; exit 1; }

# A wrapper, because launchd runs the job with an empty environment: no PATH, no
# .env, no locale. Sourcing .env here keeps the password out of the plist.
cat > "$REPO/scripts/daily-wrapper.sh" <<WRAP
#!/usr/bin/env bash
set -euo pipefail
cd "$REPO"
if [[ -f .env ]]; then set -a; . ./.env; set +a; fi
exec "$REPO/.venv/bin/python" "$REPO/scripts/run_daily.py" "\$@"
WRAP
chmod 700 "$REPO/scripts/daily-wrapper.sh"

mkdir -p "$HOME/Library/LaunchAgents" "$REPO/outputs"
cat > "$PLIST" <<PL
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key>
  <array>
    <string>$REPO/scripts/daily-wrapper.sh</string>
  </array>
  <key>StartCalendarInterval</key>
  <dict>
    <key>Hour</key><integer>$HOUR</integer>
    <key>Minute</key><integer>$MINUTE</integer>
  </dict>
  <key>WorkingDirectory</key><string>$REPO</string>
  <key>StandardOutPath</key><string>$REPO/outputs/launchd.out.log</string>
  <key>StandardErrorPath</key><string>$REPO/outputs/launchd.err.log</string>
  <key>RunAtLoad</key><false/>
  <key>ProcessType</key><string>Background</string>
</dict>
</plist>
PL

launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"

printf 'installed %s at %02d:%02d local time\n' "$LABEL" "$HOUR" "$MINUTE"
echo
echo "  check   launchctl print gui/$(id -u)/$LABEL | head -20"
echo "  run now launchctl kickstart -p gui/$(id -u)/$LABEL"
echo "  logs    tail -f $REPO/outputs/launchd.err.log"
echo "  remove  ./scripts/install-schedule.sh --remove"
echo
echo "launchd uses local time, so 10:00 follows the Mac's clock. The machine must be"
echo "awake or asleep-but-not-shut-down; a missed run fires when it wakes."
