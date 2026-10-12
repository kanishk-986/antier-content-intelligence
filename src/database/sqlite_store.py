"""SQLite implementation of Store.

The section 9 schema verbatim. Chosen for the section 40 vertical slice because
Postgres, pgvector and Docker are absent from the build machine and installing them
before any pipeline code exists inverts the blueprint's own instruction to validate
the architecture first. See ARCHITECTURE.md for the deviation record.
"""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from typing import Any

MIGRATIONS = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "migrations",
)

JSON_FIELDS = {"topics", "entities", "claims", "metadata", "embedding"}


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _encode(value: Any) -> Any:
    if isinstance(value, (list, dict)):
        return json.dumps(value, sort_keys=True)
    return value


class SqliteStore:
    def __init__(self, path: str = "data/aci.db"):
        self.path = path
        parent = os.path.dirname(os.path.abspath(path))
        if parent:
            os.makedirs(parent, exist_ok=True)
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")

    # --- lifecycle -------------------------------------------------------------
    def migrate(self) -> None:
        for name in sorted(os.listdir(MIGRATIONS)):
            if name.endswith(".sql"):
                with open(os.path.join(MIGRATIONS, name)) as fh:
                    self.conn.executescript(fh.read())
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    # --- sources ---------------------------------------------------------------
    def upsert_source(self, source: dict[str, Any]) -> None:
        self.conn.execute(
            """
            INSERT INTO sources (id, name, url, source_type, authority_score, topics, active)
            VALUES (:id, :name, :url, :source_type, :authority_score, :topics, :active)
            ON CONFLICT(id) DO UPDATE SET
                name=excluded.name, url=excluded.url,
                source_type=excluded.source_type,
                authority_score=excluded.authority_score,
                topics=excluded.topics, active=excluded.active
            """,
            {
                "id": source["id"],
                "name": source["name"],
                "url": source["url"],
                "source_type": source.get("source_type"),
                "authority_score": int(source["authority_score"]),
                "topics": _encode(source.get("topics")),
                "active": 1 if source.get("active", True) else 0,
            },
        )
        self.conn.commit()

    def active_sources(self) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM sources WHERE active = 1 "
            "ORDER BY authority_score DESC, name COLLATE NOCASE"
        ).fetchall()
        return [dict(r) for r in rows]

    def mark_source_checked(self, source_id: str, when: str,
                            last_item_at: str | None = None) -> None:
        if last_item_at:
            self.conn.execute(
                "UPDATE sources SET last_checked_at=?, last_item_at=? WHERE id=?",
                (when, last_item_at, source_id),
            )
        else:
            self.conn.execute(
                "UPDATE sources SET last_checked_at=? WHERE id=?", (when, source_id)
            )
        self.conn.commit()

    # --- content ---------------------------------------------------------------
    def content_hash_exists(self, content_hash: str) -> bool:
        row = self.conn.execute(
            "SELECT 1 FROM content_items WHERE content_hash=? LIMIT 1", (content_hash,)
        ).fetchone()
        return row is not None

    def seen_urls(self, source_id: str) -> set[str]:
        rows = self.conn.execute(
            "SELECT item_url FROM fetch_state WHERE source_id=?", (source_id,)
        ).fetchall()
        return {r["item_url"] for r in rows}

    def insert_content(self, item: dict[str, Any]) -> bool:
        payload = {
            "id": item["id"],
            "source_id": item["source_id"],
            "url": item["url"],
            "title": item.get("title"),
            "author": item.get("author"),
            "published_at": item.get("published_at"),
            "retrieved_at": item.get("retrieved_at") or utcnow(),
            "raw_text": item.get("raw_text"),
            "clean_text": item.get("clean_text"),
            "content_hash": item["content_hash"],
            "language": item.get("language"),
            "metadata": _encode(item.get("metadata")),
        }
        try:
            self.conn.execute(
                """
                INSERT INTO content_items
                  (id, source_id, url, title, author, published_at, retrieved_at,
                   raw_text, clean_text, content_hash, language, metadata)
                VALUES
                  (:id, :source_id, :url, :title, :author, :published_at, :retrieved_at,
                   :raw_text, :clean_text, :content_hash, :language, :metadata)
                """,
                payload,
            )
            self.conn.commit()
            return True
        except sqlite3.IntegrityError as exc:
            # Only the content_hash uniqueness conflict means "duplicate" -- that is
            # the expected section 10.2 outcome for a syndicated story. Anything else
            # (a dangling source_id, a missing NOT NULL) is a programming error and
            # must surface, not be silently reported as a duplicate.
            if "content_items.content_hash" in str(exc) or "content_hash" in str(exc):
                return False
            raise

    def content_items(self, since: str | None = None,
                      limit: int | None = None) -> list[dict[str, Any]]:
        sql = "SELECT * FROM content_items"
        params: list[Any] = []
        if since:
            sql += " WHERE retrieved_at >= ?"
            params.append(since)
        sql += " ORDER BY retrieved_at DESC"
        if limit:
            sql += " LIMIT ?"
            params.append(limit)
        return [dict(r) for r in self.conn.execute(sql, params).fetchall()]

    def record_fetch(self, source_id: str, item_url: str, content_hash: str | None,
                     when: str, etag: str | None = None,
                     last_modified: str | None = None) -> None:
        self.conn.execute(
            """
            INSERT INTO fetch_state
              (source_id, item_url, content_hash, seen_at, etag, last_modified)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(source_id, item_url) DO UPDATE SET
              content_hash=excluded.content_hash, seen_at=excluded.seen_at,
              etag=excluded.etag, last_modified=excluded.last_modified
            """,
            (source_id, item_url, content_hash, when, etag, last_modified),
        )
        self.conn.commit()

    # --- audit -----------------------------------------------------------------
    def audit(self, actor: str, action: str, object_ref: str | None = None,
              detail: str | None = None) -> None:
        self.conn.execute(
            "INSERT INTO audit_log (at, actor, action, object_ref, detail) "
            "VALUES (?, ?, ?, ?, ?)",
            (utcnow(), actor, action, object_ref, detail),
        )
        self.conn.commit()

    # --- counts ----------------------------------------------------------------
    def counts(self) -> dict[str, int]:
        tables = [
            "sources", "content_items", "intelligence", "narratives",
            "narrative_items", "opportunities", "qa_reviews", "audit_log",
            "fetch_state",
        ]
        out = {}
        for t in tables:
            out[t] = self.conn.execute(f"SELECT COUNT(*) AS n FROM {t}").fetchone()["n"]
        return out
