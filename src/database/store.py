"""Storage interface.

Every pipeline stage persists through this. No stage imports a database driver
directly (CLAUDE.md, ARCHITECTURE.md), so moving from SQLite to PostgreSQL +
pgvector is a new implementation of this protocol rather than a rewrite.

Deliberately narrow: the methods here are the ones stages actually need. Adding a
method is a design decision, not a convenience.
"""

from __future__ import annotations

from typing import Any, Protocol


class Store(Protocol):
    # --- lifecycle -------------------------------------------------------------
    def migrate(self) -> None:
        """Apply schema migrations. Idempotent."""

    def close(self) -> None: ...

    # --- sources ---------------------------------------------------------------
    def upsert_source(self, source: dict[str, Any]) -> None:
        """Insert or update one registry row. Keyed on id."""

    def active_sources(self) -> list[dict[str, Any]]:
        """Active sources, highest authority first."""

    def mark_source_checked(self, source_id: str, when: str,
                            last_item_at: str | None = None) -> None:
        """Record a poll. Drives the section 10.2 efficiency rule."""

    # --- content ---------------------------------------------------------------
    def content_hash_exists(self, content_hash: str) -> bool:
        """True if this exact content is already stored (section 10.2 dedupe)."""

    def seen_urls(self, source_id: str) -> set[str]:
        """URLs already fetched for a source, so a re-poll can skip them."""

    def insert_content(self, item: dict[str, Any]) -> bool:
        """Store one item. Returns False if it was a duplicate."""

    def content_items(self, since: str | None = None,
                      limit: int | None = None) -> list[dict[str, Any]]:
        """Stored items, newest retrieved first."""

    def record_fetch(self, source_id: str, item_url: str, content_hash: str | None,
                     when: str, etag: str | None = None,
                     last_modified: str | None = None) -> None:
        """Remember that a URL was seen, duplicate or not."""

    # --- intelligence ----------------------------------------------------------
    def items_without_intelligence(self, limit: int | None = None) -> list[dict[str, Any]]:
        """Content items not yet extracted. The section 10.2 efficiency rule applied
        to the LLM stage: never re-pay for an item already processed."""

    def insert_intelligence(self, content_id: str, record: dict[str, Any],
                            prompt_version: str, model: str) -> None:
        """Store one extracted record."""

    def intelligence_for(self, content_id: str) -> dict[str, Any] | None: ...

    # --- narratives ------------------------------------------------------------
    def replace_narratives(self, narratives: list[dict[str, Any]]) -> None:
        """Write a fresh clustering run, discarding the previous one.

        Clustering is a pure function of the corpus, so a re-run supersedes rather
        than accumulates. Audit history lives in audit_log, not in stale clusters.
        """

    def narratives(self) -> list[dict[str, Any]]:
        """Stored narratives, largest first."""

    def narrative_items(self, narrative_id: str) -> list[dict[str, Any]]:
        """Content items belonging to one narrative."""

    def source_authority(self) -> dict[str, int]:
        """{source_id: authority_score}, for momentum's authority coverage."""

    # --- audit -----------------------------------------------------------------
    def audit(self, actor: str, action: str, object_ref: str | None = None,
              detail: str | None = None) -> None:
        """Append to the section 33 audit trail. Never updates an existing row."""

    # --- counts ----------------------------------------------------------------
    def counts(self) -> dict[str, int]:
        """Row count per table, for runbook and test assertions."""
