"""Run the ingestion stage.

    python3 scripts/run_ingestion.py --limit 10          # top 10 sources by authority
    python3 scripts/run_ingestion.py --limit 10 --no-bodies   # feed metadata only
    python3 scripts/run_ingestion.py                     # whole registry

Section 40's vertical slice starts with 10 test sources; --limit is that knob.
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.database.sqlite_store import SqliteStore, utcnow
from src.ingestion.pipeline import ingest, load_registry, sync_registry


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="data/aci.db")
    ap.add_argument("--limit", type=int, help="first N sources by authority")
    ap.add_argument("--max-items", type=int, default=20, help="per source")
    ap.add_argument("--no-bodies", action="store_true",
                    help="skip article downloads; feed metadata only")
    ap.add_argument("--no-listing", action="store_true",
                    help="feeds only; skip the phase 3b listing fallback")
    args = ap.parse_args()

    store = SqliteStore(args.db)
    store.migrate()

    sources = load_registry()
    sync_registry(store, sources)
    if args.limit:
        sources = sources[: args.limit]

    print(f"ingesting {len(sources)} source(s) -> {args.db}\n")
    report = ingest(store, sources, max_items=args.max_items,
                    fetch_bodies=not args.no_bodies,
                    use_listing=not args.no_listing)

    width = max(len(r["source_name"]) for r in report.per_source)
    for row in report.per_source:
        print("  %-*s  %-8s %-13s new=%-3d dup=%-3d %s" % (
            width, row["source_name"][:width], row.get("via", "-"), row["status"],
            row["new"], row["duplicates"], row["detail"][:52]))

    # SOURCE_POLICY.md: a source that yields nothing is a coverage fact and has to
    # survive the run. Without this, "why did 85 of 105 sources yield nothing" can
    # only be answered by probing all of them again.
    run_at = utcnow()
    logged = store.log_fetch_outcome(run_at, report.per_source)
    print(f"\n  logged {logged} source outcome(s) at {run_at}")

    print(f"  attempted {report.attempted} | stored {report.stored} | "
          f"duplicates {report.duplicates}")
    print("  by status: " + ", ".join(f"{k}={v}" for k, v in
                                      sorted(report.by_status().items())))
    print("  db counts: " + ", ".join(f"{k}={v}" for k, v in store.counts().items()
                                      if v))
    store.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
