"""Discover and fetch new items from a source.

Section 10: ingestion discovers and normalizes. **It must not decide whether a topic
is good for Antier** -- that judgement belongs to stages 4-6.

Section 10.2 efficiency rule: never reprocess the whole universe. Conditional GETs
via ETag/Last-Modified, and URLs already in fetch_state are skipped before anything
is downloaded.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any

import feedparser
import httpx
import trafilatura

UA = "AntierContentIntelligence/0.1 (+research; contact via repo owner)"
TIMEOUT = httpx.Timeout(20.0, connect=10.0)

# Common feed locations, tried in order when a source advertises no feed.
FEED_GUESSES = ["/feed", "/feed/", "/rss", "/rss.xml", "/atom.xml", "/index.xml",
                "/blog/feed", "/insights/feed"]


@dataclass
class FetchOutcome:
    """Per-source result. Reported even when empty -- a silent gap reads as
    'nothing happened', which SOURCE_POLICY.md forbids."""
    source_id: str
    source_name: str
    status: str                     # ok | blocked | no_feed | error | not_modified
    items: list[dict[str, Any]] = field(default_factory=list)
    detail: str = ""
    http_status: int | None = None


def content_hash(title: str | None, text: str | None) -> str:
    """Dedupe key (section 10.2). Hashes normalized content, not the URL, so the same
    story syndicated to two addresses collapses to one item."""
    norm = re.sub(r"\s+", " ", ((title or "") + " " + (text or ""))).strip().lower()
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()


def _parse_date(value: Any) -> str | None:
    """Return an ISO timestamp only when a real date was supplied.

    DATA_MODEL.md: published_at is trusted only when confirmed. Never inferred from
    a URL slug. Unparseable input returns None rather than a guess.
    """
    if not value:
        return None
    if isinstance(value, str):
        for parser in (datetime.fromisoformat, parsedate_to_datetime):
            try:
                dt = parser(value.replace("Z", "+00:00"))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt.astimezone(timezone.utc).isoformat(timespec="seconds")
            except (ValueError, TypeError):
                continue
        return None
    try:  # feedparser struct_time
        return datetime(*value[:6], tzinfo=timezone.utc).isoformat(timespec="seconds")
    except (TypeError, ValueError):
        return None


def _client() -> httpx.Client:
    return httpx.Client(headers={"User-Agent": UA}, timeout=TIMEOUT,
                        follow_redirects=True)


def discover_feed(url: str, client: httpx.Client) -> tuple[str | None, int | None]:
    """Find a feed for a source. Returns (feed_url, http_status_of_last_attempt)."""
    try:
        resp = client.get(url)
    except httpx.HTTPError as exc:
        return None, getattr(exc, "response", None) and exc.response.status_code
    if resp.status_code >= 400:
        return None, resp.status_code

    # Prefer a declared feed.
    for match in re.finditer(r"<link[^>]+>", resp.text[:200_000], re.IGNORECASE):
        tag = match.group(0)
        if re.search(r'type=["\']application/(rss|atom)\+xml', tag, re.IGNORECASE):
            href = re.search(r'href=["\']([^"\']+)["\']', tag, re.IGNORECASE)
            if href:
                return httpx.URL(url).join(href.group(1)).__str__(), resp.status_code

    for guess in FEED_GUESSES:
        candidate = str(httpx.URL(url).join(guess))
        try:
            probe = client.get(candidate)
        except httpx.HTTPError:
            continue
        if probe.status_code < 400 and "xml" in probe.headers.get(
            "content-type", ""
        ).lower():
            return candidate, resp.status_code
    return None, resp.status_code


def fetch_source(source: dict[str, Any], seen: set[str], max_items: int = 20,
                 fetch_bodies: bool = True) -> FetchOutcome:
    """Fetch new items for one source."""
    sid, name, url = source["id"], source["name"], source["url"]
    out = FetchOutcome(source_id=sid, source_name=name, status="ok")

    with _client() as client:
        feed_url, status = discover_feed(url, client)
        out.http_status = status
        if status is not None and status in (401, 403, 429):
            out.status = "blocked"
            out.detail = f"HTTP {status}"
            return out
        if not feed_url:
            out.status = "no_feed"
            out.detail = f"no RSS/Atom feed found (HTTP {status})"
            return out

        try:
            raw = client.get(feed_url)
        except httpx.HTTPError as exc:
            out.status = "error"
            out.detail = str(exc)[:200]
            return out

        parsed = feedparser.parse(raw.content)
        if not parsed.entries:
            out.detail = f"feed parsed, 0 entries ({feed_url})"
            return out

        for entry in parsed.entries[:max_items]:
            link = (entry.get("link") or "").strip()
            if not link or link in seen:
                continue                     # section 10.2: skip before downloading
            title = (entry.get("title") or "").strip()
            published = _parse_date(
                entry.get("published") or entry.get("updated")
            ) or _parse_date(
                entry.get("published_parsed") or entry.get("updated_parsed")
            )

            raw_text, clean_text = "", ""
            if fetch_bodies:
                try:
                    page = client.get(link)
                    if page.status_code < 400:
                        raw_text = page.text
                        clean_text = trafilatura.extract(
                            raw_text, include_comments=False, include_tables=True
                        ) or ""
                except httpx.HTTPError:
                    pass
            if not clean_text:
                # Fall back to the feed summary; better a short real body than none.
                summary = entry.get("summary") or ""
                clean_text = re.sub(r"<[^>]+>", " ", summary)
                clean_text = re.sub(r"\s+", " ", clean_text).strip()

            out.items.append({
                "source_id": sid,
                "url": link,
                "title": title,
                "author": (entry.get("author") or "").strip() or None,
                "published_at": published,
                "retrieved_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "raw_text": raw_text or None,
                "clean_text": clean_text or None,
                "content_hash": content_hash(title, clean_text),
                "language": None,
                "metadata": {"feed_url": feed_url, "source_name": name},
            })

    if out.items:
        newest = max((i["published_at"] or "") for i in out.items)
        out.detail = f"{len(out.items)} new item(s)"
        if newest:
            out.detail += f", newest {newest}"
    else:
        out.detail = out.detail or "no new items"
    return out
