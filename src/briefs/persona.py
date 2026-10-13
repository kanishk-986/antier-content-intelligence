"""Assign an opportunity to an editorial persona (section 4, section 18).

A persona is a territory, not a job title. The question is which angle an
opportunity should be written from, and the answer routes it to the person who owns
that angle.

Two inputs, in order of authority:

  1. The QA reviewer's `recommended_persona`. A human-reviewable judgement already
     exists and section 20 makes it the stronger signal; overriding it with a
     keyword match would discard the better evidence.
  2. A deterministic territory match. Every persona config lists its `territory`,
     and the narrative's own text is matched against it. This is arithmetic, not
     judgement, so it belongs in Python (CLAUDE.md rule 7).

An opportunity that matches no territory is assigned to `company`, which is the
general channel, and the reason is recorded. It is never dropped: a silent drop
would make the brief look like nothing happened in that territory.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Any

import yaml

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BRAND = os.path.join(REPO, "config", "brand")
RECIPIENTS = os.path.join(BRAND, "recipients.yaml")

PERSONAS = ("ceo", "cto", "sme", "company")
FALLBACK = "company"

_WORD = re.compile(r"[a-z][a-z0-9+#.-]{2,}")


@dataclass
class Assignment:
    persona: str
    reason: str
    from_qa: bool


def load_personas(brand_dir: str = BRAND) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for persona in PERSONAS:
        path = os.path.join(brand_dir, f"{persona}.yaml")
        if not os.path.exists(path):
            continue
        with open(path) as fh:
            out[persona] = yaml.safe_load(fh) or {}
    return out


def load_recipients(path: str = RECIPIENTS) -> dict[str, Any]:
    with open(path) as fh:
        return yaml.safe_load(fh) or {}


def _tokens(text: str) -> set[str]:
    return set(_WORD.findall((text or "").lower()))


def territory_terms(config: dict[str, Any]) -> set[str]:
    """Every word of a persona's territory, plus its framing keys.

    Framing keys are narrative names from the section 18 matrix, which is the most
    direct statement available of what belongs to a persona.
    """
    terms: set[str] = set()
    for entry in config.get("territory") or []:
        terms |= _tokens(str(entry))
    for key in (config.get("framing") or {}):
        terms |= _tokens(str(key).replace("_", " "))
    return terms


def assign(opportunity, items: list[dict[str, Any]],
           personas: dict[str, dict[str, Any]],
           qa_persona: str | None = None) -> Assignment:
    if qa_persona in personas:
        return Assignment(qa_persona, "QA reviewer's recommendation", True)

    text = " ".join([
        getattr(opportunity, "narrative_name", "") or "",
        " ".join((i.get("title") or "") for i in items),
    ])
    words = _tokens(text)

    scores: dict[str, int] = {}
    for persona, config in personas.items():
        hits = words & territory_terms(config)
        if hits:
            scores[persona] = len(hits)
    if not scores:
        return Assignment(FALLBACK, "no territory matched; general channel", False)

    # A tie goes to the more specific persona: `company` is the catch-all, so it
    # only wins when nothing narrower matched at all.
    best = max(scores.items(), key=lambda kv: (kv[1], kv[0] != FALLBACK))
    return Assignment(best[0], f"{best[1]} territory term(s) matched", False)
