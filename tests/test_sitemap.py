"""Sitemap ingestion. Offline: robots parsing, URL selection and filtering."""

import os
import sys
from datetime import datetime, timedelta, timezone

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.ingestion import sitemap as sm

NOW = datetime(2026, 10, 13, 12, 0, tzinfo=timezone.utc)

ROBOTS = """
# comment
User-agent: *
Disallow: /external/country/
Disallow: /search
Sitemap: https://acme.test/sitemap.xml

User-agent: BadBot
Disallow: /
"""

URLSET = """<?xml version="1.0"?>
<urlset>
  <url><loc>https://acme.test/news/alpha-beta-gamma</loc>
       <lastmod>2026-10-12</lastmod></url>
  <url><loc>https://acme.test/news/delta-epsilon-zeta</loc>
       <lastmod>2026-01-02T08:00:00Z</lastmod></url>
  <url><loc>https://acme.test/news/no-date-here</loc></url>
</urlset>
"""

INDEX = """<?xml version="1.0"?>
<sitemapindex>
  <sitemap><loc>https://acme.test/sitemap-news.xml</loc></sitemap>
</sitemapindex>
"""


# --- robots.txt ---------------------------------------------------------------

def test_sitemap_and_disallow_are_read():
    sitemaps, disallow = sm.parse_robots(ROBOTS)
    assert sitemaps == ["https://acme.test/sitemap.xml"]
    assert disallow == ["/external/country/", "/search"]


def test_a_rule_for_a_named_crawler_is_not_ours():
    """BadBot is disallowed everything. Claiming that group would be reading the
    file to suit ourselves; claiming it does not apply to us is simply true."""
    _, disallow = sm.parse_robots(ROBOTS)
    assert "/" not in disallow


def test_disallow_is_honoured():
    dis = ["/external/country/", "/search"]
    assert not sm.is_allowed("https://acme.test/external/country/x", dis)
    assert not sm.is_allowed("https://acme.test/search?q=1", dis)
    assert sm.is_allowed("https://acme.test/news/alpha-beta-gamma", dis)


def test_a_blanket_disallow_does_not_block_everything():
    """Disallow: / under User-agent: * would mean no crawling at all. The sitemap
    path is not the place to decide that, and treating it as a prefix match would
    silently reject every URL with no explanation."""
    assert sm.is_allowed("https://acme.test/news/x", ["/"])


def test_empty_robots_permits_everything():
    assert sm.parse_robots("") == ([], [])


# --- parsing ------------------------------------------------------------------

def test_lastmod_belongs_to_its_own_url():
    """Parsed per entry, not by two independent findall() calls -- which would pair
    the second URL with the third date as soon as one entry omitted a lastmod."""
    is_index, entries = sm.parse_sitemap(URLSET)
    assert not is_index
    assert entries[0] == ("https://acme.test/news/alpha-beta-gamma",
                          datetime(2026, 10, 12, tzinfo=timezone.utc))
    assert entries[1][1] == datetime(2026, 1, 2, 8, 0, tzinfo=timezone.utc)
    assert entries[2][1] is None


def test_an_index_is_recognised():
    is_index, entries = sm.parse_sitemap(INDEX)
    assert is_index and entries[0][0].endswith("sitemap-news.xml")


def test_a_malformed_sitemap_yields_nothing_rather_than_raising():
    assert sm.parse_sitemap("<html>not a sitemap</html>") == (False, [])


# --- selection ----------------------------------------------------------------

def _entry(days_ago, slug="news/alpha-beta-gamma"):
    return (f"https://acme.test/{slug}", NOW - timedelta(days=days_ago))


def test_newest_first_within_the_window():
    picked = sm.recent_urls([_entry(40), _entry(1), _entry(10)], now=NOW, limit=5)
    assert [n for _, n in picked] == sorted((n for _, n in picked), reverse=True)


def test_an_undated_url_is_not_used():
    """This is a daily intelligence system: a URL with no date cannot be told from
    the archive, and section 14 must never guess one."""
    picked = sm.recent_urls([("https://acme.test/news/x", None), _entry(1)],
                            now=NOW)
    assert len(picked) == 1


def test_anything_older_than_the_window_is_dropped():
    assert sm.recent_urls([_entry(400)], now=NOW, window_days=120) == []


def test_a_future_lastmod_is_dropped():
    """Same rule as momentum: a date that has not arrived is not news."""
    future = [("https://acme.test/news/x", NOW + timedelta(days=30))]
    assert sm.recent_urls(future, now=NOW) == []


def test_the_limit_is_respected():
    assert len(sm.recent_urls([_entry(i) for i in range(1, 30)], now=NOW,
                              limit=5)) == 5


# --- filtering ----------------------------------------------------------------

@pytest.mark.parametrize("url,kept,why", [
    ("https://acme.test/news/alpha-beta-gamma", True, "an article"),
    ("https://acme.test/blog/a-real-post-here", True, "an article"),
    ("https://acme.test/products-and-services/optimisation", False,
     "a product page; a sitemap has no editorial curation behind it"),
    ("https://acme.test/press-releases/acme-executive-bios/jane-doe", False,
     "213 words of biography clears the article floor"),
    ("https://acme.test/en/expert/analyst", False, "an analyst profile"),
    ("https://acme.test/pt-br/news/us-banks-interest", False,
     "a Portuguese translation of a page we already take in English"),
    ("https://acme.test/es/news/us-banks-interest", False, "a Spanish translation"),
    ("https://acme.test/en/news/us-banks-interest", True, "the English original"),
    ("https://acme.test/news/report.pdf", False, "not a web page"),
])
def test_only_editorial_english_pages_survive(url, kept, why):
    got = sm.editorial_only([(url, NOW)])
    assert bool(got) is kept, why


def test_enabled_for_is_opt_in():
    rules = {"sitemap_sources": ["ondo.finance"]}
    assert sm.enabled_for({"url": "https://ondo.finance"}, rules)
    assert not sm.enabled_for({"url": "https://dtcc.com"}, rules)
    assert not sm.enabled_for({"url": "https://ondo.finance"}, {})


def test_the_real_config_enables_only_verified_sources():
    from src.ingestion.listing import load_rules
    enabled = load_rules().get("sitemap_sources") or []
    assert "ondo.finance" in enabled
    assert "dtcc.com" not in enabled, (
        "DTCC yields 4 articles in 6; it needs a path allowlist first")


# --- malformed input ----------------------------------------------------------

def test_a_cdata_wrapped_loc_is_read():
    """Valid and used by real sitemaps. A pattern that stops at the first "<" reads
    such an entry as empty and silently drops every URL in the file."""
    _, entries = sm.parse_sitemap(
        "<urlset><url><loc><![CDATA[https://a.test/news/x-y-z]]></loc>"
        "<lastmod>2026-10-14</lastmod></url></urlset>")
    assert entries[0][0] == "https://a.test/news/x-y-z"
    assert entries[0][1] is not None


@pytest.mark.parametrize("xml", [
    "", "<html><body>hi</body></html>",
    "<urlset><url><loc>https://a.test/news/x</lo",      # truncated mid-tag
    "<urlset><url><loc></loc></url></urlset>",
])
def test_malformed_xml_yields_nothing_rather_than_raising(xml):
    is_index, entries = sm.parse_sitemap(xml)
    assert is_index is False
    assert all(url.strip() for url, _ in entries)


def test_whitespace_around_a_loc_is_trimmed():
    _, entries = sm.parse_sitemap(
        "<urlset><url><loc>\n  https://a.test/news/alpha-beta-gamma  \n</loc>"
        "</url></urlset>")
    assert entries[0][0] == "https://a.test/news/alpha-beta-gamma"


def test_an_unparseable_lastmod_is_none_not_a_guess():
    _, entries = sm.parse_sitemap(
        "<urlset><url><loc>https://a.test/news/x-y-z</loc>"
        "<lastmod>soon</lastmod></url></urlset>")
    assert entries[0][1] is None
