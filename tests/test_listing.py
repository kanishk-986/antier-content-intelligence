"""Listing extraction. Offline: link selection is the logic worth testing."""

import os
import sys

import httpx
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.ingestion import listing, urls
from src.ingestion.listing import (
    _flag_shared_dates,
    candidate_links,
    load_rules,
    rules_for,
)

REJECT = [r.lower() for r in (load_rules().get("reject_patterns") or [])]

HTML = """
<a href="/news/press/2026/mastercard-unveils-agent-pay/">Agent Pay</a>
<a href="/news/press/stablecoin-settlement-expansion">Stablecoin settlement</a>
<a href="/products-and-services/capital-liquidity-optimization">Capital Optimization</a>
<a href="/news">News</a>
<a href="/careers">Careers</a>
<a href="/news/press/report.pdf">PDF</a>
<a href="https://other.test/news/press/elsewhere-story-here">Offsite</a>
<a href="mailto:a@b.test">Mail</a>
<a href="#top">Anchor</a>
<a href="/news/press/2026/mastercard-unveils-agent-pay/">Dupe</a>
"""


def links():
    return candidate_links(HTML, "https://acme.test/news/press", REJECT)


def test_article_links_are_found():
    assert "https://acme.test/news/press/2026/mastercard-unveils-agent-pay/" in links()
    assert "https://acme.test/news/press/stablecoin-settlement-expansion" in links()


def test_product_pages_are_excluded_by_the_path_prefix():
    """The constraint that matters: an article reached from /news/press lives under
    it. Without this, a 3-word product slug qualifies and marketing copy enters the
    corpus, which section 2.2 forbids."""
    assert not any("products-and-services" in u for u in links())


def test_offsite_links_excluded():
    assert not any("other.test" in u for u in links())


def test_nav_and_reject_patterns_excluded():
    got = links()
    assert not any(u.endswith("/careers") for u in got)
    assert not any(u.endswith(".pdf") for u in got)


def test_the_listing_page_itself_is_not_a_candidate():
    assert "https://acme.test/news" not in links()
    assert "https://acme.test/news/press" not in links()


def test_mailto_and_anchors_excluded():
    assert not any(u.startswith("mailto:") or "#" in u for u in links())


def test_duplicates_collapse():
    got = links()
    assert len(got) == len(set(got))


def test_overrides_match_on_host_substring():
    rules = load_rules()
    assert rules_for("www.mastercard.com", rules).get("listing_paths")
    assert rules_for("unknown-host.test", rules) == {}


def test_shared_date_is_flagged_not_deleted():
    """Nulling a date destroys what the momentum engine needs; annotate instead."""
    items = [
        {"published_at": "2026-10-12T00:00:00+00:00", "metadata": {}},
        {"published_at": "2026-10-12T00:00:00+00:00", "metadata": {}},
        {"published_at": "2026-10-12T00:00:00+00:00", "metadata": {}},
        {"published_at": "2026-10-12T00:00:00+00:00", "metadata": {}},
    ]
    _flag_shared_dates(items)
    assert all(i["published_at"] == "2026-10-12T00:00:00+00:00" for i in items)
    assert all(i["metadata"]["date_confidence"] == "low" for i in items)


def test_distinct_dates_are_not_flagged():
    items = [
        {"published_at": "2026-10-01T00:00:00+00:00", "metadata": {}},
        {"published_at": "2026-10-05T00:00:00+00:00", "metadata": {}},
        {"published_at": "2026-10-09T00:00:00+00:00", "metadata": {}},
    ]
    _flag_shared_dates(items)
    assert not any("date_confidence" in i["metadata"] for i in items)


def test_too_few_items_to_judge_are_left_alone():
    items = [{"published_at": "2026-10-12T00:00:00+00:00", "metadata": {}}]
    _flag_shared_dates(items)
    assert "date_confidence" not in items[0]["metadata"]


# --- the section constraint, and the four bugs it had ------------------------

def test_a_listing_url_ending_in_a_filename_still_matches_links():
    """KPMG, Deloitte and EY list at /xx/en/our-insights.html. A prefix of
    "...our-insights.html/" prefixes nothing, so every link was rejected."""
    html = '<a href="/xx/en/media/press-releases/2026/05/kpmg-signs-alliance">x</a>'
    got = listing.candidate_links(html, "https://kpmg.test/xx/en/media.html", [])
    assert got == ["https://kpmg.test/xx/en/media/press-releases/2026/05/kpmg-signs-alliance"]


def test_articles_under_a_sibling_path_are_kept():
    """The World Bank lists at /ext/en/news and publishes at /en/news/... A strict
    prefix test dropped all eight of its press releases."""
    html = ('<a href="/en/news/press-release/2026/10/12/world-bank-launches-hub">x</a>')
    got = listing.candidate_links(html, "https://worldbank.test/ext/en/news", [])
    assert len(got) == 1 and "/en/news/press-release/" in got[0]


def test_a_locale_segment_is_never_treated_as_a_section():
    """ey.com lists at /en_gl/insights. Treating "en_gl" as a section admitted 88
    service pages from the whole site; only /insights should qualify."""
    html = ('<a href="/en_gl/services/strategy/corporate-growth-strategy">no</a>'
            '<a href="/en_gl/insights/consulting/how-a-leader-transformed">yes</a>')
    got = listing.candidate_links(html, "https://ey.test/en_gl/insights", [])
    assert len(got) == 1 and "/insights/" in got[0]


@pytest.mark.parametrize("path,expected", [
    ("/global/en/our-thinking.html", ""),       # all-locale prefix constrains nothing
    ("/xx/en/media.html", ""),
    ("/en/news", "/en/news"),
    ("/ext/en/news", "/ext/en/news"),
])
def test_an_all_locale_prefix_is_dropped(path, expected):
    assert listing._listing_prefix(path) == expected


def test_media_assets_are_rejected():
    """Deloitte serves /content/dam/.../2025/Our-thinking-xyz.jpg, which carries a
    year and a hyphenated slug and passed every other test."""
    html = ('<a href="/global/en/our-thinking/2025/Our-thinking-digital-assets.jpg">x</a>'
            '<a href="/global/en/our-thinking/2025/tokenised-funds-outlook">y</a>')
    reject = [r.lower() for r in listing.load_rules()["reject_patterns"]]
    got = listing.candidate_links(html, "https://deloitte.test/global/en/our-thinking",
                                  reject)
    assert len(got) == 1 and got[0].endswith("tokenised-funds-outlook")


@pytest.mark.parametrize("registry,final,same", [
    ("https://kpmg.com", "https://kpmg.com/xx/en/media.html", True),
    ("https://kpmg.com", "https://www.kpmg.com/news", True),
    ("https://cadwalader.com", "https://www.hlc.com/", False),
    ("https://acme.co.uk", "https://news.acme.co.uk/x", True),
    ("https://acme.co.uk", "https://other.co.uk/x", False),
])
def test_offsite_redirect_detection(registry, final, same):
    """cadwalader.com/press-releases lands on hlc.com. Same-host filtering then
    measures against the wrong host, and the corpus gains items attributed to a
    source that never published them."""
    assert urls.same_site(registry, final) is same


# --- the page that answers must be a listing ---------------------------------

STEMS = [s.lower() for s in (load_rules().get("editorial_segments") or [])]


@pytest.mark.parametrize("url,ok,why", [
    ("https://blackrock.test/corporate/home", False,
     "newsroom redirected to the homepage; 'corporate' then matched the whole site"),
    ("https://kpmg.test/xx/en/media.html", True, "media is editorial"),
    ("https://worldbank.test/ext/en/news", True, "news is editorial"),
    ("https://ey.test/en_us/newsroom", True, "newsroom is editorial"),
    ("https://deloitte.test/global/en/our-thinking.html", True,
     "matched by stem, not by an exact name"),
    ("https://acme.test/products-and-services", False, "a product index"),
    ("https://acme.test/about/leadership", False, "neither news nor product"),
])
def test_only_an_editorial_index_counts_as_a_listing(url, ok, why):
    assert listing._has_editorial_section(url, STEMS) is ok, why


def test_no_configured_stems_means_no_opinion():
    """An empty config must not silently reject every source."""
    assert listing._has_editorial_section("https://x.test/corporate/home", []) is True


def test_the_real_config_carries_stems():
    """The guard is only load-bearing if the config is populated."""
    assert len(STEMS) >= 10
    assert "news" in STEMS and "thinking" in STEMS


# --- a refusal is not our bug ------------------------------------------------

@pytest.mark.parametrize("exc,status", [
    (httpx.RemoteProtocolError("Server disconnected without sending a response."),
     "blocked_transport"),
    (httpx.ReadError("Connection reset by peer"), "blocked_transport"),
    (httpx.ConnectError("Connection refused"), "blocked_transport"),
    (httpx.ConnectError("[SSL: CERTIFICATE_VERIFY_FAILED] verify failed"), "error"),
    (httpx.ConnectTimeout("timed out"), "error"),
])
def test_transport_refusal_is_not_reported_as_our_error(exc, status):
    """A server that completes a handshake then drops the connection is refusing us.
    Reported as `error` it sits on the health report's "fixable here" list forever.
    McKinsey does exactly this."""
    assert listing._classify_transport(exc)[0] == status


def test_the_detail_survives_classification():
    _, detail = listing._classify_transport(httpx.ReadError("Connection reset by peer"))
    assert "Connection reset by peer" in detail


def test_link_scanning_is_bounded():
    """A listing page should not offer thousands of article links. Scanning every
    one of a hostile or generated page costs memory for nothing, since the caller
    takes at most MAX_CANDIDATES anyway."""
    html = "".join(f'<a href="/news/item-number-{i}">x</a>' for i in range(10_000))
    got = listing.candidate_links(html, "https://a.test/news", [])
    assert len(got) == listing.MAX_LINKS_SCANNED


@pytest.mark.parametrize("html", [
    "", "<html></html>",
    '<a href="https://a.test/news/x-y-z>text',          # unterminated attribute
    '<a href="javascript:alert(1)">x</a>',
    '<a href="data:text/html,<script>">x</a>',
])
def test_malformed_html_yields_no_bad_links(html):
    got = listing.candidate_links(html, "https://a.test/news", [])
    assert all(u.startswith("https://a.test/") for u in got)
