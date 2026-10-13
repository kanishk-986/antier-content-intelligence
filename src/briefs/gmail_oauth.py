"""Send the daily brief through the Gmail API with OAuth2.

Why this exists: Google Workspace reports "the setting that you are looking for is
not available for your account" on the app-passwords page when an administrator has
disabled app passwords for the organisation. That cannot be fixed from the account,
so SMTP with a password is simply unavailable. OAuth is the route that remains.

Three security choices worth stating:

  **Send-only scope.** `gmail.send` can send mail as the user and cannot read a
  single message. If this refresh token leaks it cannot be used to read the inbox,
  which a full `https://mail.google.com/` scope would allow.

  **PKCE.** An installed application cannot keep a client secret secret -- it ships
  on the user's machine -- so the authorization code is bound to a one-time verifier
  this process generated. An intercepted code is useless without it.

  **Nothing is logged.** Tokens never reach a log line or an exception message;
  `_redact` scrubs them from anything that is reported.

Stdlib plus httpx, which the project already depends on. The google-auth libraries
would add a large dependency tree for one POST and one refresh.
"""

from __future__ import annotations

import base64
import hashlib
import os
import re
import secrets
import urllib.parse
from dataclasses import dataclass
from email.message import EmailMessage

import httpx

AUTH_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
SEND_ENDPOINT = "https://gmail.googleapis.com/gmail/v1/users/me/messages/send"

# Least privilege: send only. This scope cannot read mail.
SCOPE = "https://www.googleapis.com/auth/gmail.send"

REQUIRED = ("GMAIL_CLIENT_ID", "GMAIL_CLIENT_SECRET", "GMAIL_REFRESH_TOKEN")

_SECRET_KEYS = ("refresh_token", "access_token", "client_secret", "code_verifier")


@dataclass
class Tokens:
    access_token: str
    refresh_token: str | None
    expires_in: int


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def new_verifier() -> str:
    """A PKCE code verifier: 43-128 unreserved characters, cryptographically random."""
    return _b64url(secrets.token_bytes(64))


def challenge_for(verifier: str) -> str:
    return _b64url(hashlib.sha256(verifier.encode()).digest())


def build_auth_url(client_id: str, redirect_uri: str, verifier: str,
                   login_hint: str | None = None) -> str:
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": SCOPE,
        # offline plus consent is what actually returns a refresh token. Without
        # prompt=consent Google omits it on a repeat authorization, and the setup
        # appears to succeed while leaving nothing to refresh with.
        "access_type": "offline",
        "prompt": "consent",
        "code_challenge": challenge_for(verifier),
        "code_challenge_method": "S256",
    }
    if login_hint:
        params["login_hint"] = login_hint
    return f"{AUTH_ENDPOINT}?{urllib.parse.urlencode(params)}"


def redact(text: str) -> str:
    """Keep a token out of an error string.

    Google's error responses echo request fields, and an httpx exception carries the
    response body. This runs on every path that reports a failure.
    """
    for key in _SECRET_KEYS:
        text = re.sub(rf"(?i)({key}\"?\s*[=:]\s*\"?)[^\s\"&,}}]+", r"\1***", text)
    # A bare Google token, if one appears without its field name.
    text = re.sub(r"\b1//[A-Za-z0-9_\-]{20,}", "***", text)
    text = re.sub(r"\bya29\.[A-Za-z0-9_\-.]{20,}", "***", text)
    return text


def _post_token(payload: dict[str, str], client: httpx.Client | None = None) -> Tokens:
    owned = client is None
    client = client or httpx.Client(timeout=30.0)
    try:
        resp = client.post(TOKEN_ENDPOINT, data=payload)
        body = resp.json() if resp.content else {}
        if resp.status_code >= 400:
            detail = body.get("error_description") or body.get("error") or resp.text
            raise RuntimeError(redact(f"token endpoint {resp.status_code}: {detail}"))
        return Tokens(body["access_token"], body.get("refresh_token"),
                      int(body.get("expires_in", 0)))
    finally:
        if owned:
            client.close()


def exchange_code(code: str, client_id: str, client_secret: str, redirect_uri: str,
                  verifier: str, client: httpx.Client | None = None) -> Tokens:
    return _post_token({
        "code": code, "client_id": client_id, "client_secret": client_secret,
        "redirect_uri": redirect_uri, "grant_type": "authorization_code",
        "code_verifier": verifier,
    }, client)


def refresh_access_token(client_id: str, client_secret: str, refresh_token: str,
                         client: httpx.Client | None = None) -> Tokens:
    tokens = _post_token({
        "client_id": client_id, "client_secret": client_secret,
        "refresh_token": refresh_token, "grant_type": "refresh_token",
    }, client)
    # A refresh response omits the refresh token; the stored one stays valid.
    return Tokens(tokens.access_token, refresh_token, tokens.expires_in)


def config_from_env(env: dict[str, str] | None = None) -> dict[str, str]:
    env = env if env is not None else dict(os.environ)
    missing = [k for k in REQUIRED if not (env.get(k) or "").strip()]
    if missing:
        raise RuntimeError(
            "missing Gmail OAuth settings: " + ", ".join(missing)
            + ". Run `python3 scripts/gmail_authorize.py` once; it writes them to "
              ".env for you. Never paste a token on a command line or into chat."
        )
    return {k: env[k].strip() for k in REQUIRED}


def send_message(message: EmailMessage, env: dict[str, str] | None = None,
                 client: httpx.Client | None = None) -> str:
    """Send an already-built message. Returns the Gmail message id."""
    settings = config_from_env(env)
    tokens = refresh_access_token(settings["GMAIL_CLIENT_ID"],
                                  settings["GMAIL_CLIENT_SECRET"],
                                  settings["GMAIL_REFRESH_TOKEN"], client)
    owned = client is None
    client = client or httpx.Client(timeout=60.0)
    try:
        resp = client.post(
            SEND_ENDPOINT,
            headers={"Authorization": f"Bearer {tokens.access_token}"},
            json={"raw": _b64url(message.as_bytes())},
        )
        if resp.status_code >= 400:
            body = resp.json() if resp.content else {}
            detail = (body.get("error") or {}).get("message") or resp.text
            raise RuntimeError(redact(f"gmail send {resp.status_code}: {detail}"))
        return (resp.json() or {}).get("id", "")
    finally:
        if owned:
            client.close()
