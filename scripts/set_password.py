"""Type a password into .env safely.

    python3 scripts/set_password.py

The prompt hides what you type, the value goes straight into .env, and it is never
displayed, never written to shell history and never shown to anyone. Use this
instead of a text editor if that is easier, and instead of `export VAR=secret`,
which leaves the secret in your shell history and visible to `ps`.
"""

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

    write_value(key, value.strip(), args.env)
    print(f"\nSaved to {args.env} (readable only by you). The value was not shown.")
    print("Check it works:  python3 scripts/test_mail.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
