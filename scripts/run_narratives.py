"""Cluster stored content into narratives and score momentum.

    python3 scripts/run_narratives.py                  # cluster + persist + report
    python3 scripts/run_narratives.py --threshold 0.35 # tighter clusters
    python3 scripts/run_narratives.py --dry-run        # report without writing

Section 12: 100 items should become 10-20 narratives, not a ranked article list.
"""

import argparse
import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.database.sqlite_store import SqliteStore, utcnow
from src.narratives import momentum as mom
from src.narratives.cluster import DEFAULT_THRESHOLD, cluster_items, shared_terms
from src.narratives.similarity import TfidfSimilarity


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="data/aci.db")
    ap.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD)
    ap.add_argument("--min-size", type=int, default=1,
                    help="only report narratives with at least N items")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    store = SqliteStore(args.db)
    store.migrate()
    items = store.content_items()
    if not items:
        print("No content items. Run scripts/run_ingestion.py first.", file=sys.stderr)
        return 1

    authority = store.source_authority()
    source_types = store.source_types()
    similarity = TfidfSimilarity()
    narratives = cluster_items(items, similarity, threshold=args.threshold)

    print("%d item(s) -> %d narrative(s)  [threshold %.2f, %s]\n"
          % (len(items), len(narratives), args.threshold, similarity.name))

    payload = []
    shown = 0
    for narrative in narratives:
        m = mom.compute(narrative.items, authority, source_types=source_types)
        dates = [i.get("published_at") for i in narrative.items if i.get("published_at")]
        payload.append({
            "id": str(uuid.uuid4()),
            "name": narrative.name,
            "description": narrative.description,
            "embedding": None,
            "first_seen_at": min(dates) if dates else None,
            "last_seen_at": max(dates) if dates else None,
            "velocity": m.velocity,
            "acceleration": m.acceleration,
            "saturation": None,          # needs competitor data (section 16)
            "status": m.status,
            "baseline_rule": m.baseline_rule,
            "members": [(i["id"], None) for i in narrative.items],
        })
        if narrative.size < args.min_size:
            continue
        shown += 1
        print("  [%2d items] %-9s vel=%-5s auth=%-5s nov=%-5s emrg=%-5s"
              % (narrative.size, m.status, m.velocity, m.authority_coverage,
                 m.novelty, m.emergence))
        print("       terms: %s" % ", ".join(shared_terms(narrative)[:7]))
        print("       srcs : %d distinct | dated %d, undated %d"
              % (len(narrative.source_ids()), m.dated_items, m.undated_items))
        for item in narrative.items[:2]:
            print("       - %s" % (item.get("title") or "(untitled)")[:74])
        print()

    sizes = [n.size for n in narratives]
    multi = [s for s in sizes if s > 1]
    print("  shown %d of %d | multi-item narratives: %d | largest: %d | singletons: %d"
          % (shown, len(narratives), len(multi), max(sizes), sizes.count(1)))

    if not args.dry_run:
        store.replace_narratives(payload)
        store.audit("system", "narratives_clustered",
                    detail="%d items -> %d narratives via %s"
                           % (len(items), len(payload), similarity.name))
        print("  persisted %d narratives at %s" % (len(payload), utcnow()))
    store.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
