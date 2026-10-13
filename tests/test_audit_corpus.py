"""The corpus audit. This code deletes rows from the live database, so the
classification and the cascade are both worth testing.

Three of its bugs are already recorded in CHANGELOG: it left purged URLs in the
section 10.2 seen set so they could never return, it judged an article's own URL
instead of the index it came from, and it left empty narratives behind.
"""

import importlib.util
import os
import sys
import uuid

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from src.database.sqlite_store import SqliteStore
from src.ingestion.listing import load_rules

_spec = importlib.util.spec_from_file_location(
    "audit_corpus", os.path.join(ROOT, "scripts", "audit_corpus.py"))
audit = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(audit)

STEMS = [s.lower() for s in (load_rules().get("editorial_segments") or [])]


def _row(url, metadata):
    return {"id": "i1", "url": url, "title": "t", "metadata": metadata,
            "source_id": "s1", "name": "Src"}


# --- classification -----------------------------------------------------------

def test_a_feed_item_from_the_same_site_is_clean():
    meta = '{"feed_url": "https://richmondfed.org/?cc_view=rss"}'
    assert audit.classify(
        _row("https://www.richmondfed.org/publications/x", meta), STEMS) is None


def test_an_outbound_feed_link_is_offsite():
    meta = '{"feed_url": "https://richmondfed.org/?cc_view=rss"}'
    assert audit.classify(
        _row("https://doi.org/10.1093/jeea/jvag015", meta), STEMS) == "offsite"


def test_a_renamed_publisher_is_not_offsite():
    """EigenCloud's blog.eigencloud.xyz feed resolves to eigenlabs.org. Judging
    against the registry URL would have discarded eight real articles."""
    meta = '{"feed_url": "https://www.eigenlabs.org/blog/rss/"}'
    assert audit.classify(
        _row("https://www.eigenlabs.org/blog/introducing-yukon/", meta), STEMS) is None


def test_a_listing_item_is_judged_by_its_index_not_its_own_path():
    """A real newsroom links articles under /resources/ all the time. Judging the
    article URL purged a legitimate BitGo piece."""
    meta = '{"listing_url": "https://bitgo.com/newsroom", "via": "listing"}'
    assert audit.classify(
        _row("https://bitgo.com/resources/not-all-custody-is-equal", meta),
        STEMS) is None


def test_an_item_from_a_non_editorial_index_is_flagged():
    meta = '{"listing_url": "https://blackrock.com/corporate/home", "via": "listing"}'
    assert audit.classify(
        _row("https://blackrock.com/institutions/en-us/solutions/x", meta),
        STEMS) == "not_editorial"


def test_an_item_with_no_recorded_provenance_is_not_condemned():
    assert audit.classify(_row("https://x.test/a/b", "{}"),
                          STEMS) == "unverifiable_provenance"


@pytest.mark.parametrize("meta", [None, "", "{not json", "[]", "null"])
def test_unreadable_metadata_does_not_crash(meta):
    assert audit.classify(_row("https://x.test/a/b", meta),
                          STEMS) == "unverifiable_provenance"


# --- the cascade --------------------------------------------------------------

def _seeded(tmp_path):
    store = SqliteStore(str(tmp_path / "a.db"))
    store.migrate()
    store.upsert_source({"id": "s1", "name": "BlackRock",
                         "url": "https://blackrock.com", "source_type": "institution",
                         "authority_score": 9, "topics": "", "active": True})
    bad = str(uuid.uuid4())
    store.conn.execute(
        "INSERT INTO content_items (id, source_id, url, title, content_hash,"
        " retrieved_at, metadata) VALUES (?,?,?,?,?,?,?)",
        (bad, "s1", "https://blackrock.com/institutions/en-us/solutions/x", "Product",
         "h-bad", "2026-10-13T00:00:00+00:00",
         '{"listing_url": "https://blackrock.com/corporate/home"}'))
    store.record_fetch("s1", "https://blackrock.com/institutions/en-us/solutions/x",
                       "h-bad", "2026-10-13T00:00:00+00:00")
    nid, oid = str(uuid.uuid4()), str(uuid.uuid4())
    store.conn.execute("INSERT INTO narratives (id, name) VALUES (?,?)", (nid, "n"))
    store.conn.execute(
        "INSERT INTO narrative_items (narrative_id, content_id) VALUES (?,?)",
        (nid, bad))
    store.conn.execute(
        "INSERT INTO opportunities (id, narrative_id) VALUES (?,?)", (oid, nid))
    # qa_reviews.id is an INTEGER AUTOINCREMENT, not a uuid like the other tables.
    store.conn.execute(
        "INSERT INTO qa_reviews (opportunity_id, ai_decision) VALUES (?,?)",
        (oid, "REJECT"))
    store.conn.commit()
    return store, bad


def test_purge_removes_the_item_and_everything_that_referenced_it(tmp_path, monkeypatch):
    store, _ = _seeded(tmp_path)
    url = "https://blackrock.com/institutions/en-us/solutions/x"
    monkeypatch.setattr(sys, "argv",
                        ["audit", "--db", store.path, "--purge"])
    assert audit.main() == 0

    conn = SqliteStore(store.path).conn
    counts = {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
              for t in ("content_items", "narrative_items", "narratives",
                        "opportunities", "qa_reviews", "fetch_state")}
    assert counts["content_items"] == 0
    assert counts["narrative_items"] == 0
    assert counts["narratives"] == 0, "an empty narrative must not survive"
    assert counts["opportunities"] == 0
    assert counts["qa_reviews"] == 0
    assert counts["fetch_state"] == 0, (
        "a purged URL left in the seen set can never be re-ingested, so purging "
        "something legitimate would exclude it permanently and silently")
    assert url not in SqliteStore(store.path).seen_urls("s1")


def test_a_report_only_run_changes_nothing(tmp_path, monkeypatch):
    store, _ = _seeded(tmp_path)
    monkeypatch.setattr(sys, "argv", ["audit", "--db", store.path])
    assert audit.main() == 0
    conn = SqliteStore(store.path).conn
    assert conn.execute("SELECT COUNT(*) FROM content_items").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM fetch_state").fetchone()[0] == 1
