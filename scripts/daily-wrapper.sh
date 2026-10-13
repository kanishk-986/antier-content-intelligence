#!/usr/bin/env bash
set -euo pipefail
cd "/Users/kanishk.raj/antier-content-intelligence"

# Rebuild the PATH launchd does not provide. The directories are resolved at
# install time from the shell that could actually find these tools.
export PATH="/Users/kanishk.raj/.local/bin:/Users/kanishk.raj/.local/bin:$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
export HOME="$HOME"
export LANG="${LANG:-en_US.UTF-8}"

if [[ -f .env ]]; then set -a; . ./.env; set +a; fi
exec "/Users/kanishk.raj/antier-content-intelligence/.venv/bin/python" "/Users/kanishk.raj/antier-content-intelligence/scripts/run_daily.py" "$@"
