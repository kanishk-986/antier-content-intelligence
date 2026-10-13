"""Section 19 adversarial AI QA over scored opportunities.

    python3 scripts/run_qa.py --top 5              # review the 5 highest-scored
    python3 scripts/run_qa.py --top 5 --dry-run    # no model call

Section 20: this narrows the queue; it does not decide. Human review is final, and
nothing here publishes anything.
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import yaml

from src.agents import qa
from src.database.sqlite_store import SqliteStore
from src.scoring import weights as wcfg
from src.scoring.opportunity import persist, score_all

BRAND = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     "config", "brand", "antier.yaml")


class StubQA:
    """Deterministic stand-in. Rejects everything, because an adversarial reviewer
    that approves by default is the failure mode section 19 warns about."""

    model = "stub-qa-v1"

    def extract(self, system, user, schema):
        thin = "from 1 distinct source" in user
        return {
            "decision": "RESEARCH_MORE" if thin else "REJECT",
            "confidence": 0.3,
            "problems": ["stub reviewer: no judgement applied (Q3)"],
            "evidence_issues": ["stub: evidence not assessed"],
            "factual_issues": [], "brand_issues": [], "risk_flags": [],
            "recommended_persona": "", "recommended_priority": "low",
            "failed_questions": [3],
        }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="data/aci.db")
    ap.add_argument("--top", type=int, default=5)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    config = wcfg.load()
    services = wcfg.load_services()
    with open(BRAND) as fh:
        proof_points = (yaml.safe_load(fh) or {}).get("proof_points") or []

    store = SqliteStore(args.db)
    store.migrate()
    narratives = store.narratives()
    if not narratives:
        print("No narratives. Run run_narratives.py then run_scoring.py.",
              file=sys.stderr)
        store.close()
        return 1

    intel = {}
    for item in store.content_items():
        row = store.intelligence_for(item["id"])
        if row:
            intel[item["id"]] = row

    scored = score_all(store, config, services, proof_points)
    if not args.dry_run:
        # Persist before reviewing: qa_reviews references opportunity ids, so the
        # rows under review must be the rows in the table.
        persist(store, [o for o, _ in scored])
    queue = scored[: args.top]

    if args.dry_run:
        llm = StubQA()
        print("DRY RUN — stub reviewer, no model call.\n")
    else:
        from src.intelligence.claude_cli import ClaudeCliLLM
        llm = ClaudeCliLLM()
        print("reviewing via the `claude` CLI — subscription, not API credits.\n")

    prompt = qa.load_prompt()
    tally = {}
    for opportunity, items in queue:
        result = qa.review_opportunity(llm, opportunity, items, intel, prompt=prompt)
        if result.review is None:
            print("  %5.2f  ERROR  %-40s %s" % (opportunity.score_0_10,
                                                opportunity.narrative_name[:40],
                                                result.error[:60]))
            store.audit("llm:" + result.model, "qa_failed",
                        object_ref=opportunity.id, detail=result.error)
            continue

        review = result.review
        tally[review["decision"]] = tally.get(review["decision"], 0) + 1
        print("  %5.2f  %-14s %s" % (opportunity.score_0_10, qa.summarise(review),
                                     opportunity.narrative_name[:40]))
        for problem in review["problems"][:3]:
            print("          · %s" % problem[:96])

        store.insert_qa_review(qa.as_row(result))
        store.audit("llm:" + result.model, "qa_reviewed",
                    object_ref=opportunity.id,
                    detail=json.dumps({"decision": review["decision"],
                                       "failed": review["failed_questions"]}))

    print("\n  decisions: %s" % (", ".join("%s=%d" % kv for kv in sorted(tally.items()))
                                 or "none"))
    print("  Section 20: this narrows the queue. Human review is final; nothing is "
          "published here.")
    store.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
