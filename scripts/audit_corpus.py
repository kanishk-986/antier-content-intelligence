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

# macOS ships Python 3.9, which cannot parse `str | None` at runtime and has none
# of this project's dependencies. Re-exec into the project venv so `python3
# scripts/x.py` works regardless of which interpreter the shell found first.
import os as _os
import sys as _sys

_VENV = _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))),
                      ".venv", "bin", "python")
if _os.path.exists(_VENV) and _os.path.realpath(_sys.executable) != _os.path.realpath(_VENV):
    _os.execv(_VENV, [_VENV, _os.path.abspath(__file__), *_sys.argv[1:]])

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
    via = (meta.get("via") or "").strip()

    feed_url = meta.get("feed_url")
    if via == "feed" or feed_url:
        return None if same_site(feed_url, row["url"]) else "offsite"

    if via == "sitemap":
        # A sitemap lists the whole site and is not itself an index page, so its
        # URL has no editorial segment -- judging it flags every article that came
        # through this path. 89 real Ondo, Circle and State Street posts were
        # flagged for deletion this way. The editorial test that applies here is
        # the one ingestion already ran: the article's own URL.
        return (None if _has_editorial_section(row["url"], stems)
                else "not_editorial")

    # For a listing item, the question is whether the *index* it came from was an
    # editorial one -- not whether the article's own path looks editorial. A real
    # newsroom links articles under /resources/ and /library/ all the time, and
    # judging the article URL purged legitimate work.
    listing_url = meta.get("listing_url")
    if listing_url:
        return (None if _has_editorial_section(listing_url, stems)
                else "not_editorial")
    return "unverifiable_provenance"


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
        if verdict == "unverifiable_provenance":
            print(f"  {verdict}: {len(group)}  (reported, never purged — these "
                  "predate provenance recording)\n")
            continue
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

    # unverifiable_provenance is reported, never purged: it means the item predates
    # provenance recording, not that it is bad.
    purgeable = {k: v for k, v in flagged.items() if k != "unverifiable_provenance"}
    if not purgeable:
        print("  nothing purgeable; the flagged rows only lack recorded provenance")
        return 0
    ids = [row["id"] for group in purgeable.values() for row in group]
    urls = [row["url"] for group in purgeable.values() for row in group]
    conn = store.conn
    # narrative_items and intelligence reference content_items; clear them first so
    # the delete cannot fail halfway and leave a half-purged corpus.
    marks = ",".join("?" * len(ids))
    conn.execute(f"DELETE FROM narrative_items WHERE content_id IN ({marks})", ids)
    conn.execute(f"DELETE FROM intelligence WHERE content_id IN ({marks})", ids)
    conn.execute(f"DELETE FROM content_items WHERE id IN ({marks})", ids)
    # fetch_state is the section 10.2 "already seen" set. Leaving a purged URL in it
    # means the item can never be re-ingested -- so purging something legitimate
    # would exclude it permanently, and silently. That is worse than the
    # contamination this script exists to remove.
    umarks = ",".join("?" * len(urls))
    conn.execute(f"DELETE FROM fetch_state WHERE item_url IN ({umarks})", urls)
    # A narrative whose every item was contamination is now empty, and an empty
    # narrative still reaches scoring, where it means nothing. My first version of
    # this script left one behind.
    empty = conn.execute(
        "SELECT id FROM narratives n WHERE NOT EXISTS "
        "(SELECT 1 FROM narrative_items ni WHERE ni.narrative_id = n.id)").fetchall()
    if empty:
        empty_ids = [r["id"] for r in empty]
        em = ",".join("?" * len(empty_ids))
        conn.execute(f"DELETE FROM qa_reviews WHERE opportunity_id IN "
                     f"(SELECT id FROM opportunities WHERE narrative_id IN ({em}))",
                     empty_ids)
        conn.execute(f"DELETE FROM opportunities WHERE narrative_id IN ({em})",
                     empty_ids)
        conn.execute(f"DELETE FROM narratives WHERE id IN ({em})", empty_ids)
    conn.commit()
    store.audit("system", "corpus_purged",
                detail=json.dumps({k: len(v) for k, v in flagged.items()}))
    print(f"  purged {len(ids)} item(s)"
          + (f" and {len(empty)} now-empty narrative(s)" if empty else "")
          + ". Re-run narratives, scoring and QA:")
    print("    python3 scripts/run_narratives.py && python3 scripts/run_scoring.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
