"""Read `.env` so a script does not depend on the caller having exported it.

`export $(grep -v '^#' .env | xargs)` keeps a secret out of shell history, which is
why the runbook uses it -- but forgetting it makes a correctly configured system
report its settings as missing, and the launchd agent inherits no environment at
all. Scripts load the file themselves; an exported variable still wins, so a one-off
override on the command line behaves as expected.

This is read-only and never writes or logs a value.
"""

from __future__ import annotations

import os

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DEFAULT_PATH = os.path.join(REPO, ".env")


def read_env_file(path: str = DEFAULT_PATH) -> dict[str, str]:
    out: dict[str, str] = {}
    if not os.path.exists(path):
        return out
    with open(path) as fh:
        for raw in fh:
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            # `export VAR=value` is valid in a file meant to be sourced, and the
            # launchd wrapper does source it with `set -a`. Reading the key as
            # "export VAR" would make the same file work under the scheduler and
            # silently fail for every script that reads it directly.
            key = key.strip()
            if key.startswith("export ") or key.startswith("export\t"):
                key = key[len("export"):].strip()
            value = value.strip()
            # Quotes are a shell convention for values with spaces, not part of the
            # value. `export` strips them, so reading the file must too.
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                value = value[1:-1]
            out[key] = value
    return out


def environment(path: str = DEFAULT_PATH) -> dict[str, str]:
    """`.env` underneath, the real environment on top."""
    return {**read_env_file(path), **os.environ}
