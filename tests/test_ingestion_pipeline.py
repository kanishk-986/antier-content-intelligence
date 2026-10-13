"""Pipeline wiring. Offline: registry parsing and the blocked-source guard."""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.database.sqlite_store import SqliteStore
from src.ingestion.pipeline import ingest, load_registry, sync_registry

HEADER = ("source_id,source_name,url,source_type,category,authority_score,"
          "crawl_frequency,region,topics,personas,active,last_seen_at,notes\n")


def write_registry(rows):
    fd, path = tempfile.mkstemp(suffix=".csv")
    with os.fdopen(fd, "w") as fh:
        fh.write(HEADER)
        fh.writelines(rows)
    return path


def test_real_registry_loads_and_is_non_empty():
    rows = load_registry()
    assert len(rows) > 50
    assert all(r["url"].startswith("http") for r in rows)
    assert all(isinstance(r["authority_score"], int) for r in rows)


def test_inactive_rows_are_skipped():
    path = write_registry([
        "src-001,On,https://a.test,media,generic,8,weekly,global,,,true,,\n",
        "src-002,Off,https://b.test,media,generic,8,weekly,global,,,false,,\n",
    ])
    rows = load_registry(path)
    os.unlink(path)
    assert [r["id"] for r in rows] == ["src-001"]


def test_topics_split_into_a_list():
    path = write_registry([
        'src-001,X,https://a.test,media,generic,8,weekly,global,"rwa, stablecoins",,true,,\n',
    ])
    rows = load_registry(path)
    os.unlink(path)
    assert rows[0]["topics"] == ["rwa", "stablecoins"]


def test_known_blocked_source_is_reported_not_fetched():
    """SOURCE_POLICY.md: a measured bot-block must never read as an empty feed,
    and must not be retried blindly on every run."""
    path = write_registry([
        "src-001,Dune,https://dune.com/home,data_platform,specific_website,8,"
        "weekly,global,,,true,,BLOCKED HTTP 403 as of 2026-10-06\n",
    ])
    sources = load_registry(path)
    os.unlink(path)

    fd, db = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.unlink(db)
    store = SqliteStore(db)
    store.migrate()
    sync_registry(store, sources)
    report = ingest(store, sources)          # no network: the guard short-circuits
    store.close()
    os.unlink(db)

    assert report.attempted == 0, "a known-blocked source must not be attempted"
    assert report.per_source[0]["status"] == "blocked_known"
    assert "403" in report.per_source[0]["detail"]


def test_every_source_appears_in_the_report():
    """Coverage is reported, never assumed."""
    path = write_registry([
        "src-001,A,https://dune.com/home,x,y,8,weekly,global,,,true,,BLOCKED 403\n",
        "src-002,B,https://defillama.com/,x,y,8,weekly,global,,,true,,BLOCKED 403\n",
    ])
    sources = load_registry(path)
    os.unlink(path)
    fd, db = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.unlink(db)
    store = SqliteStore(db)
    store.migrate()
    sync_registry(store, sources)
    report = ingest(store, sources)
    store.close()
    os.unlink(db)
    assert len(report.per_source) == len(sources)


# --- progress reporting -------------------------------------------------------

def _blocked(sid, name):
    return {"id": sid, "name": name, "url": f"https://{sid}.test",
            "source_type": "regulator", "authority_score": 9, "topics": "",
            "active": True, "notes": "BLOCKED: measured 403"}


def _tmp_store(sources):
    fd, db = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.unlink(db)
    store = SqliteStore(db)
    store.migrate()
    sync_registry(store, sources)
    return store, db


def test_each_source_is_reported_as_it_completes():
    """A full run fetches bodies from a hundred sites and takes tens of minutes.
    Reporting only at the end makes a slow run indistinguishable from a hung one."""
    sources = [_blocked("s1", "Alpha"), _blocked("s2", "Beta")]
    store, db = _tmp_store(sources)
    seen = []
    ingest(store, sources, use_listing=False,
           on_source=lambda row, done, total: seen.append(
               (row["source_name"], done, total)))
    store.close()
    os.unlink(db)
    assert seen == [("Alpha", 1, 2), ("Beta", 2, 2)]


def test_ingest_works_without_a_progress_callback():
    sources = [_blocked("s1", "Alpha")]
    store, db = _tmp_store(sources)
    report = ingest(store, sources, use_listing=False)
    store.close()
    os.unlink(db)
    assert len(report.per_source) == 1
