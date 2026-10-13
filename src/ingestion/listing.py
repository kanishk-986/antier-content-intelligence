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
from src.ingestion.urls import same_site

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

# Locale and CMS-plumbing path segments carry no topic, so they must not be treated
# as a section: matching on "en" or "en_gl" would admit the entire site. Enumerating
# locales is a losing game -- ey.com uses /en_gl, kpmg.com /xx -- so the shape is
# matched instead: one or two letters, optionally a two-part tag like en_gl.
_LOCALE_SHAPE = re.compile(r"^[a-z]{2}([_-][a-z]{2})?$|^[a-z]$")
_PLUMBING_SEGMENTS = {
    "ext", "content", "web", "site", "sites", "global", "www", "html",
    "index", "home", "page", "pages", "default", "xx", "dam", "etc",
}


def _is_locale(segment: str) -> bool:
    seg = segment.split(".")[0].lower()
    return bool(_LOCALE_SHAPE.match(seg)) or seg in _PLUMBING_SEGMENTS


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


# A server that completes a TLS handshake and then drops the connection, or resets
# it mid-response, is refusing us. That is the publisher's decision and belongs with
# the other blocks -- reported as `error` it sits on the health report's "fixable
# here" list forever, drawing attention that cannot fix it. McKinsey does this.
_REFUSAL_TELLS = (
    "server disconnected",
    "connection reset",
    "connection refused",
    "remoteprotocolerror",
    "incomplete read",
)


def _classify_transport(exc: Exception) -> tuple[str, str]:
    text = f"{type(exc).__name__}: {exc}".strip()
    low = text.lower()
    if any(tell in low for tell in _REFUSAL_TELLS):
        return "blocked_transport", text[:160]
    return "error", text[:160]


def _has_editorial_section(url: str, stems: list[str]) -> bool:
    """Does this page's path look like an editorial index at all?

    A redirect can land somewhere that is readable but is not a listing.
    blackrock.com/corporate/newsroom answers at /corporate/home; "corporate" then
    matches every path on the site, so the extractor pulled in evergreen marketing
    that section 2.2 excludes. Requiring an editorial stem in the path costs nothing
    on a real newsroom and stops that class of page entirely.
    """
    if not stems:
        return True
    sections = _section_segments(urlparse(url).path)
    return any(stem in seg for seg in sections for stem in stems)


def _listing_prefix(path: str) -> str:
    """The directory a listing page sits in.

    A listing URL ending in a filename -- /xx/en/our-insights.html, common on AEM
    and SharePoint sites -- has no path below it, so `startswith(prefix + "/")`
    rejected every link on the page. KPMG, Deloitte and EY all failed this way.
    """
    path = path.rstrip("/")
    last = path.rsplit("/", 1)[-1]
    if "." in last and not last.startswith("."):
        path = path[: -len(last)].rstrip("/")
    # A prefix of nothing but locale segments constrains nothing: deloitte.com's
    # /global/en/our-thinking.html would reduce to /global/en, which prefixes the
    # entire site. Section matching is the only constraint left in that case.
    segments = [s for s in path.strip("/").split("/") if s]
    if segments and all(_is_locale(s) for s in segments):
        return ""
    return path


def _section_segments(path: str) -> set[str]:
    """The topical segments of a listing path, ignoring locale and CMS plumbing.

    A CMS often serves its listing and its articles under sibling prefixes: the
    World Bank lists at /ext/en/news and publishes at /en/news/press-release/...
    A strict prefix test drops every article. Matching on the topical segment
    instead keeps /products-and-services/... out while letting the siblings in.
    """
    return {seg.split(".")[0].lower() for seg in path.strip("/").split("/")
            if seg and not _is_locale(seg)}


def candidate_links(html: str, listing_url: str, reject: list[str]) -> list[str]:
    """Article-looking links from a listing page, same host only.

    Three constraints, all required:

    1. Same host as the listing.
    2. **Within the listing's section.** Under the listing's own directory, or
       under one of its topical segments. An article reached from /news lives under
       /news somewhere. Without this the slug heuristic happily matches
       /products-and-services/capital-liquidity-optimization, which is a product
       page -- precisely the marketing content section 2.2 forbids in the corpus.
    3. A path containing a year, or a slug of at least three hyphenated words.
    """
    base = urlparse(listing_url)
    prefix = _listing_prefix(base.path)
    sections = _section_segments(base.path)
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
        # Constraint 2: below the listing's directory, or inside its section.
        if prefix and not path.startswith(prefix + "/"):
            segments = {seg.split(".")[0].lower()
                        for seg in path.strip("/").split("/")}
            if not sections or not (sections & segments):
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
    editorial = [s.lower() for s in (rules.get("editorial_segments") or [])]
    out = ListingOutcome(source["id"], source["name"], "no_listing")

    with httpx.Client(headers={"User-Agent": UA}, timeout=httpx.Timeout(20.0),
                      follow_redirects=True) as client:
        shell_seen = False
        for listing_url in _resolve_listings(source, rules):
            try:
                resp = client.get(listing_url)
            except httpx.HTTPError as exc:
                out.status, out.detail = _classify_transport(exc)
                continue
            if resp.status_code in (401, 403, 429):
                out.status = "blocked"
                out.detail = f"HTTP {resp.status_code} on {listing_url}"
                continue
            if resp.status_code >= 400:
                continue

            # The URL after redirects, not the one requested. kpmg.com/news lands
            # on /xx/en/media.html, and its article links sit under
            # /xx/en/media/press-releases/... Deriving the section from the
            # requested /news rejected every one of them.
            final_url = str(resp.url)

            # ...but a redirect that leaves the domain changes who is speaking.
            # cadwalader.com/press-releases lands on hlc.com, a different firm;
            # same-host filtering then measures against the wrong host and the
            # corpus gains items attributed to a source that never published them.
            if not same_site(source["url"], final_url):
                out.status = "offsite_redirect"
                out.detail = (f"{listing_url} redirects off-domain to "
                              f"{urlparse(final_url).netloc}")
                continue

            if not _has_editorial_section(final_url, editorial):
                out.status = "not_a_listing"
                out.detail = (f"{listing_url} answers at {final_url}, which is not "
                              "an editorial index")
                continue

            links = candidate_links(resp.text, final_url, reject)
            if len(links) < JS_SHELL_LINK_FLOOR and _NEXT_SHELL.search(resp.text):
                shell_seen = True
                continue
            if not links:
                continue

            out.listing_url = final_url
            fresh = [u for u in links if u not in seen][:max_candidates]
            for url in fresh:
                item = _fetch_article(client, source, url, final_url)
                if item:
                    out.items.append(item)
            _flag_shared_dates(out.items)
            if out.items:
                out.status = "ok"
                out.detail = (f"{len(out.items)} item(s) from {final_url} "
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


def _fetch_article(client: httpx.Client, source: dict[str, Any], url: str,
                   listing_url: str | None = None) -> dict[str, Any] | None:
    """One article from a listing page.

    `listing_url` is the index the link was found on, recorded so an item's
    provenance is checkable later. It used to be set to the article's own URL, which
    made the field useless for exactly the audit it exists to support.
    """
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
        "metadata": {"listing_url": listing_url, "article_url": url,
                     "source_name": source["name"], "via": "listing",
                     "word_count": len(text.split()), "text_source": "article"},
    }
