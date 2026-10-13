#!/usr/bin/env bash
set -euo pipefail
cd "/Users/kanishk.raj/antier-content-intelligence"
if [[ -f .env ]]; then set -a; . ./.env; set +a; fi
exec "/Users/kanishk.raj/antier-content-intelligence/.venv/bin/python" "/Users/kanishk.raj/antier-content-intelligence/scripts/run_daily.py" "$@"
