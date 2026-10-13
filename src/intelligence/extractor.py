"""Call Claude for one content item and return a validated section 11 record.

CLAUDE.md rule 6: structured outputs, not prose. The schema is passed as
`output_config.format`, so the model returns JSON that already matches the shape, and
schema.validate then checks it is sensible as well as well-formed.

The client is injected rather than constructed here, so the pipeline and its tests
can run against a stub with no API key and no network.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Any, Protocol

from src.intelligence.schema import INTELLIGENCE_SCHEMA, ValidationError, validate

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PROMPT_PATH = os.path.join(REPO, "prompts", "intelligence.v1.md")
PROMPT_VERSION = "intelligence.v1"

DEFAULT_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-opus-5")
MAX_BODY_CHARS = 12_000       # a long article adds cost, not accuracy, past this
MAX_TOKENS = 4_000


class LLM(Protocol):
    def extract(self, system: str, user: str, schema: dict[str, Any]) -> dict[str, Any]:
        """Return a parsed JSON object matching `schema`."""

    @property
    def model(self) -> str: ...


@dataclass
class ExtractionResult:
    content_id: str
    record: dict[str, Any] | None
    error: str = ""
    prompt_version: str = PROMPT_VERSION
    model: str = ""


def load_prompt(path: str = PROMPT_PATH) -> tuple[str, str]:
    """Split the prompt file into its SYSTEM and USER halves."""
    with open(path) as fh:
        text = fh.read()
    parts = re.split(r"^##\s+(SYSTEM|USER)\s*$", text, flags=re.MULTILINE)
    sections: dict[str, str] = {}
    for i in range(1, len(parts) - 1, 2):
        sections[parts[i]] = parts[i + 1].strip()
    if "SYSTEM" not in sections or "USER" not in sections:
        raise ValueError(f"{path} must contain '## SYSTEM' and '## USER' headings")
    return sections["SYSTEM"], sections["USER"]


def render_user(template: str, item: dict[str, Any], source: dict[str, Any]) -> str:
    body = (item.get("clean_text") or "")[:MAX_BODY_CHARS]
    return template.format(
        source_name=source.get("name") or "unknown",
        authority_score=source.get("authority_score") or "?",
        published_at=item.get("published_at") or "unconfirmed",
        url=item.get("url") or "",
        title=item.get("title") or "(untitled)",
        body=body or "(no body text extracted)",
    )


class AnthropicLLM:
    """Real client. Constructed only when a key is present."""

    def __init__(self, model: str = DEFAULT_MODEL, effort: str = "low"):
        import anthropic  # imported late so the module loads without the SDK

        self._client = anthropic.Anthropic()
        self._model = model
        # Extraction is a reading task, not a reasoning task, and runs over every
        # item -- low effort keeps per-item cost sane. Thinking is left at its
        # default (adaptive on Opus 5) rather than disabled, which on this model can
        # leak internal tags into the response.
        self._effort = effort

    @property
    def model(self) -> str:
        return self._model

    def extract(self, system: str, user: str, schema: dict[str, Any]) -> dict[str, Any]:
        response = self._client.messages.create(
            model=self._model,
            max_tokens=MAX_TOKENS,
            system=system,
            output_config={
                "effort": self._effort,
                "format": {"type": "json_schema", "schema": schema},
            },
            messages=[{"role": "user", "content": user}],
        )
        if response.stop_reason == "refusal":
            raise RuntimeError("model refused the request")
        text = next((b.text for b in response.content if b.type == "text"), "")
        if not text:
            raise RuntimeError(f"empty response (stop_reason={response.stop_reason})")
        return json.loads(text)


def extract_item(llm: LLM, item: dict[str, Any], source: dict[str, Any],
                 prompt: tuple[str, str] | None = None) -> ExtractionResult:
    """Extract one item. Errors are returned, not raised: one bad article must not
    abort a run over hundreds."""
    system, user_template = prompt or load_prompt()
    try:
        raw = llm.extract(system, render_user(user_template, item, source),
                          INTELLIGENCE_SCHEMA)
    except Exception as exc:
        return ExtractionResult(item["id"], None, f"{type(exc).__name__}: {exc}"[:220],
                                model=getattr(llm, "model", ""))
    try:
        record = validate(raw)
    except ValidationError as exc:
        return ExtractionResult(item["id"], None, f"invalid record: {exc}",
                                model=getattr(llm, "model", ""))
    return ExtractionResult(item["id"], record, model=getattr(llm, "model", ""))
