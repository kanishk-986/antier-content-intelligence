"""One-time Gmail authorization. Run once; the daily brief uses it from then on.

    python3 scripts/gmail_authorize.py

What happens: a browser opens, you approve send-only access, and this writes
GMAIL_REFRESH_TOKEN into .env. The token is never printed, never passed on a
command line, and never leaves your machine except to Google.

Before running it you need an OAuth client, which is free and takes a few minutes:

  1. https://console.cloud.google.com/projectcreate — any name.
  2. APIs & Services → Library → search "Gmail API" → Enable.
  3. APIs & Services → OAuth consent screen → User type **Internal** if your
     Workspace offers it (no verification needed), otherwise **External** and add
     yourself under Test users. Scope: nothing to add here; this asks for
     gmail.send at authorization time.
  4. APIs & Services → Credentials → Create credentials → OAuth client ID →
     Application type **Desktop app**.
  5. Copy the client ID and client secret into .env as GMAIL_CLIENT_ID and
     GMAIL_CLIENT_SECRET. Do not paste them into a chat or a terminal command.

If your administrator restricts third-party apps, step 3's Internal option still
needs the app allow-listed in the Admin console. That is the same wall app
passwords hit, and it is the one thing this route cannot work around.
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
import http.server
import os
import secrets
import socket
import sys
import threading
import urllib.parse
import webbrowser

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.briefs.gmail_oauth import build_auth_url, exchange_code, new_verifier, redact

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV_PATH = os.path.join(REPO, ".env")

PAGE = b"""<!doctype html><meta charset=utf-8>
<style>body{font:16px -apple-system,sans-serif;margin:4em auto;max-width:28em;
text-align:center;color:#1a1a1a}</style>
<h2>%s</h2><p>%s</p><p>You can close this tab.</p>"""


def load_env(path: str = ENV_PATH) -> dict[str, str]:
    out: dict[str, str] = {}
    if not os.path.exists(path):
        return out
    with open(path) as fh:
        for raw in fh:
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            out[key.strip()] = value.strip().strip('"').strip("'")
    return out


def write_env(updates: dict[str, str], path: str = ENV_PATH) -> None:
    """Rewrite .env in place, preserving comments and ordering.

    Written here rather than printed so the token is never on screen, never in
    scrollback and never in shell history.
    """
    lines = []
    if os.path.exists(path):
        with open(path) as fh:
            lines = fh.read().splitlines()

    remaining = dict(updates)
    out = []
    for line in lines:
        key = line.split("=", 1)[0].strip() if "=" in line else ""
        if key in remaining:
            out.append(f"{key}={remaining.pop(key)}")
        else:
            out.append(line)
    for key, value in remaining.items():
        out.append(f"{key}={value}")

    with open(path, "w") as fh:
        fh.write("\n".join(out).rstrip("\n") + "\n")
    os.chmod(path, 0o600)


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--env", default=ENV_PATH)
    args = ap.parse_args()

    env = {**load_env(args.env), **os.environ}
    client_id = (env.get("GMAIL_CLIENT_ID") or "").strip()
    client_secret = (env.get("GMAIL_CLIENT_SECRET") or "").strip()
    if not client_id or not client_secret:
        print("GMAIL_CLIENT_ID and GMAIL_CLIENT_SECRET must be in .env first.\n"
              "See the setup steps at the top of this file "
              "(scripts/gmail_authorize.py).", file=sys.stderr)
        return 1

    port = free_port()
    redirect_uri = f"http://localhost:{port}"
    verifier = new_verifier()
    state = secrets.token_urlsafe(24)
    received: dict[str, str] = {}
    done = threading.Event()

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):                      # the name http.server requires
            query = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            got_state = (query.get("state") or [""])[0]
            if got_state != state:
                # A mismatched state means this response is not the one we asked
                # for, so the code in it is not ours to use.
                body = PAGE % (b"Rejected", b"State mismatch; nothing was saved.")
                received["error"] = "state mismatch"
            elif "code" in query:
                received["code"] = query["code"][0]
                body = PAGE % (b"Authorized", b"The daily brief can now send mail.")
            else:
                received["error"] = (query.get("error") or ["no code returned"])[0]
                body = PAGE % (b"Not authorized", received["error"].encode())
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(body)
            done.set()

        def log_message(self, *a):             # silence the default access log
            return

    server = http.server.HTTPServer(("127.0.0.1", port), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()

    url = build_auth_url(client_id, redirect_uri, verifier,
                         login_hint=(env.get("SMTP_USER") or "").strip() or None)
    print("Opening your browser to approve send-only access.")
    print("If it does not open, paste this into a browser:\n")
    print(f"  {url}\n")
    webbrowser.open(url)

    if not done.wait(timeout=300):
        server.shutdown()
        print("Timed out after 5 minutes with no response.", file=sys.stderr)
        return 1
    server.shutdown()

    if "code" not in received:
        print(f"Authorization failed: {received.get('error')}", file=sys.stderr)
        return 1

    try:
        tokens = exchange_code(received["code"], client_id, client_secret,
                               redirect_uri, verifier)
    except RuntimeError as exc:
        print(redact(str(exc)), file=sys.stderr)
        return 1

    if not tokens.refresh_token:
        print("Google returned no refresh token. Revoke this app at "
              "https://myaccount.google.com/permissions and run this again — "
              "Google only issues one on a fresh consent.", file=sys.stderr)
        return 1

    write_env({"GMAIL_REFRESH_TOKEN": tokens.refresh_token,
               "MAIL_BACKEND": "gmail"}, args.env)
    print(f"\nSaved to {args.env} (chmod 600). The token was not displayed.")
    print("MAIL_BACKEND=gmail — the daily brief will use the Gmail API.")
    print("\nTest it:  python3 scripts/run_daily.py --brief-only")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
