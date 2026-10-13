"""The subscription-backed LLM client. Offline: parsing and prompt assembly only."""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.intelligence.claude_cli import ClaudeCliLLM, parse_json
from src.intelligence.schema import INTELLIGENCE_SCHEMA


@pytest.mark.parametrize("raw", [
    '{"a": 1}',
    '```json\n{"a": 1}\n```',
    '```\n{"a": 1}\n```',
    'Here is the record:\n{"a": 1}',
    '  \n {"a": 1} \n ',
])
def test_json_is_recovered_from_realistic_cli_output(raw):
    """A stray fence or preamble costs a whole model call to retry, so tolerate it."""
    assert parse_json(raw) == {"a": 1}


def test_nested_structures_survive():
    got = parse_json('{"sentiment": {"market": 0.4}, "entities": ["Visa"]}')
    assert got["sentiment"]["market"] == 0.4
    assert got["entities"] == ["Visa"]


@pytest.mark.parametrize("raw,fragment", [
    ("", "no output"),
    ("   ", "no output"),
    ("not json at all", "no JSON object"),
    ("{broken", "no JSON object"),
])
def test_garbage_raises_rather_than_returning_a_guess(raw, fragment):
    """Tolerant of formatting, intolerant of nonsense: the pipeline must record a
    failure, never store an invention."""
    with pytest.raises(RuntimeError) as exc:
        parse_json(raw)
    assert fragment in str(exc.value)


def test_prompt_carries_system_schema_and_user():
    prompt = ClaudeCliLLM._build("SYSTEM TEXT", "USER TEXT", INTELLIGENCE_SCHEMA)
    assert "SYSTEM TEXT" in prompt
    assert "USER TEXT" in prompt
    assert '"primary_topic"' in prompt, "schema must be inlined; the CLI has no "\
        "output_config.format"


def test_no_prose_instruction_is_repeated_at_the_end():
    """Last instruction wins when a long article sits in the middle."""
    prompt = ClaudeCliLLM._build("S", "U" * 5000, INTELLIGENCE_SCHEMA)
    assert prompt.rstrip().endswith("Return only the JSON object.")


def test_user_content_comes_after_the_contract():
    prompt = ClaudeCliLLM._build("S", "ARTICLE", INTELLIGENCE_SCHEMA)
    assert prompt.index("OUTPUT CONTRACT") < prompt.index("ARTICLE")
