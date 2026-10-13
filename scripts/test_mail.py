"""Prove delivery works, without running the pipeline.

    python3 scripts/test_mail.py

Sends one short message to the digest address in config/brand/recipients.yaml.
Ten seconds, and it tells you which backend it used and exactly what the server
said if it refused.
"""

# macOS ships Python 3.9, which cannot parse `str | None` at runtime and has none
# of this project's dependencies. Re-exec into the project venv so `python3
# scripts/x.py` works regardless of which interpreter the shell found first.
import os as _os
import sys as _sys

_VENV = _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))),
                      ".venv", "bin", "python")
if _os.path.exists(_VENV) and _os.path.realpath(_sys.executable) != _os.path.realpath(_VENV):
    _os.execv(_VENV, [_VENV, _os.path.abspath(__file__), *_sys.argv[1:]])

import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.briefs import mailer
from src.briefs.envfile import environment
from src.briefs.persona import load_recipients


def main() -> int:
    recipients = load_recipients()
    to = (recipients.get("digest") or {}).get("email") or ""
    if not to:
        print("No digest address in config/brand/recipients.yaml", file=sys.stderr)
        return 1

    env = environment()
    backend = mailer._backend(env)
    sender = mailer.sender_address(env)
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")

    print(f"  backend: {backend}")
    print(f"  from:    {sender or '(not set)'}")
    print(f"  to:      {to}")
    if not sender:
        print("\n  MAIL_FROM is not set and SMTP_USER is not an address. A relay's\n"
              "  login is not your email address — set MAIL_FROM in .env to the\n"
              "  address the relay has verified for you.", file=sys.stderr)
        return 1

    body = (f"# Antier daily brief — delivery test\n\n"
            f"If you are reading this, the {backend} backend works and the 10:00 "
            f"schedule can mail the real brief.\n\n"
            f"Sent {now}.\n")
    result = mailer.send("Antier brief — delivery test", body, [to], env=env)

    print(f"\n  {'OK' if result.sent else 'FAILED'}: {result.detail}")
    if not result.sent:
        print("\n  Nothing in that message contains your password — it is redacted\n"
              "  before being printed, so it is safe to share when asking for help.",
              file=sys.stderr)
    return 0 if result.sent else 1


if __name__ == "__main__":
    raise SystemExit(main())
