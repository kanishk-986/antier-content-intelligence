"""Score stored narratives into section 9.5 opportunities.

    python3 scripts/run_scoring.py                 # score, persist, report
    python3 scripts/run_scoring.py --min-score 5   # hide rejects
    python3 scripts/run_scoring.py --dry-run       # report without writing

No model is called: section 15 is deterministic arithmetic over stored narratives,
momentum and intelligence (CLAUDE.md rule 7). Re-running after extraction changes the
score, and says which dimensions were still unmeasured.
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
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import yaml

from src.database.sqlite_store import SqliteStore
from src.scoring import weights as wcfg
from src.scoring.opportunity import persist, score_all

BRAND = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     "config", "brand", "antier.yaml")


def load_proof_points():
    with open(BRAND) as fh:
        return (yaml.safe_load(fh) or {}).get("proof_points") or []


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="data/aci.db")
    ap.add_argument("--min-score", type=float, default=0.0)
    ap.add_argument("--top", type=int, default=15)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    try:
        config = wcfg.load()
    except wcfg.ConfigError as exc:
        print("scoring config invalid: %s" % exc, file=sys.stderr)
        return 1
    services = wcfg.load_services()
    proof_points = load_proof_points()

    store = SqliteStore(args.db)
    store.migrate()
    narratives = store.narratives()
    if not narratives:
        print("No narratives. Run scripts/run_narratives.py first.", file=sys.stderr)
        store.close()
        return 1

    intel = {}
    for item in store.content_items():
        row = store.intelligence_for(item["id"])
        if row:
            intel[item["id"]] = row
    opportunities = [o for o, _ in score_all(store, config, services, proof_points)]

    print("%d narrative(s) scored | weights v%d | %d/%d items have intelligence\n"
          % (len(opportunities), config.version, len(intel),
             len(store.content_items())))

    shown = [o for o in opportunities if o.score_0_10 >= args.min_score][: args.top]
    for o in shown:
        rank = ("svc %d" % o.service_rank) if o.service_rank else "no svc"
        print("  %5.2f  %-20s %-7s  %s" % (o.score_0_10, o.band, rank,
                                           o.narrative_name[:46]))
        parts = ["%s=%.2f" % (k[:4], v.value) for k, v in o.dimensions.items()]
        print("         %s" % "  ".join(parts))
        if o.unmeasured:
            print("         unmeasured: %s" % ", ".join(o.unmeasured))

    bands = {}
    for o in opportunities:
        bands[o.band] = bands.get(o.band, 0) + 1
    print("\n  bands: %s" % ", ".join("%s=%d" % kv for kv in sorted(bands.items())))
    print("  competitor saturation axis: %s (section 32 defers it; never read as 0)"
          % config.saturation.get("competitor_axis"))

    if not args.dry_run:
        persist(store, opportunities)
        store.audit("system", "opportunities_scored",
                    detail="%d scored, weights v%d" % (len(opportunities),
                                                       config.version))
        print("  persisted %d opportunities" % len(opportunities))
    store.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
