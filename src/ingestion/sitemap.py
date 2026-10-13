"""Sitemap ingestion: the third path, after feed and listing page.

A sitemap is the one route a publisher builds *for machines*, declares in
robots.txt, and keeps current. It gives a URL and a `lastmod` date, which is
exactly what section 14 needs, and it does not care whether the page it points at
is rendered in the browser.

That matters for two groups the other paths cannot reach:

  js_rendered   DTCC and Ondo serve a client-rendered shell to an HTTP client, so
                the listing extractor sees no links. Their sitemaps carry 881 and
                201 URLs with dates. No headless browser required.
  no_feed       The US Treasury, Circle and State Street publish no feed and no
                readable index, and 19829, 5476 and 317 sitemap URLs respectively.

`robots.txt` Disallow rules are honoured. A sitemap is an invitation, not a licence
to ignore the rest of the file.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx

from src.ingestion.listing import (
    MIN_ARTICLE_CHARS,
    _fetch_article,
    _has_editorial_section,
    load_rules,
)
from src.ingestion.urls import same_site

UA = "Mozilla/5.0 (compatible; AntierContentIntelligence/1.0; +research)"

# A sitemap index points at sitemaps; one level of indirection is enough for every
# publisher measured, and unbounded recursion on a hostile file is not worth it.
MAX_INDEX_CHILDREN = 5
MAX_URLS_SCANNED = 5000
DEFAULT_MAX_ITEMS = 12
DEFAULT_WINDOW_DAYS = 120

_LOC = re.compile(r"<loc>\s*([^<\s]+)\s*</loc>", re.IGNORECASE)
_ENTRY = re.compile(r"<(url|sitemap)\b.*?</\1>", re.IGNORECASE | re.DOTALL)
_LASTMOD = re.compile(r"<lastmod>\s*([^<\s]+)\s*</lastmod>", re.IGNORECASE)
_IS_INDEX = re.compile(r"<sitemapindex", re.IGNORECASE)

# A sitemap lists the whole site, so it needs the filtering a newsroom index gives
# for free. Measured on real sitemaps: DTCC offers
# /products-and-services/consulting/regulatory-reporting and
# /events/dtcc-transformation-office-hours, Celent offers /en/expert/analyst.
_LOCALE_SEGMENT = re.compile(r"^([a-z]{2})([_-][a-z]{2})?$")
_ENGLISH = {"en", "en-us", "en-gb", "en_us", "en_gb", "us-en", "eng"}


def _is_translation(url: str) -> bool:
    """A non-English localisation of an article we would otherwise take twice.

    Circle's sitemap carries /pt-br/us-banks-interest and /es/us-banks-interest
    alongside the English page. content_hash cannot collapse them, because a
    translation is genuinely different text.
    """
    for seg in urlparse(url).path.strip("/").split("/"):
        low = seg.lower()
        if _LOCALE_SEGMENT.match(low) and low not in _ENGLISH:
            return True
    return False


@dataclass
class SitemapOutcome:
    source_id: str
    source_name: str
    status: str                      # ok | no_sitemap | blocked | error
    detail: str = ""
    sitemap_url: str | None = None
    urls: list[tuple[str, datetime | None]] = field(default_factory=list)
    items: list[dict[str, Any]] = field(default_factory=list)


def parse_robots(text: str) -> tuple[list[str], list[str]]:
    """Sitemap declarations and the Disallow rules that apply to every agent.

    Only the `User-agent: *` group is read. A rule aimed at a named crawler is not
    aimed at us, and claiming a narrower group would be reading the file to suit
    ourselves.
    """
    sitemaps: list[str] = []
    disallow: list[str] = []
    applies = False
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line or ":" not in line:
            continue
        field_name, _, value = line.partition(":")
        key, value = field_name.strip().lower(), value.strip()
        if key == "sitemap" and value:
            sitemaps.append(value)
        elif key == "user-agent":
            applies = value == "*"
        elif key == "disallow" and applies and value:
            disallow.append(value)
    return sitemaps, disallow


def is_allowed(url: str, disallow: list[str]) -> bool:
    path = urlparse(url).path or "/"
    return not any(path.startswith(rule) for rule in disallow if rule != "/")


def _parse_lastmod(value: str | None) -> datetime | None:
    if not value:
        return None
    text = value.strip().replace("Z", "+00:00")
    for candidate in (text, text[:10]):
        try:
            when = datetime.fromisoformat(candidate)
        except ValueError:
            continue
        return when if when.tzinfo else when.replace(tzinfo=timezone.utc)
    return None


def parse_sitemap(xml: str) -> tuple[bool, list[tuple[str, datetime | None]]]:
    """(is_index, [(loc, lastmod)]). Entries are read as blocks so a `lastmod`
    belongs to the URL it sits with rather than to whichever came first."""
    out: list[tuple[str, datetime | None]] = []
    for block in _ENTRY.finditer(xml):
        chunk = block.group(0)
        loc = _LOC.search(chunk)
        if not loc:
            continue
        mod = _LASTMOD.search(chunk)
        out.append((loc.group(1).strip(),
                    _parse_lastmod(mod.group(1) if mod else None)))
        if len(out) >= MAX_URLS_SCANNED:
            break
    if not out:                     # a sitemap with no per-entry wrappers
        out = [(loc.strip(), None) for loc in _LOC.findall(xml)[:MAX_URLS_SCANNED]]
    return bool(_IS_INDEX.search(xml)), out


def discover(source: dict[str, Any], client: httpx.Client) -> SitemapOutcome:
    """Find a source's sitemap via robots.txt, falling back to /sitemap.xml."""
    out = SitemapOutcome(source["id"], source["name"], "no_sitemap")
    root = f"{urlparse(source['url']).scheme}://{urlparse(source['url']).netloc}"
    declared: list[str] = []
    disallow: list[str] = []
    try:
        robots = client.get(urljoin(root, "/robots.txt"))
        if robots.status_code < 400:
            declared, disallow = parse_robots(robots.text)
    except httpx.HTTPError:
        pass

    for candidate in [*declared, urljoin(root, "/sitemap.xml")]:
        if not same_site(source["url"], candidate):
            continue                 # a sitemap on another domain is another site
        try:
            resp = client.get(candidate)
        except httpx.HTTPError as exc:
            out.status, out.detail = "error", f"{type(exc).__name__} on {candidate}"
            continue
        if resp.status_code in (401, 403, 429):
            out.status = "blocked"
            out.detail = f"HTTP {resp.status_code} on {candidate}"
            continue
        if resp.status_code >= 400 or "<loc" not in resp.text.lower():
            continue

        is_index, entries = parse_sitemap(resp.text)
        if is_index:
            children = [u for u, _ in entries
                        if same_site(source["url"], u)][:MAX_INDEX_CHILDREN]
            entries = []
            for child in children:
                try:
                    sub = client.get(child)
                except httpx.HTTPError:
                    continue
                if sub.status_code >= 400:
                    continue
                entries.extend(parse_sitemap(sub.text)[1])
        kept = editorial_only(
            [(u, m) for u, m in entries
             if same_site(source["url"], u) and is_allowed(u, disallow)])
        if kept:
            out.status, out.sitemap_url, out.urls = "ok", candidate, kept
            out.detail = f"{len(kept)} URL(s) from {candidate}"
            return out
    return out


def editorial_only(entries: list[tuple[str, datetime | None]],
                   rules: dict[str, Any] | None = None,
                   ) -> list[tuple[str, datetime | None]]:
    """Keep the URLs that look like published writing.

    The same two tests the listing path applies -- an editorial stem in the path and
    none of the reject patterns -- plus the translation filter a feed never needs.
    """
    rules = rules if rules is not None else load_rules()
    stems = [s.lower() for s in (rules.get("editorial_segments") or [])]
    reject = [r.lower() for r in (rules.get("reject_patterns") or [])]
    out = []
    for url, mod in entries:
        low = url.lower()
        if any(bad in low for bad in reject):
            continue
        if _is_translation(url):
            continue
        if not _has_editorial_section(url, stems):
            continue
        out.append((url, mod))
    return out


def recent_urls(entries: list[tuple[str, datetime | None]],
                now: datetime | None = None,
                window_days: int = DEFAULT_WINDOW_DAYS,
                limit: int = DEFAULT_MAX_ITEMS) -> list[tuple[str, datetime]]:
    """Newest first, dated only, inside the window.

    An undated sitemap entry is unusable here: this is a daily intelligence system,
    and a URL with no date cannot be told from the archive. Section 14 would have to
    guess, and `_parse_date` exists precisely so it never does.
    """
    now = now or datetime.now(timezone.utc)
    floor = now - timedelta(days=window_days)
    horizon = now + timedelta(hours=24)
    dated = [(u, m) for u, m in entries if m and floor <= m <= horizon]
    dated.sort(key=lambda pair: pair[1], reverse=True)
    return dated[:limit]


def enabled_for(source: dict[str, Any], rules: dict[str, Any] | None = None) -> bool:
    """Is sitemap ingestion switched on for this source?

    Opt-in, like a listing path, and for the same reason: a sitemap lists the whole
    site with no editorial curation behind it, so whether it yields articles or
    section fronts is a measured fact about that publisher, never an assumption.
    """
    rules = rules if rules is not None else load_rules()
    host = urlparse(source["url"]).netloc.lower()
    return any(h.lower() in host for h in (rules.get("sitemap_sources") or []))


def extract_sitemap(source: dict[str, Any], seen: set[str],
                    rules: dict[str, Any] | None = None,
                    max_items: int = DEFAULT_MAX_ITEMS,
                    window_days: int = DEFAULT_WINDOW_DAYS) -> SitemapOutcome:
    """Fetch a source's newest sitemap-listed articles.

    The sitemap supplies the date, and `_fetch_article` supplies the body with the
    same MIN_ARTICLE_CHARS floor the listing path uses -- which is what keeps an
    index page like /en/research out, since a sitemap cannot tell an article from a
    section front.
    """
    rules = rules if rules is not None else load_rules()
    with httpx.Client(headers={"User-Agent": UA}, timeout=httpx.Timeout(20.0),
                      follow_redirects=True) as client:
        out = discover(source, client)
        if out.status != "ok":
            return out

        fresh = [(u, m) for u, m in recent_urls(
            out.urls, window_days=window_days, limit=max_items * 3)
            if u not in seen][:max_items]
        if not fresh:
            out.status = "no_sitemap"
            out.detail = (f"{len(out.urls)} URL(s) but none dated inside "
                          f"{window_days}d and unseen")
            return out

        for url, lastmod in fresh:
            item = _fetch_article(client, source, url, out.sitemap_url)
            if not item:
                continue        # below MIN_ARTICLE_CHARS: a section front, not an article
            # The page's own metadata wins; lastmod is the fallback, and section 14
            # needs a date more than it needs the publisher's preferred one.
            if not item.get("published_at"):
                item["published_at"] = lastmod.isoformat()
                item["metadata"]["date_source"] = "sitemap_lastmod"
            item["metadata"]["via"] = "sitemap"
            out.items.append(item)

        if out.items:
            out.detail = (f"{len(out.items)} item(s) from {out.sitemap_url} "
                          f"({len(fresh)} candidate(s), floor {MIN_ARTICLE_CHARS} chars)")
        else:
            out.status = "no_sitemap"
            out.detail = (f"{len(fresh)} dated URL(s), none with "
                          f"{MIN_ARTICLE_CHARS}+ chars of article text")
    return out
