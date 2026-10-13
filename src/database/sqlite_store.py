"""SQLite implementation of Store.

The section 9 schema verbatim. Chosen for the section 40 vertical slice because
Postgres, pgvector and Docker are absent from the build machine and installing them
before any pipeline code exists inverts the blueprint's own instruction to validate
the architecture first. See ARCHITECTURE.md for the deviation record.
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
from datetime import datetime, timezone
from typing import Any

MIGRATIONS = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "migrations",
)

JSON_FIELDS = {"topics", "entities", "claims", "metadata", "embedding"}

_ADD_COLUMN = re.compile(
    r"^\s*ALTER\s+TABLE\s+(\w+)\s+ADD\s+COLUMN\s+(\w+)", re.IGNORECASE
)


def _strip_leading_comments(statement: str) -> str:
    """Drop leading `--` comment lines.

    A statement split from a migration carries the comment block above it, so an
    anchored match on ALTER would miss -- which is exactly how the ADD COLUMN guard
    was silently skipped the first time.
    """
    lines = statement.splitlines()
    while lines and (not lines[0].strip() or lines[0].lstrip().startswith("--")):
        lines.pop(0)
    return "\n".join(lines).strip()


def _statements(script: str) -> list[str]:
    """Split a migration into complete SQL statements.

    Uses sqlite3.complete_statement so comments and string literals containing a
    semicolon do not split a statement in half.
    """
    out, buf = [], ""
    for line in script.splitlines(keepends=True):
        buf += line
        if sqlite3.complete_statement(buf):
            if buf.strip():
                out.append(buf.strip())
            buf = ""
    if buf.strip():
        out.append(buf.strip())
    return out


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
    def _columns(self, table: str) -> set[str]:
        return {r[1] for r in self.conn.execute(f"PRAGMA table_info({table})")}

    def migrate(self) -> None:
        """Apply every migration in order. Idempotent.

        Statements are split with sqlite3's own parser rather than on semicolons --
        a naive split mangles the DDL comments in 001.

        SQLite has no `ADD COLUMN IF NOT EXISTS`, so such statements are guarded by
        checking the live schema first. Catching "duplicate column name" instead
        would be wrong: if one ALTER in a file had already succeeded, aborting the
        file would leave the rest permanently unapplied.
        """
        for name in sorted(os.listdir(MIGRATIONS)):
            if not name.endswith(".sql"):
                continue
            with open(os.path.join(MIGRATIONS, name)) as fh:
                script = fh.read()
            for statement in _statements(script):
                add = _ADD_COLUMN.match(_strip_leading_comments(statement))
                if add:
                    table, column = add.group(1), add.group(2)
                    if column in self._columns(table):
                        continue
                self.conn.execute(statement)
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

    # --- intelligence ----------------------------------------------------------
    def items_without_intelligence(self, limit: int | None = None) -> list[dict[str, Any]]:
        sql = ("SELECT c.* FROM content_items c "
               "LEFT JOIN intelligence i ON i.content_id = c.id "
               "WHERE i.content_id IS NULL "
               "ORDER BY c.published_at DESC, c.retrieved_at DESC")
        params: list[Any] = []
        if limit:
            sql += " LIMIT ?"
            params.append(limit)
        return [dict(r) for r in self.conn.execute(sql, params).fetchall()]

    def insert_intelligence(self, content_id: str, record: dict[str, Any],
                            prompt_version: str, model: str) -> None:
        sentiment = record["sentiment"]
        self.conn.execute(
            """
            INSERT INTO intelligence
              (content_id, entities, topics, claims, market_sentiment,
               institutional_sentiment, developer_sentiment, regulatory_sentiment,
               enterprise_sentiment, community_sentiment, importance_score,
               prompt_version, extracted_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(content_id) DO UPDATE SET
               entities=excluded.entities, topics=excluded.topics,
               claims=excluded.claims, market_sentiment=excluded.market_sentiment,
               institutional_sentiment=excluded.institutional_sentiment,
               developer_sentiment=excluded.developer_sentiment,
               regulatory_sentiment=excluded.regulatory_sentiment,
               enterprise_sentiment=excluded.enterprise_sentiment,
               community_sentiment=excluded.community_sentiment,
               importance_score=excluded.importance_score,
               prompt_version=excluded.prompt_version,
               extracted_at=excluded.extracted_at
            """,
            (
                content_id,
                _encode(record["entities"]),
                _encode([record["primary_topic"], *record["secondary_topics"]]),
                _encode(record["claims"]),
                sentiment["market"], sentiment["institutional"],
                sentiment["developer"], sentiment["regulatory"],
                sentiment["enterprise"], sentiment["community"],
                record["importance"],
                "%s@%s" % (prompt_version, model),
                utcnow(),
            ),
        )
        self.conn.commit()

    def intelligence_for(self, content_id: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            "SELECT * FROM intelligence WHERE content_id = ?", (content_id,)
        ).fetchone()
        return dict(row) if row else None

    # --- narratives ------------------------------------------------------------
    def replace_narratives(self, narratives: list[dict[str, Any]]) -> None:
        self.conn.execute("DELETE FROM narrative_items")
        self.conn.execute("DELETE FROM narratives")
        for n in narratives:
            self.conn.execute(
                """
                INSERT INTO narratives
                  (id, name, description, embedding, first_seen_at, last_seen_at,
                   velocity, acceleration, saturation, status, baseline_rule)
                VALUES (:id, :name, :description, :embedding, :first_seen_at,
                        :last_seen_at, :velocity, :acceleration, :saturation,
                        :status, :baseline_rule)
                """,
                {
                    "id": n["id"], "name": n["name"],
                    "description": n.get("description"),
                    "embedding": _encode(n.get("embedding")),
                    "first_seen_at": n.get("first_seen_at"),
                    "last_seen_at": n.get("last_seen_at"),
                    "velocity": n.get("velocity"),
                    "acceleration": n.get("acceleration"),
                    "saturation": n.get("saturation"),
                    "status": n.get("status"),
                    "baseline_rule": n.get("baseline_rule"),
                },
            )
            for content_id, sim in n.get("members", []):
                self.conn.execute(
                    "INSERT INTO narrative_items (narrative_id, content_id, similarity)"
                    " VALUES (?, ?, ?)",
                    (n["id"], content_id, sim),
                )
        self.conn.commit()

    def narratives(self) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT n.*, COUNT(ni.content_id) AS item_count FROM narratives n "
            "LEFT JOIN narrative_items ni ON ni.narrative_id = n.id "
            "GROUP BY n.id ORDER BY item_count DESC, n.name"
        ).fetchall()
        return [dict(r) for r in rows]

    def narrative_items(self, narrative_id: str) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT c.* FROM content_items c "
            "JOIN narrative_items ni ON ni.content_id = c.id "
            "WHERE ni.narrative_id = ? ORDER BY c.published_at DESC",
            (narrative_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def source_authority(self) -> dict[str, int]:
        rows = self.conn.execute("SELECT id, authority_score FROM sources").fetchall()
        return {r["id"]: r["authority_score"] for r in rows}

    # --- qa reviews ------------------------------------------------------------
    def insert_qa_review(self, row: dict[str, Any]) -> None:
        """Append a review. Never updates: section 33 wants an audit trail, so an AI
        decision and a later human override both survive as separate rows."""
        cols = ", ".join(row)
        marks = ", ".join(":" + k for k in row)
        self.conn.execute(
            f"INSERT INTO qa_reviews ({cols}, created_at) "
            f"VALUES ({marks}, datetime('now'))", row)
        self.conn.commit()

    def qa_reviews(self, opportunity_id: str | None = None) -> list[dict[str, Any]]:
        sql = "SELECT * FROM qa_reviews"
        params: list[Any] = []
        if opportunity_id:
            sql += " WHERE opportunity_id = ?"
            params.append(opportunity_id)
        sql += " ORDER BY id DESC"
        return [dict(r) for r in self.conn.execute(sql, params).fetchall()]

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
