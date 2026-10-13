"""The section 11 intelligence record: JSON schema plus validation.

CLAUDE.md rule 6 requires structured outputs, so the schema is enforced by the API
via `output_config.format`. It is validated again on return, because a schema
guarantees shape, not sense: a sentiment of 4.2 or an importance of -1 is
well-formed and still wrong.
"""

from __future__ import annotations

from typing import Any

SENTIMENT_DIMENSIONS = (
    "market", "institutional", "developer", "regulatory", "enterprise", "community",
)

# Section 11 output schema. additionalProperties false and a full `required` list are
# what make strict structured output possible.
INTELLIGENCE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "primary_topic": {"type": "string"},
        "secondary_topics": {
            "type": "array", "items": {"type": "string"}, "maxItems": 5,
        },
        "entities": {"type": "array", "items": {"type": "string"}, "maxItems": 20},
        "claims": {"type": "array", "items": {"type": "string"}, "maxItems": 12},
        "sentiment": {
            "type": "object",
            "properties": {
                d: {"type": "number", "minimum": -1, "maximum": 1}
                for d in SENTIMENT_DIMENSIONS
            },
            "required": list(SENTIMENT_DIMENSIONS),
            "additionalProperties": False,
        },
        "market_implication": {"type": "string"},
        "technical_implication": {"type": "string"},
        "business_implication": {"type": "string"},
        "importance": {"type": "number", "minimum": 0, "maximum": 1},
        "is_price_speculation": {"type": "boolean"},
    },
    "required": [
        "primary_topic", "secondary_topics", "entities", "claims", "sentiment",
        "market_implication", "technical_implication", "business_implication",
        "importance", "is_price_speculation",
    ],
    "additionalProperties": False,
}


class ValidationError(ValueError):
    """A record that is well-formed but not sensible."""


def validate(record: dict[str, Any]) -> dict[str, Any]:
    """Check and normalise one record. Raises ValidationError on nonsense.

    Clamping silently would hide a misbehaving prompt, and QA_POLICY.md depends on
    sentiment being comparable across items -- so out-of-range values are rejected,
    not squashed.
    """
    missing = [k for k in INTELLIGENCE_SCHEMA["required"] if k not in record]
    if missing:
        raise ValidationError(f"missing fields: {', '.join(missing)}")

    if not isinstance(record["primary_topic"], str) or not record["primary_topic"].strip():
        raise ValidationError("primary_topic is empty")

    sentiment = record["sentiment"]
    if not isinstance(sentiment, dict):
        raise ValidationError("sentiment is not an object")
    for dim in SENTIMENT_DIMENSIONS:
        if dim not in sentiment:
            raise ValidationError(f"sentiment.{dim} missing")
        value = sentiment[dim]
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise ValidationError(f"sentiment.{dim} is not a number")
        if not -1.0 <= float(value) <= 1.0:
            raise ValidationError(f"sentiment.{dim}={value} outside [-1, 1]")

    importance = record["importance"]
    if not isinstance(importance, (int, float)) or isinstance(importance, bool):
        raise ValidationError("importance is not a number")
    if not 0.0 <= float(importance) <= 1.0:
        raise ValidationError(f"importance={importance} outside [0, 1]")

    for key in ("secondary_topics", "entities", "claims"):
        if not isinstance(record[key], list):
            raise ValidationError(f"{key} is not an array")
        if not all(isinstance(v, str) for v in record[key]):
            raise ValidationError(f"{key} contains a non-string")

    return record


def sentiment_tension(sentiment: dict[str, float]) -> float:
    """Spread between the most and least positive dimension.

    Section 13 treats tension as a feature: strong institutional optimism beside
    developer frustration is a thought-leadership opening, so it is measured rather
    than averaged away.
    """
    values = [float(sentiment[d]) for d in SENTIMENT_DIMENSIONS if d in sentiment]
    return round(max(values) - min(values), 3) if values else 0.0
