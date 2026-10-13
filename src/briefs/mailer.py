"""Send the daily brief over SMTP (Google Workspace).

Section 33 and 7.2: credentials never appear in code, in a committed file, or in a
shell command. This reads them from the environment only, and `.env` is gitignored
and chmod 600. Nothing here logs or echoes the password, including on failure --
an SMTP error message can otherwise carry the credential into a log file.

The brief is sent as multipart/alternative: Markdown as the plain-text part and a
minimal HTML rendering alongside it, so a mail client that shows HTML gets readable
headings and one that does not still gets the whole brief.
"""

from __future__ import annotations

import html
import os
import re
import smtplib
from dataclasses import dataclass
from email.message import EmailMessage

from src.briefs import gmail_oauth

REQUIRED = ("SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_PASSWORD")


@dataclass
class MailResult:
    sent: bool
    detail: str
    recipients: list[str]


def config_from_env(env: dict[str, str] | None = None) -> dict[str, str]:
    env = env if env is not None else dict(os.environ)
    missing = [k for k in REQUIRED if not (env.get(k) or "").strip()]
    if missing:
        raise RuntimeError(
            "missing SMTP settings: " + ", ".join(missing)
            + ". Put them in .env (gitignored, chmod 600) and load with "
              "`export $(grep -v '^#' .env | xargs)` so the value stays out of "
              "shell history and ps. Never pass a password on the command line."
        )
    return {k: env[k].strip() for k in REQUIRED}


def _redact(text: str, secret: str) -> str:
    """Keep a credential out of an error string.

    smtplib puts the server's response in the exception, and a failed AUTH can echo
    part of what was sent. Cheap insurance on a path that writes to logs.
    """
    if secret and secret in text:
        text = text.replace(secret, "***")
    return re.sub(r"(?i)(password|auth\w*)[=:\s]+\S+", r"\1 ***", text)


def markdown_to_html(markdown: str) -> str:
    """A deliberately small renderer.

    A Markdown library would be a dependency for one email; this handles the five
    constructs the brief actually uses. Everything is escaped first, so a title from
    a fetched page cannot inject markup into the mail.
    """
    lines = []
    in_list = False
    for raw in markdown.splitlines():
        line = html.escape(raw.rstrip())
        link = re.sub(r"\[([^\]]+)\]\(([^)]+)\)",
                      r'<a href="\2">\1</a>', line)
        link = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", link)
        link = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<em>\1</em>", link)
        link = re.sub(r"`([^`]+)`", r"<code>\1</code>", link)

        if line.startswith("### "):
            tag = f"<h3>{link[4:]}</h3>"
        elif line.startswith("## "):
            tag = f"<h2>{link[3:]}</h2>"
        elif line.startswith("# "):
            tag = f"<h1>{link[2:]}</h1>"
        elif line.startswith("- "):
            tag = f"<li>{link[2:]}</li>"
        elif line.startswith("---"):
            tag = "<hr>"
        elif not line.strip():
            tag = ""
        else:
            tag = f"<p>{link}</p>"

        if not line.startswith("- ") and in_list:
            lines.append("</ul>")
            in_list = False
        if line.startswith("- ") and not in_list:
            lines.append("<ul>")
            in_list = True
        if tag:
            lines.append(tag)
    if in_list:
        lines.append("</ul>")
    body = "\n".join(lines)
    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<style>body{font:15px/1.55 -apple-system,Segoe UI,Helvetica,sans-serif;"
        "max-width:46em;margin:1.5em auto;padding:0 1em;color:#1a1a1a}"
        "h1{font-size:1.5em}h2{font-size:1.2em;margin-top:1.8em;"
        "border-bottom:1px solid #e3e3e3;padding-bottom:.25em}"
        "h3{font-size:1.05em;margin-bottom:.2em}"
        "code{background:#f3f3f3;padding:.1em .3em;border-radius:3px;font-size:.9em}"
        "a{color:#0b5cad}em{color:#555}li{margin:.2em 0}hr{border:0;"
        "border-top:1px solid #e3e3e3;margin:2em 0}</style></head><body>"
        f"{body}</body></html>"
    )


def build_message(subject: str, markdown: str, sender: str,
                  to: list[str]) -> EmailMessage:
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = sender
    message["To"] = ", ".join(to)
    message.set_content(markdown)
    message.add_alternative(markdown_to_html(markdown), subtype="html")
    return message


def _backend(env: dict[str, str]) -> str:
    """`gmail` or `smtp`.

    Defaults to the Gmail API when a refresh token is present, because a Workspace
    account that needed OAuth got there by having app passwords disabled -- falling
    back to SMTP would just fail again, more confusingly.
    """
    chosen = (env.get("MAIL_BACKEND") or "").strip().lower()
    if chosen in ("gmail", "smtp"):
        return chosen
    return "gmail" if (env.get("GMAIL_REFRESH_TOKEN") or "").strip() else "smtp"


def send(subject: str, markdown: str, to: list[str],
         env: dict[str, str] | None = None,
         transport=None) -> MailResult:
    """`transport` is injected so the send path is testable without a server."""
    recipients = [address for address in to if address and "@" in address]
    if not recipients:
        return MailResult(False, "no valid recipient address configured", [])

    env = env if env is not None else dict(os.environ)

    if transport is None and _backend(env) == "gmail":
        sender = (env.get("SMTP_USER") or env.get("GMAIL_SENDER") or "me").strip()
        message = build_message(subject, markdown, sender, recipients)
        try:
            message_id = gmail_oauth.send_message(message, env)
        except Exception as exc:       # reported, never raised, never with a token
            return MailResult(False, gmail_oauth.redact(
                f"{type(exc).__name__}: {exc}"), recipients)
        return MailResult(True, f"sent via Gmail API ({message_id}) to "
                                f"{', '.join(recipients)}", recipients)

    settings = config_from_env(env)
    message = build_message(subject, markdown, settings["SMTP_USER"], recipients)

    try:
        if transport is not None:
            transport(message, settings)
        else:
            with smtplib.SMTP(settings["SMTP_HOST"],
                              int(settings["SMTP_PORT"]), timeout=30) as smtp:
                smtp.starttls()
                smtp.login(settings["SMTP_USER"], settings["SMTP_PASSWORD"])
                smtp.send_message(message)
    except Exception as exc:          # a failed send is reported, never raised
        detail = _redact(f"{type(exc).__name__}: {exc}", settings["SMTP_PASSWORD"])
        return MailResult(False, detail, recipients)
    return MailResult(True, f"sent to {', '.join(recipients)}", recipients)
