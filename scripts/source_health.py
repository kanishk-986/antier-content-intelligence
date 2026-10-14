"""Source health and corpus independence, from the ingestion log.

Answers two questions the item table alone cannot:

  1. Why did a source yield nothing? A 403, a JavaScript-rendered listing and a
     genuinely quiet week are indistinguishable in a corpus, and only the third is
     acceptable. `source_fetch_log` keeps the answer per run.
  2. Is the corpus independent? A corpus of vendor press releases can look healthy
     on volume and support no claim at all.

    python3 scripts/source_health.py
    python3 scripts/source_health.py --actionable    # only what is worth fixing
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

from src.database.sqlite_store import SqliteStore
from src.ingestion.status import ACTIONABLE, environment_fault, guidance
from src.narratives.momentum import load_independence


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="data/aci.db")
    ap.add_argument("--run", help="a specific run_at; default is the latest")
    ap.add_argument("--actionable", action="store_true",
                    help="list only sources whose failure we can fix")
    args = ap.parse_args()

    store = SqliteStore(args.db)
    rows = store.source_health(args.run)
    if not rows:
        print("No fetch log. Run scripts/run_ingestion.py first.", file=sys.stderr)
        return 1

    party = load_independence()["primary_party_types"]
    run_at = rows[0]["run_at"]
    print(f"source health for run {run_at}  ({len(rows)} sources)\n")

    # Lead with this. Every number below is computed from the same run, so a
    # reader who meets the caveat after the figures has already believed them.
    fault = environment_fault(rows)
    if fault:
        signature, count = fault
        print(f"  ENVIRONMENT FAULT: {count} of {len(rows)} sources failed with "
              f"the same error —\n    {signature}\n"
              "  One shared failure across most of a run is this machine's network,"
              "\n  not those publishers. Every figure below is from that run and is"
              "\n  therefore unreliable. Re-run on a stable connection before"
              " acting on it.\n")

    # --- yield by source type, split on independence ------------------------
    buckets: dict[str, dict[str, int]] = {}
    for r in rows:
        b = buckets.setdefault(r["source_type"], {"n": 0, "ok": 0, "items": 0})
        b["n"] += 1
        b["items"] += r["new_items"]
        if r["status"] == "ok":
            b["ok"] += 1

    print(f"  {'source_type':18} {'sources':>7} {'yielding':>8} {'items':>6}  role")
    ind_items = ind_n = 0
    for stype, b in sorted(buckets.items(), key=lambda kv: -kv[1]["items"]):
        role = "primary party" if stype in party else "INDEPENDENT"
        if stype not in party:
            ind_items += b["items"]
            ind_n += b["n"]
        print(f"  {stype:18} {b['n']:>7} {b['ok']:>8} {b['items']:>6}  {role}")

    total = sum(b["items"] for b in buckets.values())
    if total:
        share = 100 * ind_items / total
        print(f"\n  independent items: {ind_items}/{total} = {share:.0f}%")
        if share < 50 and not fault:
            print("  ^ a corpus this self-reported cannot support a claim. "
                  "See SCORING.md, 'Authority is not corroboration'.")
        elif share < 50:
            print("  ^ not a conclusion: this run's independent sources were the "
                  "ones that failed.")
    print(f"  independent sources in registry: {ind_n}/{len(rows)}")

    # --- why the silent ones were silent ------------------------------------
    silent = [r for r in rows if r["status"] != "ok"]
    by_status: dict[str, list[dict]] = {}
    for r in silent:
        by_status.setdefault(r["status"], []).append(r)

    print(f"\n  {len(silent)} of {len(rows)} sources yielded nothing:")
    for status, group in sorted(by_status.items(), key=lambda kv: -len(kv[1])):
        try:
            note = guidance(status)
        except KeyError as exc:
            # A status nobody classified would otherwise print an empty
            # recommendation and read as "nothing to do".
            note = f"UNCLASSIFIED — {exc.args[0].split('.')[0]}"
        ind = sum(1 for r in group if r["source_type"] not in party)
        print(f"    {status:14} {len(group):>3}  ({ind} independent)  {note}")

    fixable = [r for r in silent if r["status"] in ACTIONABLE]
    independent_fixable = [r for r in fixable if r["source_type"] not in party]
    print(f"\n  {len(fixable)} fixable, {len(independent_fixable)} of them independent"
          " — these are the ones that change the corpus")

    listed = independent_fixable if args.actionable else fixable
    if listed:
        print()
        width = min(40, max(len(r["source_name"]) for r in listed))
        for r in sorted(listed, key=lambda r: -r["authority_score"]):
            print("  %-*s  auth=%-3s %-14s %-16s %s" % (
                width, r["source_name"][:width], r["authority_score"],
                r["source_type"], r["status"], (r["detail"] or "")[:52]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
