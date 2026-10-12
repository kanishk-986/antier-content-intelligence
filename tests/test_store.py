"""Store behaviour. Offline: no network, temp database per test."""

import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.database.sqlite_store import SqliteStore


@pytest.fixture
def store():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.unlink(path)
    s = SqliteStore(path)
    s.migrate()
    yield s
    s.close()
    if os.path.exists(path):
        os.unlink(path)


SOURCE = {"id": "src-001", "name": "BIS", "url": "https://bis.org",
          "source_type": "regulator", "authority_score": 10,
          "topics": ["cbdc"], "active": True}


def item(h, url="https://x/1", title="T", text="body"):
    return {"id": "i-" + h[:6], "source_id": "src-001", "url": url, "title": title,
            "clean_text": text, "content_hash": h}


def test_migrate_is_idempotent(store):
    store.migrate()
    store.migrate()
    assert store.counts()["sources"] == 0


def test_all_nine_tables_exist(store):
    assert len(store.counts()) == 9


def test_upsert_source_updates_rather_than_duplicates(store):
    store.upsert_source(SOURCE)
    store.upsert_source({**SOURCE, "name": "BIS renamed"})
    rows = store.active_sources()
    assert len(rows) == 1
    assert rows[0]["name"] == "BIS renamed"


def test_active_sources_ordered_by_authority_desc(store):
    store.upsert_source(SOURCE)
    store.upsert_source({**SOURCE, "id": "src-002", "name": "Blog",
                         "authority_score": 7})
    assert [r["authority_score"] for r in store.active_sources()] == [10, 7]


def test_inactive_sources_excluded(store):
    store.upsert_source({**SOURCE, "active": False})
    assert store.active_sources() == []


def test_duplicate_content_hash_is_rejected(store):
    """Section 10.2: the same story from a second URL is one item."""
    store.upsert_source(SOURCE)
    assert store.insert_content(item("h" * 64)) is True
    assert store.insert_content(
        {**item("h" * 64, url="https://other/2"), "id": "i-2"}
    ) is False
    assert store.counts()["content_items"] == 1


def test_content_hash_exists(store):
    store.upsert_source(SOURCE)
    store.insert_content(item("a" * 64))
    assert store.content_hash_exists("a" * 64)
    assert not store.content_hash_exists("b" * 64)


def test_seen_urls_drives_the_efficiency_rule(store):
    store.upsert_source(SOURCE)
    assert store.seen_urls("src-001") == set()
    store.record_fetch("src-001", "https://x/1", "h", "2026-10-12T00:00:00+00:00")
    assert store.seen_urls("src-001") == {"https://x/1"}


def test_record_fetch_is_upsert_not_append(store):
    store.upsert_source(SOURCE)
    for _ in range(3):
        store.record_fetch("src-001", "https://x/1", "h", "2026-10-12T00:00:00+00:00")
    assert store.counts()["fetch_state"] == 1


def test_audit_log_is_append_only(store):
    store.audit("system", "run_a")
    store.audit("system", "run_b")
    assert store.counts()["audit_log"] == 2


def test_foreign_key_is_enforced(store):
    """Content must belong to a known source."""
    import sqlite3
    with pytest.raises(sqlite3.IntegrityError):
        store.insert_content({**item("c" * 64), "source_id": "src-missing"})


def test_unconfirmed_date_is_stored_as_null_not_fabricated(store):
    store.upsert_source(SOURCE)
    store.insert_content({**item("d" * 64), "published_at": None})
    assert store.content_items()[0]["published_at"] is None
