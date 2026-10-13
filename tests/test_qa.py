"""Section 19 adversarial QA. Offline: schema, validation and prompt assembly."""

import os
import sys
from dataclasses import dataclass, field

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.agents import qa
from src.scoring.relevance import DimensionScore
from src.scoring.saturation import Saturation

CLEAN = {
    "decision": "APPROVE", "confidence": 0.8, "problems": [],
    "evidence_issues": [], "factual_issues": [], "brand_issues": [], "risk_flags": [],
    "recommended_persona": "ceo", "recommended_priority": "high",
    "failed_questions": [],
}


@dataclass
class FakeOpportunity:
    id: str = "o1"
    narrative_id: str = "n1"
    narrative_name: str = "stablecoin rails"
    score_0_10: float = 7.5
    band: str = "good"
    service_rank: int = 2
    unmeasured: list = field(default_factory=list)
    dimensions: dict = field(default_factory=lambda: {
        "trend_velocity": DimensionScore(0.5, "velocity 1.0"),
        "antier_relevance": DimensionScore(0.9, "service 2"),
    })
    saturation: Saturation = field(default_factory=lambda: Saturation(
        "not_measured", 3, "not_measured", "saturation unknown"))


def item(i, title="Visa expands settlement", source="s1"):
    return {"id": f"i{i}", "source_id": source, "title": title,
            "clean_text": "body text here", "url": f"https://x/{i}",
            "published_at": "2026-10-12T00:00:00+00:00"}


# --- schema and validation ----------------------------------------------------

def test_schema_is_strict():
    assert qa.QA_SCHEMA["additionalProperties"] is False
    assert set(qa.QA_SCHEMA["required"]) == set(qa.QA_SCHEMA["properties"])


def test_decision_enum_matches_the_blueprint():
    assert qa.DECISIONS == ("APPROVE", "REJECT", "RESEARCH_MORE")


def test_clean_approve_validates():
    assert qa.validate(dict(CLEAN))


def test_reject_without_a_stated_problem_is_invalid():
    """Section 27 must show 'rejected topics with reasons' and section 30's feedback
    loop consumes them, so a silent rejection is useless downstream."""
    with pytest.raises(qa.QAValidationError) as exc:
        qa.validate({**CLEAN, "decision": "REJECT", "problems": []})
    assert "no stated problem" in str(exc.value)


def test_research_more_also_needs_a_reason():
    with pytest.raises(qa.QAValidationError):
        qa.validate({**CLEAN, "decision": "RESEARCH_MORE", "problems": []})


def test_reject_with_a_problem_is_valid():
    assert qa.validate({**CLEAN, "decision": "REJECT",
                        "problems": ["Q3: single-source vendor PR"]})


@pytest.mark.parametrize("patch,fragment", [
    ({"decision": "MAYBE"}, "not one of"),
    ({"confidence": 1.5}, "outside"),
    ({"confidence": "high"}, "not a number"),
    ({"recommended_priority": "urgent"}, "priority"),
    ({"recommended_persona": "cfo"}, "persona"),
    ({"problems": "lots"}, "not an array"),
])
def test_invalid_fields_are_rejected(patch, fragment):
    with pytest.raises(qa.QAValidationError) as exc:
        qa.validate({**CLEAN, **patch})
    assert fragment in str(exc.value)


def test_missing_field_is_reported():
    partial = {k: v for k, v in CLEAN.items() if k != "risk_flags"}
    with pytest.raises(qa.QAValidationError) as exc:
        qa.validate(partial)
    assert "risk_flags" in str(exc.value)


# --- prompt -------------------------------------------------------------------

def test_prompt_tells_the_reviewer_to_find_reasons_not_to_publish():
    """Section 19: an analyst who approves everything has failed."""
    system, _ = qa.load_prompt()
    assert "find reasons not to publish" in system.lower()


def test_prompt_treats_the_score_as_evidence_not_verdict():
    system, _ = qa.load_prompt()
    low = system.lower()
    assert "do not recompute" in low
    assert "a high score is not evidence" in low


def test_prompt_targets_the_recency_artefact():
    """This is why Phase 7 is the chosen fix for the 30% recency weighting."""
    system, _ = qa.load_prompt()
    low = system.lower()
    assert "treat_as_emerging" in low
    assert "timing is doing the work" in low


def test_render_includes_provenance_and_unmeasured_dimensions():
    _, template = qa.load_prompt()
    o = FakeOpportunity(unmeasured=["commercial_relevance"])
    out = qa.render(template, o, [item(1), item(2, source="s2")], {})
    assert "trend_velocity" in out and "velocity 1.0" in out
    assert "commercial_relevance" in out
    assert "2 from 2 distinct source" in out


def test_render_marks_an_unconfirmed_date(monkeypatch):
    _, template = qa.load_prompt()
    bare = {**item(1), "published_at": None}
    out = qa.render(template, FakeOpportunity(), [bare], {})
    assert "UNCONFIRMED" in out


def test_render_says_so_when_nothing_is_extracted():
    _, template = qa.load_prompt()
    out = qa.render(template, FakeOpportunity(), [item(1)], {})
    assert "has been extracted yet" in out


def test_render_caps_the_article_list():
    _, template = qa.load_prompt()
    items = [item(i) for i in range(qa.MAX_ARTICLES + 4)]
    out = qa.render(template, FakeOpportunity(), items, {})
    assert "more item(s)" in out


# --- failure handling ---------------------------------------------------------

class BoomQA:
    model = "boom"

    def extract(self, system, user, schema):
        raise RuntimeError("cli died")


def test_model_failure_is_returned_not_raised():
    got = qa.review_opportunity(BoomQA(), FakeOpportunity(), [item(1)], {})
    assert got.review is None and "cli died" in got.error


def test_row_records_prompt_version_and_model():
    result = qa.QAResult("o1", dict(CLEAN), model="m1")
    row = qa.as_row(result)
    assert row["prompt_version"] == "ai_qa.v1@m1"
    assert row["human_decision"] is None, "human decision is not AI's to set"


def test_summarise_is_readable():
    text = qa.summarise({**CLEAN, "decision": "REJECT", "failed_questions": [3, 7]})
    assert "REJECT" in text and "Q3,7" in text


# --- regression guard ---------------------------------------------------------

@pytest.mark.parametrize("name", ["ai_qa.v1.md", "intelligence.v1.md"])
def test_no_directive_is_stranded_above_the_system_header(name):
    """load_prompt() discards everything above '## SYSTEM'. A rule written there
    looks delivered in review and silently never reaches the model."""
    path = os.path.join(os.path.dirname(qa.PROMPT_PATH), name)
    with open(path) as fh:
        preamble = fh.read().split("## SYSTEM")[0].lower()
    for tell in ("do not", "you must", "never ", "**you"):
        assert tell not in preamble, (
            f"{name}: directive {tell!r} sits above '## SYSTEM' and is dropped"
        )
