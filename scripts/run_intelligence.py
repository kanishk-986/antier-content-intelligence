"""Run section 11 intelligence extraction over un-extracted content items.

    python3 scripts/run_intelligence.py --dry-run        # no API call; validates wiring
    python3 scripts/run_intelligence.py --limit 20       # real extraction, 20 items
    python3 scripts/run_intelligence.py --estimate       # cost/volume estimate only

--dry-run uses a deterministic stub in place of the model, so the prompt, schema,
store writes and the efficiency rule can all be exercised with no key and no network.
It proves the plumbing, not the model's judgement.
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.database.sqlite_store import SqliteStore
from src.intelligence import pipeline
from src.intelligence.extractor import DEFAULT_MODEL, MAX_BODY_CHARS
from src.intelligence.stub import StubLLM


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="data/aci.db")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--dry-run", action="store_true",
                    help="use the deterministic stub; no API call")
    ap.add_argument("--estimate", action="store_true",
                    help="report how many items and roughly how many input tokens")
    ap.add_argument("--keep-speculation", action="store_true",
                    help="store price/token-prediction items instead of filtering")
    args = ap.parse_args()

    store = SqliteStore(args.db)
    store.migrate()
    pending = store.items_without_intelligence(limit=args.limit)

    if args.estimate:
        chars = sum(min(len(i["clean_text"] or ""), MAX_BODY_CHARS) for i in pending)
        print("  pending items      : %d" % len(pending))
        print("  body chars to send : %d" % chars)
        print("  ~input tokens      : %d (4 chars/token, prompt excluded)" % (chars // 4))
        print("  model              : %s" % DEFAULT_MODEL)
        store.close()
        return 0

    if args.dry_run:
        llm = StubLLM()
        print("DRY RUN — deterministic stub, no API call. Proves wiring, not judgement.\n")
    else:
        if not os.environ.get("ANTHROPIC_API_KEY"):
            print("ANTHROPIC_API_KEY is not set.\n", file=sys.stderr)
            print("Put it in .env (never in a shell command, never committed):",
                  file=sys.stderr)
            print("  cp .env.example .env && chmod 600 .env", file=sys.stderr)
            print("  export $(grep -v '^#' .env | xargs)", file=sys.stderr)
            print("\nOr try the wiring first:  --dry-run", file=sys.stderr)
            store.close()
            return 1
        from src.intelligence.extractor import AnthropicLLM
        llm = AnthropicLLM()
        print("extracting with %s\n" % llm.model)

    report = pipeline.run(store, llm, limit=args.limit,
                          skip_speculation=not args.keep_speculation)

    for row in sorted(report.records, key=lambda r: -r["importance"])[:12]:
        print("  imp=%.2f tension=%.2f  %-34s %s" % (
            row["importance"], row["tension"], row["primary_topic"][:34],
            (row["title"] or "")[:40]))
    if report.errors:
        print("\n  failures:")
        for cid, err in report.errors[:8]:
            print("    %s  %s" % (cid[:8], err[:88]))

    print("\n  attempted %d | stored %d | failed %d | speculation filtered %d"
          % (report.attempted, report.stored, report.failed,
             report.speculation_filtered))
    print("  db: " + ", ".join("%s=%d" % (k, v) for k, v in store.counts().items() if v))
    store.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
