"""Gmail OAuth sending. Offline: URL construction, PKCE, redaction and dispatch."""

import base64
import os
import sys
import urllib.parse
from email.message import EmailMessage

import httpx
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.briefs import gmail_oauth as g
from src.briefs import mailer

ENV = {"GMAIL_CLIENT_ID": "cid", "GMAIL_CLIENT_SECRET": "csecret",
       "GMAIL_REFRESH_TOKEN": "1//0gREFRESHxxxxxxxxxxxxxxxxxxxxxxxxx"}


def _params(url):
    return urllib.parse.parse_qs(urllib.parse.urlparse(url).query)


# --- scope and PKCE -----------------------------------------------------------

def test_the_scope_cannot_read_mail():
    """Least privilege: a leaked token must not open the inbox."""
    assert g.SCOPE == "https://www.googleapis.com/auth/gmail.send"
    assert "mail.google.com" not in g.SCOPE
    assert "readonly" not in g.SCOPE


def test_the_auth_url_asks_for_a_refresh_token():
    """Without access_type=offline AND prompt=consent, Google omits the refresh
    token on a repeat authorization — setup appears to work and leaves nothing to
    refresh with."""
    p = _params(g.build_auth_url("cid", "http://localhost:1234", g.new_verifier()))
    assert p["access_type"] == ["offline"]
    assert p["prompt"] == ["consent"]


def test_the_auth_url_carries_a_pkce_challenge():
    verifier = g.new_verifier()
    p = _params(g.build_auth_url("cid", "http://localhost:1234", verifier))
    assert p["code_challenge_method"] == ["S256"]
    assert p["code_challenge"] == [g.challenge_for(verifier)]
    assert verifier not in p["code_challenge"][0], "the verifier is never sent"


def test_the_verifier_is_random_and_long_enough():
    """RFC 7636: 43-128 unreserved characters."""
    a, b = g.new_verifier(), g.new_verifier()
    assert a != b
    assert 43 <= len(a) <= 128
    assert all(c.isalnum() or c in "-._~" for c in a)


def test_the_challenge_is_the_sha256_of_the_verifier():
    import hashlib
    verifier = "abc123"
    expected = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    assert g.challenge_for(verifier) == expected


# --- redaction ----------------------------------------------------------------

@pytest.mark.parametrize("text,leak", [
    ('{"refresh_token": "1//0gSECRETVALUEHERE123456"}', "1//0gSECRETVALUEHERE123456"),
    ('access_token=ya29.a0SECRETACCESSTOKENVALUE1', "ya29.a0SECRETACCESSTOKENVALUE1"),
    ('client_secret: "GOCSPX-abcdefghijklmnop"', "GOCSPX-abcdefghijklmnop"),
    ('bare 1//0gLOOSETOKENWITHOUTAFIELD99', "1//0gLOOSETOKENWITHOUTAFIELD99"),
])
def test_tokens_never_survive_into_an_error_string(text, leak):
    """Google's error responses echo request fields, and an httpx exception carries
    the response body."""
    out = g.redact(text)
    assert leak not in out
    assert "***" in out


# --- config -------------------------------------------------------------------

def test_missing_settings_name_themselves_and_the_fix():
    with pytest.raises(RuntimeError) as exc:
        g.config_from_env({})
    for key in g.REQUIRED:
        assert key in str(exc.value)
    assert "gmail_authorize.py" in str(exc.value)
    assert "Never paste a token on a command line" in str(exc.value)


# --- refresh and send ---------------------------------------------------------

def _client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_a_refresh_keeps_the_stored_refresh_token():
    """A refresh response omits it; losing it would break every later run."""
    def handler(request):
        return httpx.Response(200, json={"access_token": "ya29.new", "expires_in": 3599})
    tokens = g.refresh_access_token("cid", "csecret", "stored-refresh",
                                    client=_client(handler))
    assert tokens.access_token == "ya29.new"
    assert tokens.refresh_token == "stored-refresh"


def test_a_refresh_failure_is_reported_without_the_token():
    def handler(request):
        return httpx.Response(400, json={"error": "invalid_grant",
                                         "error_description": "Token has been expired"})
    with pytest.raises(RuntimeError) as exc:
        g.refresh_access_token("cid", "csecret", "1//0gSECRETREFRESHTOKEN123",
                               client=_client(handler))
    assert "invalid_grant" in str(exc.value) or "expired" in str(exc.value)
    assert "1//0gSECRETREFRESHTOKEN123" not in str(exc.value)


def test_send_posts_a_base64url_rfc822_message():
    seen = {}

    def handler(request):
        if str(request.url).startswith(g.TOKEN_ENDPOINT):
            return httpx.Response(200, json={"access_token": "ya29.tok",
                                             "expires_in": 3599})
        seen["auth"] = request.headers.get("Authorization")
        import json as _json
        seen["raw"] = _json.loads(request.content)["raw"]
        return httpx.Response(200, json={"id": "18f0"})

    message = EmailMessage()
    message["Subject"] = "Antier daily brief"
    message["To"] = "x@y.test"
    message.set_content("body")

    assert g.send_message(message, ENV, client=_client(handler)) == "18f0"
    assert seen["auth"] == "Bearer ya29.tok"
    decoded = base64.urlsafe_b64decode(seen["raw"] + "=" * (-len(seen["raw"]) % 4))
    assert b"Antier daily brief" in decoded


def test_a_send_failure_carries_googles_reason_but_no_token():
    def handler(request):
        if str(request.url).startswith(g.TOKEN_ENDPOINT):
            return httpx.Response(200, json={"access_token": "ya29.tok",
                                             "expires_in": 3599})
        return httpx.Response(403, json={"error": {"message": "Request had "
                                                             "insufficient scopes"}})
    message = EmailMessage()
    message.set_content("b")
    with pytest.raises(RuntimeError) as exc:
        g.send_message(message, ENV, client=_client(handler))
    assert "insufficient scopes" in str(exc.value)
    assert ENV["GMAIL_REFRESH_TOKEN"] not in str(exc.value)


# --- backend dispatch ---------------------------------------------------------

@pytest.mark.parametrize("env,expected", [
    ({"GMAIL_REFRESH_TOKEN": "x"}, "gmail"),
    ({}, "smtp"),
    ({"SMTP_PASSWORD": "p"}, "smtp"),
    ({"MAIL_BACKEND": "smtp", "GMAIL_REFRESH_TOKEN": "x"}, "smtp"),
    ({"MAIL_BACKEND": "gmail"}, "gmail"),
    ({"MAIL_BACKEND": "nonsense", "GMAIL_REFRESH_TOKEN": "x"}, "gmail"),
])
def test_the_backend_is_chosen_sensibly(env, expected):
    """A Workspace account that needed OAuth got there by having app passwords
    disabled, so falling back to SMTP would fail again, more confusingly."""
    assert mailer._backend(env) == expected


def test_a_gmail_send_failure_is_returned_not_raised(monkeypatch):
    monkeypatch.setattr(g, "send_message",
                        lambda *a, **k: (_ for _ in ()).throw(
                            RuntimeError("gmail send 403: blocked")))
    result = mailer.send("s", "# b", ["x@y.test"], env=ENV)
    assert not result.sent and "403" in result.detail


# --- the .env writer ----------------------------------------------------------

import importlib.util

_spec = importlib.util.spec_from_file_location(
    "gmail_authorize",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                 "scripts", "gmail_authorize.py"))
authorize = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(authorize)


def test_writing_a_token_preserves_comments_and_other_settings(tmp_path):
    """.env is hand-edited. Rewriting it must not discard the comments that explain
    what each value is."""
    path = tmp_path / ".env"
    path.write_text("# a comment\nSMTP_USER=k@a.test\n\n# another\nSMTP_PORT=587\n")
    authorize.write_env({"GMAIL_REFRESH_TOKEN": "1//0gTOKEN"}, str(path))
    text = path.read_text()
    assert "# a comment" in text and "# another" in text
    assert "SMTP_USER=k@a.test" in text and "SMTP_PORT=587" in text
    assert "GMAIL_REFRESH_TOKEN=1//0gTOKEN" in text


def test_an_existing_key_is_replaced_not_duplicated(tmp_path):
    """Two values for one key means whichever the loader reads last wins, which is
    how a rotated token silently keeps using the old one."""
    path = tmp_path / ".env"
    path.write_text("GMAIL_REFRESH_TOKEN=old\n")
    authorize.write_env({"GMAIL_REFRESH_TOKEN": "new"}, str(path))
    assert path.read_text().count("GMAIL_REFRESH_TOKEN") == 1
    assert "new" in path.read_text() and "old" not in path.read_text()


def test_the_written_file_is_owner_only(tmp_path):
    path = tmp_path / ".env"
    path.write_text("A=1\n")
    path.chmod(0o644)
    authorize.write_env({"GMAIL_REFRESH_TOKEN": "t"}, str(path))
    assert oct(path.stat().st_mode)[-3:] == "600", "a token must not be world-readable"


def test_env_values_with_quotes_and_comments_load_correctly(tmp_path):
    path = tmp_path / ".env"
    path.write_text('# lead\nSMTP_USER="k@a.test"\nEMPTY=\nSMTP_PORT=587\n')
    got = authorize.load_env(str(path))
    assert got["SMTP_USER"] == "k@a.test"
    assert got["SMTP_PORT"] == "587"
    assert got["EMPTY"] == ""
    assert "# lead" not in got
