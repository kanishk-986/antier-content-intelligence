"""Listing-page extraction for sources with no RSS/Atom feed.

Phase 3b. Section 8 names Trafilatura/BeautifulSoup/Playwright "where permitted";
this is the static half. Six of the twelve highest-authority sources expose no feed
(SOURCE_POLICY.md), and they are the primary-announcement layer, so this is a
prerequisite rather than an enhancement.

Scope, measured 2026-10-12: static extraction reaches server-rendered listings.
Client-rendered sites (DTCC, Circle, Clearstream, Digital Asset all ship a Next.js
shell whose server HTML carries navigation only) need a browser and are reported
`js_rendered` rather than silently returned empty.

Dates come from trafilatura's metadata extraction -- meta tags, JSON-LD, visible
bylines -- never from a URL slug. DATA_MODEL.md trusts published_at only when
confirmed.
"""

from __future__ import annotations

import contextlib
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx
import trafilatura
import yaml

from src.ingestion.fetcher import UA, _parse_date, content_hash

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RULES_PATH = os.path.join(REPO, "config", "sources", "listing_rules.yaml")

# A page that yields less than this much text is navigation, not an article.
MIN_ARTICLE_CHARS = 400
# A listing whose server HTML has fewer than this many candidate links is almost
# certainly client-rendered.
JS_SHELL_LINK_FLOOR = 3
MAX_CANDIDATES = 12

_SLUG_WORDS = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+){2,}")   # >=3 hyphenated words
_YEAR = re.compile(r"/20\d\d(?:[/-]|$)")
_NEXT_SHELL = re.compile(r"/_next/static|window\.__NUXT__|__remixContext")


@dataclass
class ListingOutcome:
    source_id: str
    source_name: str
    status: str                 # ok | js_rendered | no_listing | blocked | error
    items: list[dict[str, Any]] = field(default_factory=list)
    detail: str = ""
    listing_url: str | None = None


def load_rules(path: str = RULES_PATH) -> dict[str, Any]:
    with open(path) as fh:
        return yaml.safe_load(fh) or {}


def rules_for(host: str, rules: dict[str, Any]) -> dict[str, Any]:
    for key, override in (rules.get("overrides") or {}).items():
        if key in host:
            return override
    return {}


def candidate_links(html: str, listing_url: str, reject: list[str]) -> list[str]:
    """Article-looking links from a listing page, same host only.

    Three constraints, all required:

    1. Same host as the listing.
    2. **Under the listing's own path prefix.** An article reached from /news lives
       under /news. Without this the slug heuristic happily matches
       /products-and-services/capital-liquidity-optimization, which is a product
       page -- precisely the marketing content section 2.2 forbids in the corpus.
    3. A path containing a year, or a slug of at least three hyphenated words.
    """
    base = urlparse(listing_url)
    prefix = base.path.rstrip("/")
    out: list[str] = []
    seen: set[str] = set()

    for href in re.findall(r'href=["\']([^"\']+)["\']', html):
        if href.startswith(("mailto:", "tel:", "javascript:", "#")):
            continue
        absolute = urljoin(listing_url, href)
        parsed = urlparse(absolute)
        if parsed.netloc.replace("www.", "") != base.netloc.replace("www.", ""):
            continue
        path = parsed.path.rstrip("/")
        if not path or path.count("/") < 1:
            continue
        # Constraint 2: must sit below the listing page, and be deeper than it.
        if prefix and not path.startswith(prefix + "/"):
            continue
        low = absolute.lower()
        if any(bad in low for bad in reject):
            continue
        last = path.rsplit("/", 1)[-1]
        if not (_YEAR.search(path) or _SLUG_WORDS.fullmatch(last)):
            continue
        key = absolute.split("?")[0].rstrip("/").lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(absolute)
    return out


def _resolve_listings(source: dict[str, Any], rules: dict[str, Any]) -> list[str]:
    host = urlparse(source["url"]).netloc
    override = rules_for(host, rules)
    paths = override.get("listing_paths") or rules.get("default_paths") or []
    root = f"{urlparse(source['url']).scheme}://{host}"
    return [urljoin(root, p) for p in paths]


def extract_listing(source: dict[str, Any], seen: set[str],
                    rules: dict[str, Any] | None = None,
                    max_candidates: int = MAX_CANDIDATES) -> ListingOutcome:
    """Fetch one source's listing page(s) and extract article items."""
    rules = rules if rules is not None else load_rules()
    reject = [r.lower() for r in (rules.get("reject_patterns") or [])]
    out = ListingOutcome(source["id"], source["name"], "no_listing")

    with httpx.Client(headers={"User-Agent": UA}, timeout=httpx.Timeout(20.0),
                      follow_redirects=True) as client:
        shell_seen = False
        for listing_url in _resolve_listings(source, rules):
            try:
                resp = client.get(listing_url)
            except httpx.HTTPError as exc:
                out.status, out.detail = "error", str(exc)[:160]
                continue
            if resp.status_code in (401, 403, 429):
                out.status = "blocked"
                out.detail = f"HTTP {resp.status_code} on {listing_url}"
                continue
            if resp.status_code >= 400:
                continue

            links = candidate_links(resp.text, listing_url, reject)
            if len(links) < JS_SHELL_LINK_FLOOR and _NEXT_SHELL.search(resp.text):
                shell_seen = True
                continue
            if not links:
                continue

            out.listing_url = listing_url
            fresh = [u for u in links if u not in seen][:max_candidates]
            for url in fresh:
                item = _fetch_article(client, source, url)
                if item:
                    out.items.append(item)
            _flag_shared_dates(out.items)
            if out.items:
                out.status = "ok"
                out.detail = (f"{len(out.items)} item(s) from {listing_url} "
                              f"({len(links)} candidates)")
                return out

        if shell_seen and not out.items:
            out.status = "js_rendered"
            out.detail = ("server HTML is a client-rendered shell; needs a browser "
                          "(section 8 Playwright)")
        elif out.status == "no_listing":
            out.detail = "no listing page yielded article-like links"
    return out


def _flag_shared_dates(items: list[dict[str, Any]]) -> None:
    """Flag -- do not delete -- a timestamp most items share.

    Some corporate sites stamp every page with one template date; others genuinely
    publish a batch on the same day. Both look identical from here, so guessing
    either way is wrong. Nulling the date destroys information the momentum engine
    (section 14) needs, so the date is kept and annotated instead, and the stage that
    cares decides how much to trust it.
    """
    if len(items) < 3:
        return
    dates = [i["published_at"] for i in items if i["published_at"]]
    if not dates:
        return
    shared = max(set(dates), key=dates.count)
    count = dates.count(shared)
    if count >= max(3, int(len(items) * 0.6)):
        for item in items:
            if item["published_at"] == shared:
                item["metadata"]["date_confidence"] = "low"
                item["metadata"]["date_note"] = (
                    f"timestamp shared by {count} of {len(items)} items from this "
                    "listing; may be a site template default"
                )


def _fetch_article(client: httpx.Client, source: dict[str, Any],
                   url: str) -> dict[str, Any] | None:
    try:
        page = client.get(url)
    except httpx.HTTPError:
        return None
    if page.status_code >= 400:
        return None

    text = trafilatura.extract(page.text, include_comments=False,
                               include_tables=True) or ""
    if len(text) < MIN_ARTICLE_CHARS:
        return None                       # navigation or a stub, not an article

    title, author, published = None, None, None
    # Metadata extraction is best-effort: a missing byline must not lose the article.
    with contextlib.suppress(Exception):
        md = trafilatura.extract_metadata(page.text)
        if md:
            title = (getattr(md, "title", None) or "").strip() or None
            author = (getattr(md, "author", None) or "").strip() or None
            published = _parse_date(getattr(md, "date", None))

    return {
        "source_id": source["id"],
        "url": url,
        "title": title,
        "author": author,
        "published_at": published,         # None when unconfirmed, never guessed
        "retrieved_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "raw_text": page.text,
        "clean_text": text,
        "content_hash": content_hash(title, text),
        "language": None,
        "metadata": {"listing_url": url, "source_name": source["name"],
                     "via": "listing"},
    }
