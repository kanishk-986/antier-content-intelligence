"""Type a password into .env safely.

    python3 scripts/set_password.py

The prompt hides what you type, the value goes straight into .env, and it is never
displayed, never written to shell history and never shown to anyone. Use this
instead of a text editor if that is easier, and instead of `export VAR=secret`,
which leaves the secret in your shell history and visible to `ps`.
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

import argparse
import getpass
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.briefs.envfile import DEFAULT_PATH, read_env_file

# Only secrets. Everything else is plain config and belongs in a text editor.
SETTABLE = {
    "SMTP_PASSWORD": "the SMTP key from your mail provider (Brevo, SMTP2GO, Gmail)",
    "SMTP_USER": "the login the provider shows you (not always an email address)",
    "MAIL_FROM": "the address the brief is sent from",
    "SMTP_HOST": "e.g. smtp-relay.brevo.com, or smtp.gmail.com",
    "GMAIL_CLIENT_SECRET": "from your Google Cloud OAuth client",
    "GMAIL_CLIENT_ID": "from your Google Cloud OAuth client",
}


def normalise(key: str, raw: str) -> tuple[str, str | None]:
    """Clean an obviously mistyped value, and refuse one that cannot be right.

    A terminal paste goes wrong in predictable ways. Google displays an app password
    as four groups of four -- "abcd efgh ijkl mnop" -- so the spaces get pasted too,
    and a repeated paste silently concatenates. Both produce a value that looks
    plausible in a file and fails at the server with an unhelpful 535.
    """
    value = " ".join(raw.split())            # collapse runs of whitespace
    if key in ("SMTP_PASSWORD", "GMAIL_CLIENT_SECRET"):
        value = value.replace(" ", "")       # Google shows groups; they are display only

    # A repeated paste: the same chunk over and over.
    if len(value) > 40:
        for size in range(8, 25):
            if len(value) % size == 0 and len(set(
                    value[i:i + size] for i in range(0, len(value), size))) == 1:
                return value[:size], (
                    f"that looks like the same {size}-character value pasted "
                    f"{len(value) // size} times; keeping one copy")

    if key == "SMTP_PASSWORD" and 20 < len(value) != 16:
        return value, (
            f"a Google app password is exactly 16 letters; this is {len(value)}. "
            "If it was pasted more than once, delete it in Google and make a new one.")
    return value, None


def write_value(key: str, value: str, path: str) -> None:
    lines = []
    if os.path.exists(path):
        with open(path) as fh:
            lines = fh.read().splitlines()
    replaced = False
    out = []
    for line in lines:
        if "=" in line and line.split("=", 1)[0].strip() == key:
            out.append(f"{key}={value}")
            replaced = True
        else:
            out.append(line)
    if not replaced:
        out.append(f"{key}={value}")
    with open(path, "w") as fh:
        fh.write("\n".join(out).rstrip("\n") + "\n")
    os.chmod(path, 0o600)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("key", nargs="?", help="which setting to set")
    ap.add_argument("--env", default=DEFAULT_PATH)
    args = ap.parse_args()

    if not args.key:
        print("Which setting? Run again with one of these:\n")
        current = read_env_file(args.env)
        for key, what in SETTABLE.items():
            state = "set" if (current.get(key) or "").strip() else "EMPTY"
            print(f"  python3 scripts/set_password.py {key:22} [{state}]  {what}")
        print("\nNothing is ever displayed back to you, and nothing is sent anywhere"
              "\nexcept to your mail provider when the brief is sent.")
        return 0

    key = args.key.strip().upper()
    if key not in SETTABLE:
        print(f"{key} is not one of: {', '.join(SETTABLE)}", file=sys.stderr)
        return 1

    print(f"{key} — {SETTABLE[key]}")
    # getpass reads from the terminal with echo off, so the value is not on screen,
    # not in scrollback and not in shell history.
    value = getpass.getpass("Paste it here (nothing will appear as you type): ")
    if not value.strip():
        print("Nothing entered; .env unchanged.", file=sys.stderr)
        return 1

    cleaned, warning = normalise(key, value)
    if warning:
        print(f"\n  note: {warning}")
    if not cleaned:
        print("Nothing usable entered; .env unchanged.", file=sys.stderr)
        return 1

    write_value(key, cleaned, args.env)
    print(f"\nSaved to {args.env} (readable only by you). The value was not shown.")
    if key == "SMTP_PASSWORD":
        print(f"It is {len(cleaned)} characters"
              + (" — the right length for a Google app password."
                 if len(cleaned) == 16 else
                 " — a Google app password is 16, so check it if sending fails."))
    print("Check it works:  python3 scripts/test_mail.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
