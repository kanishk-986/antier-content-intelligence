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


# --- source health log (migration 003) ---------------------------------------

def _store_with_source(tmp_path, **over):
    store = SqliteStore(str(tmp_path / "h.db"))
    store.migrate()
    src = {"id": "src-1", "name": "BIS", "url": "https://bis.org",
           "source_type": "regulator", "authority_score": 10, "topics": "",
           "active": True}
    src.update(over)
    store.upsert_source(src)
    return store


def _outcome(**over):
    row = {"source_id": "src-1", "status": "ok", "via": "feed", "http_status": 200,
           "new": 3, "duplicates": 1, "detail": "3 new item(s)"}
    row.update(over)
    return row


def test_a_silent_source_is_recorded_not_lost(tmp_path):
    """fetch_state only holds items. A run that produced none left no trace, so a
    403 and a quiet week were indistinguishable."""
    store = _store_with_source(tmp_path)
    store.log_fetch_outcome("2026-10-13T06:00:00+00:00",
                            [_outcome(status="blocked", new=0, http_status=403,
                                      detail="HTTP 403")])
    health = store.source_health()
    assert len(health) == 1
    assert health[0]["status"] == "blocked"
    assert health[0]["http_status"] == 403
    assert health[0]["new_items"] == 0


def test_health_joins_the_registry_so_type_is_available(tmp_path):
    store = _store_with_source(tmp_path)
    store.log_fetch_outcome("2026-10-13T06:00:00+00:00", [_outcome()])
    row = store.source_health()[0]
    assert row["source_type"] == "regulator" and row["source_name"] == "BIS"
    assert row["authority_score"] == 10


def test_health_returns_the_latest_run_by_default(tmp_path):
    store = _store_with_source(tmp_path)
    store.log_fetch_outcome("2026-10-12T06:00:00+00:00", [_outcome(status="no_feed")])
    store.log_fetch_outcome("2026-10-13T06:00:00+00:00", [_outcome(status="ok")])
    assert store.source_health()[0]["status"] == "ok"
    old = store.source_health("2026-10-12T06:00:00+00:00")
    assert old[0]["status"] == "no_feed", "an earlier run stays queryable"


def test_an_unsynced_registry_row_is_skipped_not_an_fk_error(tmp_path):
    """The log references sources(id). A registry row never synced is a registry
    problem, and must not abort the run's logging."""
    store = _store_with_source(tmp_path)
    logged = store.log_fetch_outcome(
        "2026-10-13T06:00:00+00:00",
        [_outcome(), _outcome(source_id="src-never-synced")])
    assert logged == 1
    assert len(store.source_health()) == 1


def test_a_missing_status_is_recorded_as_error_not_null(tmp_path):
    store = _store_with_source(tmp_path)
    store.log_fetch_outcome("2026-10-13T06:00:00+00:00", [_outcome(status=None)])
    assert store.source_health()[0]["status"] == "error"


def test_long_detail_is_truncated_not_rejected(tmp_path):
    store = _store_with_source(tmp_path)
    store.log_fetch_outcome("2026-10-13T06:00:00+00:00",
                            [_outcome(detail="x" * 900)])
    assert len(store.source_health()[0]["detail"]) == 400


def test_logging_nothing_is_not_an_error(tmp_path):
    store = _store_with_source(tmp_path)
    assert store.log_fetch_outcome("2026-10-13T06:00:00+00:00", []) == 0
    assert store.source_health() == []


def test_purging_an_item_must_not_leave_it_in_the_seen_set(tmp_path):
    """fetch_state is the section 10.2 "already seen" set. A purged URL left in it
    can never be re-ingested, so purging something legitimate excludes it
    permanently and silently -- worse than the contamination being removed."""
    store = _store_with_source(tmp_path)
    url = "https://bis.org/news/real-article"
    store.record_fetch("src-1", url, "hash-1", "2026-10-13T06:00:00+00:00")
    assert url in store.seen_urls("src-1")
    store.conn.execute("DELETE FROM fetch_state WHERE item_url = ?", (url,))
    store.conn.commit()
    assert url not in store.seen_urls("src-1"), "it can be fetched again"


# --- re-running the pipeline ---------------------------------------------------

def _narrative_payload(nid="n1", content_id="c1"):
    return [{"id": nid, "name": "stablecoin rails", "status": "emerging",
             "members": [(content_id, 0.4)]}]


def _with_content(tmp_path):
    store = _store_with_source(tmp_path)
    store.conn.execute(
        "INSERT INTO content_items (id, source_id, url, title, content_hash,"
        " retrieved_at) VALUES (?,?,?,?,?,?)",
        ("c1", "src-1", "https://bis.org/news/a", "A", "h1",
         "2026-10-13T00:00:00+00:00"))
    store.conn.commit()
    return store


def test_re_clustering_succeeds_when_opportunities_already_exist(tmp_path):
    """Clustering is not incremental, so yesterday's opportunity points at a
    narrative about to stop existing. Deleting narratives with those rows present
    raised FOREIGN KEY constraint failed after the clustering work was done, and a
    full run lost 148 narratives. A daily agent must be re-runnable."""
    store = _with_content(tmp_path)
    store.replace_narratives(_narrative_payload())
    store.conn.execute("INSERT INTO opportunities (id, narrative_id) VALUES (?,?)",
                       ("o1", "n1"))
    store.conn.execute(
        "INSERT INTO qa_reviews (opportunity_id, ai_decision) VALUES (?,?)",
        ("o1", "REJECT"))
    store.conn.commit()

    store.replace_narratives(_narrative_payload(nid="n2"))      # must not raise

    assert [r["id"] for r in store.conn.execute("SELECT id FROM narratives")] == ["n2"]
    assert store.conn.execute("SELECT COUNT(*) FROM opportunities").fetchone()[0] == 0
    assert store.conn.execute("SELECT COUNT(*) FROM qa_reviews").fetchone()[0] == 0


def test_re_clustering_keeps_the_content_items(tmp_path):
    """Items are the corpus; narratives are a derived view of it."""
    store = _with_content(tmp_path)
    store.replace_narratives(_narrative_payload())
    store.replace_narratives(_narrative_payload(nid="n2"))
    assert store.conn.execute("SELECT COUNT(*) FROM content_items").fetchone()[0] == 1


def test_narrative_members_are_rewritten_not_appended(tmp_path):
    store = _with_content(tmp_path)
    store.replace_narratives(_narrative_payload())
    store.replace_narratives(_narrative_payload(nid="n2"))
    rows = store.conn.execute("SELECT narrative_id FROM narrative_items").fetchall()
    assert [r["narrative_id"] for r in rows] == ["n2"]


# --- telling an environment fault from a publisher's --------------------------

def _health_rows(error_count, ok_count, detail="ConnectError: [SSL] verify failed"):
    rows = [{"status": "error", "detail": detail} for _ in range(error_count)]
    rows += [{"status": "ok", "detail": "3 new item(s)"} for _ in range(ok_count)]
    return rows


def _fault(rows):
    import importlib.util
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    spec = importlib.util.spec_from_file_location(
        "source_health", os.path.join(root, "scripts", "source_health.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.environment_fault(rows)


def test_one_shared_failure_across_most_of_a_run_is_ours_not_theirs():
    """A run during an office-network change recorded 76 of 98 sources as `error`
    with the same SSL verification failure, and the same sources verified cleanly
    minutes later. Written into the health report, that sends someone chasing
    listing rules for sources that were never broken."""
    got = _fault(_health_rows(76, 29))
    assert got is not None
    assert got[1] == 76


def test_a_few_scattered_failures_are_not_an_environment_fault():
    assert _fault(_health_rows(3, 100)) is None


def test_failures_with_different_causes_are_not_one_fault():
    rows = [{"status": "error", "detail": f"Cause{i}: something"} for i in range(50)]
    rows += [{"status": "ok", "detail": ""} for _ in range(50)]
    assert _fault(rows) is None


def test_an_empty_run_reports_nothing():
    assert _fault([]) is None


def test_a_healthy_run_reports_nothing():
    assert _fault(_health_rows(0, 100)) is None
