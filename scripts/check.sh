#!/bin/sh
# Runs exactly what .github/workflows/ci.yml runs, locally.
#
# CI cannot run yet: pushing .github/workflows/ requires a token with `workflow`
# scope (see docs/RUNBOOK.md). Until it does, this script is the quality gate, and
# the pre-push hook enforces it. Once Actions is live this stays useful as the
# fast local check.
set -e
cd "$(dirname "$0")/.."
PY=./.venv/bin/python

echo "[1/3] lint"
./.venv/bin/ruff check .

echo "[2/3] tests"
$PY -m pytest tests/ -q

echo "[3/3] secret scan"
if grep -rInE 'sk-ant-[A-Za-z0-9_-]{15,}|ghp_[A-Za-z0-9]{20,}' \
     --exclude-dir=.git --exclude-dir=.venv --exclude=.env.example . ; then
  echo "FAIL: secret-like string present" >&2
  exit 1
fi
echo "     clean"

echo "all checks passed"
