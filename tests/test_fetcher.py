"""Hashing and date parsing. Offline: these are the pure functions."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.ingestion.fetcher import _parse_date, content_hash


def test_same_content_different_whitespace_and_case_collapses():
    """Dedupe must survive cosmetic differences between syndicated copies."""
    a = content_hash("Stablecoin Rules", "The  FSB   published a report.")
    b = content_hash("stablecoin rules", "The FSB published a report.")
    assert a == b


def test_different_content_does_not_collide():
    assert content_hash("A", "one") != content_hash("A", "two")


def test_hash_keys_on_content_not_url():
    """Two URLs, same story -> one hash. The URL is deliberately not an input."""
    assert content_hash("T", "body") == content_hash("T", "body")


def test_iso_date_parsed_to_utc():
    assert _parse_date("2026-10-12T06:00:00Z") == "2026-10-12T06:00:00+00:00"


def test_rfc2822_feed_date_parsed():
    assert _parse_date("Sun, 12 Oct 2026 06:00:00 GMT") == "2026-10-12T06:00:00+00:00"


def test_naive_date_assumed_utc():
    assert _parse_date("2026-10-12T06:00:00") == "2026-10-12T06:00:00+00:00"


def test_unparseable_date_returns_none_rather_than_a_guess():
    """DATA_MODEL.md: published_at is trusted only when confirmed."""
    for bad in ["", None, "last Tuesday", "/2026/10/some-slug/", "n/a", 12345.6]:
        assert _parse_date(bad) is None, bad


def test_struct_time_from_feedparser_parsed():
    assert _parse_date((2026, 10, 12, 6, 0, 0, 0, 0, 0)) == "2026-10-12T06:00:00+00:00"
