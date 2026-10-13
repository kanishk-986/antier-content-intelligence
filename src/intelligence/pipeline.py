"""Run extraction over items that do not yet have intelligence.

Section 10.2 applied to the LLM stage: an item already extracted is never re-sent,
because here the cost is money rather than bandwidth.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any

from src.intelligence.extractor import LLM, extract_item, load_prompt
from src.intelligence.schema import sentiment_tension


@dataclass
class ExtractionReport:
    attempted: int = 0
    stored: int = 0
    failed: int = 0
    speculation_filtered: int = 0
    stopped_early: bool = False
    remaining: int = 0
    errors: list[tuple[str, str]] = field(default_factory=list)
    records: list[dict[str, Any]] = field(default_factory=list)


def run(store, llm: LLM, limit: int | None = None,
        skip_speculation: bool = True,
        budget_seconds: float | None = None,
        now=time.monotonic) -> ExtractionReport:
    """Extract intelligence for items that have none.

    `budget_seconds` stops the pass cleanly when the wall clock runs out, between
    items rather than mid-call. Extraction is resumable by design -- an item already
    extracted is never re-sent -- so stopping early costs nothing but time.

    It exists because the subscription rate limits rather than charges: a pass that
    normally takes 20 seconds an item managed 7 items in three hours once limiting
    started, with no upper bound. Without a budget the daily cycle has no end, and a
    cycle that never ends sends no brief at all.
    """
    report = ExtractionReport()
    prompt = load_prompt()
    sources = {s["id"]: s for s in store.active_sources()}
    items = store.items_without_intelligence(limit=limit)
    started = now()

    for item in items:
        if budget_seconds is not None and now() - started >= budget_seconds:
            report.stopped_early = True
            report.remaining = len(items) - report.attempted
            break
        report.attempted += 1
        source = sources.get(item["source_id"], {})
        result = extract_item(llm, item, source, prompt=prompt)

        if result.record is None:
            report.failed += 1
            report.errors.append((item["id"], result.error))
            store.audit("llm:" + (result.model or "?"), "extraction_failed",
                        object_ref=item["id"], detail=result.error)
            continue

        record = result.record
        # Section 2.2 excludes price-only commentary and token prediction. The model
        # flags it; the decision to drop is the pipeline's, and is logged either way.
        if skip_speculation and record.get("is_price_speculation"):
            report.speculation_filtered += 1
            store.audit("llm:" + result.model, "extraction_skipped_speculation",
                        object_ref=item["id"],
                        detail=record.get("market_implication", "")[:200])
            continue

        store.insert_intelligence(item["id"], record, result.prompt_version,
                                  result.model)
        report.stored += 1
        report.records.append({
            "content_id": item["id"],
            "title": item.get("title"),
            "primary_topic": record["primary_topic"],
            "importance": record["importance"],
            "tension": sentiment_tension(record["sentiment"]),
            "entities": record["entities"][:5],
        })

    store.audit("system", "intelligence_run",
                detail=json.dumps({"attempted": report.attempted,
                                   "stored": report.stored,
                                   "failed": report.failed,
                                   "speculation": report.speculation_filtered}))
    return report
