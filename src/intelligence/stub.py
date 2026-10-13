"""A deterministic stand-in for the model.

Exists so the extraction pipeline, schema, store writes and efficiency rule can be
exercised with no API key and no network. It is keyword matching, not judgement: its
output is structurally valid and analytically worthless, which is exactly the point
-- it proves the plumbing without pretending to prove the model.
"""

from __future__ import annotations

import re
from typing import Any

from src.intelligence.schema import SENTIMENT_DIMENSIONS

_SPECULATION = re.compile(
    r"price (target|prediction)|will hit \$|moon|rally|bull run|\bpump\b", re.IGNORECASE
)
_TOPIC_HINTS = [
    ("stablecoin settlement", ["stablecoin", "usdc", "settle"]),
    ("rwa tokenization", ["tokeniz", "tokenis", "rwa", "real-world"]),
    ("ai agent infrastructure", ["agent", "agentic", "autonomous"]),
    ("regulation and policy", ["regulat", "esma", "sec ", "mica", "compliance"]),
    ("payments infrastructure", ["payment", "card", "remittance", "cross-border"]),
    ("institutional defi", ["lending", "liquidity", "defi", "custody"]),
]


class StubLLM:
    @property
    def model(self) -> str:
        return "stub-deterministic-v1"

    def extract(self, system: str, user: str, schema: dict[str, Any]) -> dict[str, Any]:
        low = user.lower()
        topic = "uncategorised"
        for name, hints in _TOPIC_HINTS:
            if any(h in low for h in hints):
                topic = name
                break
        proper = re.findall(
            r"\b[A-Z][A-Za-z&.]{2,}(?:\s[A-Z][A-Za-z&.]{2,})?", user
        )
        entities = sorted(set(proper))[:5]
        return {
            "primary_topic": topic,
            "secondary_topics": [],
            "entities": entities,
            "claims": [],
            # Zero everywhere: the stub has no basis for a sentiment, and inventing
            # one would make a test pass for the wrong reason.
            "sentiment": dict.fromkeys(SENTIMENT_DIMENSIONS, 0.0),
            "market_implication": "",
            "technical_implication": "",
            "business_implication": "",
            "importance": 0.5 if topic != "uncategorised" else 0.2,
            "is_price_speculation": bool(_SPECULATION.search(user)),
        }
