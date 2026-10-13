"""Find items the ingestion bugs let in, and optionally remove them.

Code fixes stop new contamination; they do not clean what is already stored, and
`content_hash` dedupe means a re-run will not replace a bad row either. Two defect
signatures are detectable after the fact:

  offsite      an item whose host does not belong to the feed that carried it.
               Richmond Fed's RSS includes DOI and conference-registration links;
               stored as items they are attributed to a publisher that did not
               write them, and they inflate the source diversity section 15 reads
               as corroboration.

  not_editorial an item taken from a listing page that was not an editorial index.
               blackrock.com/corporate/newsroom answered at /corporate/home, whose
               "corporate" segment matched the whole site, so product pages entered
               the corpus -- the marketing content section 2.2 excludes.

    python3 scripts/audit_corpus.py                 # report only
    python3 scripts/audit_corpus.py --purge         # delete, with a summary

Purging is deliberately opt-in and prints every row it will remove first.
"""

import argparse
import json
import os
import sys
from urllib.parse import urlparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.database.sqlite_store import SqliteStore
from src.ingestion.listing import _has_editorial_section, load_rules
from src.ingestion.urls import same_site


def classify(row: dict, stems: list[str]) -> str | None:
    meta = {}
    if row["metadata"]:
        try:
            meta = json.loads(row["metadata"]) or {}
        except (TypeError, ValueError):
            meta = {}
    feed_url = meta.get("feed_url")
    if feed_url:
        return None if same_site(feed_url, row["url"]) else "offsite"
    # No feed_url means the listing extractor produced it.
    return None if _has_editorial_section(row["url"], stems) else "not_editorial"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="data/aci.db")
    ap.add_argument("--purge", action="store_true")
    args = ap.parse_args()

    store = SqliteStore(args.db)
    stems = [s.lower() for s in (load_rules().get("editorial_segments") or [])]
    rows = [dict(r) for r in store.conn.execute(
        "SELECT ci.id, ci.url, ci.title, ci.metadata, ci.source_id, s.name "
        "FROM content_items ci LEFT JOIN sources s ON s.id = ci.source_id")]

    flagged: dict[str, list[dict]] = {}
    for row in rows:
        verdict = classify(row, stems)
        if verdict:
            flagged.setdefault(verdict, []).append(row)

    total = sum(len(v) for v in flagged.values())
    print(f"corpus audit: {len(rows)} item(s), {total} flagged\n")
    for verdict, group in sorted(flagged.items()):
        hosts: dict[str, int] = {}
        for row in group:
            host = urlparse(row["url"]).netloc
            hosts[host] = hosts.get(host, 0) + 1
        print(f"  {verdict}: {len(group)}")
        for host, n in sorted(hosts.items(), key=lambda kv: -kv[1]):
            print(f"      {n:>4}  {host}")
        for row in group[:5]:
            print(f"        e.g. {row['name']} -> {row['url'][:66]}")
        print()

    if not total:
        print("  nothing to purge")
        return 0
    if not args.purge:
        print("  re-run with --purge to delete these rows")
        return 0

    ids = [row["id"] for group in flagged.values() for row in group]
    conn = store.conn
    # narrative_items and intelligence reference content_items; clear them first so
    # the delete cannot fail halfway and leave a half-purged corpus.
    marks = ",".join("?" * len(ids))
    conn.execute(f"DELETE FROM narrative_items WHERE content_id IN ({marks})", ids)
    conn.execute(f"DELETE FROM intelligence WHERE content_id IN ({marks})", ids)
    conn.execute(f"DELETE FROM content_items WHERE id IN ({marks})", ids)
    conn.commit()
    store.audit("system", "corpus_purged",
                detail=json.dumps({k: len(v) for k, v in flagged.items()}))
    print(f"  purged {len(ids)} item(s). Re-run narratives, scoring and QA:")
    print("    python3 scripts/run_narratives.py && python3 scripts/run_scoring.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
