"""Section 19 adversarial AI QA.

Reviews one scored opportunity and tries to find reasons not to publish. The LLM
judges; the opportunity score was already computed deterministically in Python and is
given to the reviewer as *evidence to audit*, not as a verdict to ratify.

This is also where the recency artefact is caught. Section 15 gives 30% of its weight
to velocity and novelty, so a fresh low-value item can rank highly on timing alone;
question 3 of section 19 ("genuinely emerging, or merely noisy?") is the designed
place to reject that, and the prompt is given the scoring provenance so it can.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Any

from src.intelligence.extractor import LLM

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PROMPT_PATH = os.path.join(REPO, "prompts", "ai_qa.v1.md")
PROMPT_VERSION = "ai_qa.v1"

DECISIONS = ("APPROVE", "REJECT", "RESEARCH_MORE")
PRIORITIES = ("high", "medium", "low")
PERSONAS = ("company", "ceo", "cto", "sme", "")

MAX_ARTICLES = 6
ARTICLE_CHARS = 700

QA_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "decision": {"type": "string", "enum": list(DECISIONS)},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "problems": {"type": "array", "items": {"type": "string"}, "maxItems": 12},
        "evidence_issues": {"type": "array", "items": {"type": "string"}, "maxItems": 8},
        "factual_issues": {"type": "array", "items": {"type": "string"}, "maxItems": 8},
        "brand_issues": {"type": "array", "items": {"type": "string"}, "maxItems": 8},
        "risk_flags": {"type": "array", "items": {"type": "string"}, "maxItems": 8},
        "recommended_persona": {"type": "string", "enum": list(PERSONAS)},
        "recommended_priority": {"type": "string", "enum": list(PRIORITIES)},
        "failed_questions": {
            "type": "array", "items": {"type": "integer", "minimum": 1, "maximum": 10},
            "maxItems": 10,
        },
    },
    "required": [
        "decision", "confidence", "problems", "evidence_issues", "factual_issues",
        "brand_issues", "risk_flags", "recommended_persona", "recommended_priority",
        "failed_questions",
    ],
    "additionalProperties": False,
}


class QAValidationError(ValueError):
    pass


@dataclass
class QAResult:
    opportunity_id: str
    review: dict[str, Any] | None
    error: str = ""
    model: str = ""
    prompt_version: str = PROMPT_VERSION


def validate(review: dict[str, Any]) -> dict[str, Any]:
    missing = [k for k in QA_SCHEMA["required"] if k not in review]
    if missing:
        raise QAValidationError(f"missing fields: {', '.join(missing)}")
    if review["decision"] not in DECISIONS:
        raise QAValidationError(f"decision {review['decision']!r} not one of {DECISIONS}")
    conf = review["confidence"]
    if not isinstance(conf, (int, float)) or isinstance(conf, bool):
        raise QAValidationError("confidence is not a number")
    if not 0.0 <= float(conf) <= 1.0:
        raise QAValidationError(f"confidence={conf} outside [0, 1]")
    if review["recommended_priority"] not in PRIORITIES:
        raise QAValidationError(f"priority {review['recommended_priority']!r} invalid")
    if review["recommended_persona"] not in PERSONAS:
        raise QAValidationError(f"persona {review['recommended_persona']!r} invalid")
    for key in ("problems", "evidence_issues", "factual_issues", "brand_issues",
                "risk_flags"):
        if not isinstance(review[key], list):
            raise QAValidationError(f"{key} is not an array")

    # An adversarial reviewer that rejects without saying why is useless downstream:
    # section 27 requires the dashboard to show "rejected topics with reasons", and
    # section 30's feedback loop consumes them.
    if review["decision"] != "APPROVE" and not review["problems"]:
        raise QAValidationError(f"{review['decision']} with no stated problem")
    return review


def load_prompt(path: str = PROMPT_PATH) -> tuple[str, str]:
    with open(path) as fh:
        text = fh.read()
    parts = re.split(r"^##\s+(SYSTEM|USER)\s*$", text, flags=re.MULTILINE)
    sections = {parts[i]: parts[i + 1].strip() for i in range(1, len(parts) - 1, 2)}
    if "SYSTEM" not in sections or "USER" not in sections:
        raise ValueError(f"{path} must contain '## SYSTEM' and '## USER'")
    return sections["SYSTEM"], sections["USER"]


def render(template: str, opportunity, items: list[dict[str, Any]],
           intelligence: dict[str, dict[str, Any]]) -> str:
    rows = [
        "| dimension | value | basis |",
        "|---|---|---|",
    ]
    for name, dim in opportunity.dimensions.items():
        rows.append(f"| {name} | {dim.value} | {dim.basis} |")

    articles = []
    for item in items[:MAX_ARTICLES]:
        body = (item.get("clean_text") or "")[:ARTICLE_CHARS]
        articles.append(
            f"- **{item.get('title') or '(untitled)'}**\n"
            f"  published: {item.get('published_at') or 'UNCONFIRMED'}\n"
            f"  url: {item.get('url')}\n"
            f"  {body}"
        )
    if len(items) > MAX_ARTICLES:
        articles.append(f"- ...and {len(items) - MAX_ARTICLES} more item(s)")

    intel_lines = []
    for item in items:
        row = intelligence.get(item["id"])
        if not row:
            continue
        intel_lines.append(
            "- importance=%s topics=%s claims=%s"
            % (row.get("importance_score"),
               (row.get("topics") or "")[:120], (row.get("claims") or "")[:200])
        )
    if not intel_lines:
        intel_lines.append("(none of these items has been extracted yet)")

    return template.format(
        narrative_name=opportunity.narrative_name,
        item_count=len(items),
        source_count=len({i["source_id"] for i in items}),
        score=opportunity.score_0_10,
        band=opportunity.band,
        service_rank=opportunity.service_rank or "none",
        saturation=opportunity.saturation.as_text(),
        dimension_table="\n".join(rows),
        unmeasured=", ".join(opportunity.unmeasured) or "none",
        articles="\n".join(articles),
        intelligence="\n".join(intel_lines),
    )


def review_opportunity(llm: LLM, opportunity, items: list[dict[str, Any]],
                       intelligence: dict[str, dict[str, Any]],
                       prompt: tuple[str, str] | None = None) -> QAResult:
    """Review one opportunity. Errors are returned, not raised."""
    system, template = prompt or load_prompt()
    model = getattr(llm, "model", "")
    try:
        raw = llm.extract(system, render(template, opportunity, items, intelligence),
                          QA_SCHEMA)
    except Exception as exc:
        return QAResult(opportunity.id, None, f"{type(exc).__name__}: {exc}"[:220],
                        model=model)
    try:
        return QAResult(opportunity.id, validate(raw), model=model)
    except QAValidationError as exc:
        return QAResult(opportunity.id, None, f"invalid review: {exc}", model=model)


def summarise(review: dict[str, Any]) -> str:
    bits = [review["decision"], "conf=%.2f" % review["confidence"]]
    if review.get("failed_questions"):
        bits.append("failed Q" + ",".join(str(q) for q in review["failed_questions"]))
    if review.get("recommended_persona"):
        bits.append("persona=" + review["recommended_persona"])
    return " ".join(bits)


def as_row(result: QAResult) -> dict[str, Any]:
    r = result.review or {}
    return {
        "opportunity_id": result.opportunity_id,
        "ai_decision": r.get("decision"),
        "confidence": r.get("confidence"),
        "evidence_issues": json.dumps(r.get("evidence_issues") or []),
        "factual_issues": json.dumps(r.get("factual_issues") or []),
        "brand_issues": json.dumps(r.get("brand_issues") or []),
        "risk_flags": json.dumps(r.get("risk_flags") or []),
        "problems": json.dumps(r.get("problems") or []),
        "failed_questions": json.dumps(r.get("failed_questions") or []),
        "prompt_version": "%s@%s" % (result.prompt_version, result.model),
        "human_decision": None,
        "reviewer": None,
        "reviewed_at": None,
    }
