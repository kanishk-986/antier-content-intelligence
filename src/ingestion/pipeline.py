"""Ingestion pipeline: registry -> fetch -> normalize -> deduplicate -> store.

Section 6 stage [1]. Section 10: this stage discovers and normalizes only. It makes
no judgement about Antier relevance.

Coverage is reported per source, including sources that yielded nothing and sources
that could not be read -- a silent gap reads as "nothing happened" (SOURCE_POLICY.md).
"""

from __future__ import annotations

import csv
import json
import os
import uuid
from dataclasses import dataclass, field

from src.database.sqlite_store import SqliteStore, utcnow
from src.ingestion.fetcher import fetch_source

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
REGISTRY = os.path.join(REPO, "config", "sources", "source_registry.csv")


@dataclass
class IngestionReport:
    attempted: int = 0
    stored: int = 0
    duplicates: int = 0
    per_source: list[dict] = field(default_factory=list)

    def by_status(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for row in self.per_source:
            out[row["status"]] = out.get(row["status"], 0) + 1
        return out


def load_registry(path: str = REGISTRY) -> list[dict]:
    """Read the configured source universe. Configuration, not code (section 41.1)."""
    with open(path) as fh:
        rows = list(csv.DictReader(fh))
    out = []
    for row in rows:
        if row.get("active", "true").lower() != "true":
            continue
        out.append({
            "id": row["source_id"],
            "name": row["source_name"],
            "url": row["url"],
            "source_type": row.get("source_type"),
            "authority_score": int(row["authority_score"]),
            "topics": [t.strip() for t in (row.get("topics") or "").split(",") if t.strip()],
            "active": True,
            "notes": row.get("notes", ""),
        })
    return out


def sync_registry(store: SqliteStore, sources: list[dict]) -> None:
    for source in sources:
        store.upsert_source(source)
    store.audit("system", "registry_synced", detail=f"{len(sources)} sources")


def ingest(store: SqliteStore, sources: list[dict], max_items: int = 20,
           fetch_bodies: bool = True) -> IngestionReport:
    report = IngestionReport()

    for source in sources:
        notes = source.get("notes", "")
        # SOURCE_POLICY.md: a measured bot-block is reported, not retried blindly.
        if "BLOCKED" in notes:
            report.per_source.append({
                "source_id": source["id"], "source_name": source["name"],
                "status": "blocked_known", "new": 0, "duplicates": 0,
                "detail": notes.split(";")[0].strip(),
            })
            continue

        report.attempted += 1
        seen = store.seen_urls(source["id"])
        outcome = fetch_source(source, seen, max_items=max_items,
                               fetch_bodies=fetch_bodies)

        new_count, dupe_count = 0, 0
        for item in outcome.items:
            store.record_fetch(source["id"], item["url"], item["content_hash"],
                               utcnow())
            if store.content_hash_exists(item["content_hash"]):
                dupe_count += 1
                continue
            item["id"] = str(uuid.uuid4())
            if store.insert_content(item):
                new_count += 1
            else:
                dupe_count += 1

        newest = max((i["published_at"] or "" for i in outcome.items), default="")
        store.mark_source_checked(source["id"], utcnow(), newest or None)
        report.stored += new_count
        report.duplicates += dupe_count
        report.per_source.append({
            "source_id": source["id"], "source_name": source["name"],
            "status": outcome.status, "new": new_count, "duplicates": dupe_count,
            "detail": outcome.detail, "http_status": outcome.http_status,
        })

    store.audit(
        "system", "ingestion_run",
        detail=json.dumps({"attempted": report.attempted, "stored": report.stored,
                           "duplicates": report.duplicates}),
    )
    return report
