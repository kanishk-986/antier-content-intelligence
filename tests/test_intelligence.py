"""Extraction schema, prompt and pipeline. Offline: a stub replaces the model."""

import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.database.sqlite_store import SqliteStore
from src.intelligence import pipeline
from src.intelligence.extractor import (
    MAX_BODY_CHARS,
    extract_item,
    load_prompt,
    render_user,
)
from src.intelligence.schema import (
    INTELLIGENCE_SCHEMA,
    SENTIMENT_DIMENSIONS,
    ValidationError,
    sentiment_tension,
    validate,
)
from src.intelligence.stub import StubLLM

GOOD = {
    "primary_topic": "stablecoin settlement",
    "secondary_topics": ["cross-border"],
    "entities": ["Visa", "Stripe"],
    "claims": ["Visa expanded settlement to more corridors."],
    "sentiment": {"market": 0.4, "institutional": 0.8, "developer": -0.3,
                  "regulatory": 0.1, "enterprise": 0.5, "community": 0.0},
    "market_implication": "m", "technical_implication": "t",
    "business_implication": "b",
    "importance": 0.7, "is_price_speculation": False,
}


# --- schema -------------------------------------------------------------------

def test_schema_is_strict_enough_for_structured_output():
    """additionalProperties false plus a full required list is what makes the
    API-side guarantee possible (CLAUDE.md rule 6)."""
    assert INTELLIGENCE_SCHEMA["additionalProperties"] is False
    assert set(INTELLIGENCE_SCHEMA["required"]) == set(INTELLIGENCE_SCHEMA["properties"])


def test_all_six_sentiment_dimensions_required():
    """Section 13 defines six; five would silently drop one."""
    assert len(SENTIMENT_DIMENSIONS) == 6
    sentiment = INTELLIGENCE_SCHEMA["properties"]["sentiment"]
    assert set(sentiment["required"]) == set(SENTIMENT_DIMENSIONS)


def test_valid_record_passes():
    assert validate(dict(GOOD)) == GOOD


@pytest.mark.parametrize("field,value,fragment", [
    ("importance", 1.4, "importance"),
    ("importance", -0.1, "importance"),
    ("primary_topic", "", "primary_topic"),
    ("entities", "Visa", "not an array"),
    ("claims", [1, 2], "non-string"),
])
def test_nonsense_is_rejected_not_clamped(field, value, fragment):
    """Clamping would hide a misbehaving prompt, and QA depends on these being
    comparable across items."""
    with pytest.raises(ValidationError) as exc:
        validate({**GOOD, field: value})
    assert fragment in str(exc.value)


def test_out_of_range_sentiment_rejected():
    bad = {**GOOD, "sentiment": {**GOOD["sentiment"], "market": 4.2}}
    with pytest.raises(ValidationError):
        validate(bad)


def test_missing_sentiment_dimension_rejected():
    partial = {k: v for k, v in GOOD["sentiment"].items() if k != "community"}
    with pytest.raises(ValidationError) as exc:
        validate({**GOOD, "sentiment": partial})
    assert "community" in str(exc.value)


def test_booleans_are_not_accepted_as_numbers():
    with pytest.raises(ValidationError):
        validate({**GOOD, "importance": True})


def test_tension_measures_the_spread_not_the_average():
    """Section 13: averaging destroys the signal tension carries."""
    assert sentiment_tension(GOOD["sentiment"]) == 1.1
    assert sentiment_tension(dict.fromkeys(SENTIMENT_DIMENSIONS, 0.5)) == 0.0


# --- prompt -------------------------------------------------------------------

def test_prompt_splits_into_system_and_user():
    system, user = load_prompt()
    assert "mid-market" in system
    assert "{title}" in user and "{body}" in user


def test_prompt_forbids_fabrication_and_scoring():
    system, _ = load_prompt()
    low = system.lower()
    assert "never invent" in low
    assert "you do not score" in low
    assert "do not compute an opportunity score" in low


def test_render_truncates_an_overlong_body():
    """A long article adds cost, not accuracy. Asserted by substring rather than a
    character count, because the template itself contains an 'x'."""
    _, user = load_prompt()
    out = render_user(user, {"clean_text": "x" * (MAX_BODY_CHARS + 5000),
                             "title": "t", "url": "u", "published_at": None},
                      {"name": "s", "authority_score": 9})
    assert "x" * MAX_BODY_CHARS in out
    assert "x" * (MAX_BODY_CHARS + 1) not in out


def test_render_marks_an_unconfirmed_date_rather_than_blank():
    _, user = load_prompt()
    out = render_user(user, {"clean_text": "b", "title": "t", "url": "u",
                             "published_at": None}, {"name": "s", "authority_score": 9})
    assert "unconfirmed" in out


# --- extractor ----------------------------------------------------------------

class BoomLLM:
    model = "boom"

    def extract(self, system, user, schema):
        raise RuntimeError("upstream exploded")


class BadShapeLLM:
    model = "bad"

    def extract(self, system, user, schema):
        return {"primary_topic": "x"}          # missing everything else


def test_model_failure_is_returned_not_raised():
    """One bad article must not abort a run over hundreds."""
    result = extract_item(BoomLLM(), {"id": "i1", "clean_text": "b", "title": "t"},
                          {"name": "s", "authority_score": 9})
    assert result.record is None
    assert "upstream exploded" in result.error


def test_malformed_record_is_rejected_with_a_reason():
    result = extract_item(BadShapeLLM(), {"id": "i1", "clean_text": "b", "title": "t"},
                          {"name": "s", "authority_score": 9})
    assert result.record is None
    assert "invalid record" in result.error


def test_stub_output_validates():
    """The stub must be structurally honest even though it is analytically useless."""
    raw = StubLLM().extract("sys", "Visa expands stablecoin settlement", {})
    assert validate(raw)


def test_stub_sentiment_is_zero_not_invented():
    raw = StubLLM().extract("sys", "anything", {})
    assert all(v == 0.0 for v in raw["sentiment"].values())


def test_stub_detects_price_speculation():
    raw = StubLLM().extract("sys", "BTC price target: will hit $200k in a bull run", {})
    assert raw["is_price_speculation"] is True


# --- pipeline -----------------------------------------------------------------

@pytest.fixture
def store():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.unlink(path)
    s = SqliteStore(path)
    s.migrate()
    s.upsert_source({"id": "s1", "name": "BIS", "url": "https://bis.org",
                     "source_type": "regulator", "authority_score": 10,
                     "topics": [], "active": True})
    yield s
    s.close()
    if os.path.exists(path):
        os.unlink(path)


def add(store, cid, title, text):
    store.insert_content({"id": cid, "source_id": "s1", "url": f"https://x/{cid}",
                          "title": title, "clean_text": text,
                          "content_hash": cid * 10})


def test_pipeline_stores_and_respects_the_efficiency_rule(store):
    """Section 10.2 at the LLM stage: an extracted item is never re-sent, because
    here the cost is money."""
    add(store, "a", "Visa stablecoin settlement", "stablecoin settlement rails")
    add(store, "b", "Tokenized treasuries", "tokenized treasury fund")
    first = pipeline.run(store, StubLLM())
    assert first.attempted == 2 and first.stored == 2
    second = pipeline.run(store, StubLLM())
    assert second.attempted == 0, "already-extracted items were re-sent"


def test_speculation_is_filtered_and_audited(store):
    add(store, "c", "BTC price target", "price target: will hit $200k, bull run")
    report = pipeline.run(store, StubLLM())
    assert report.speculation_filtered == 1
    assert report.stored == 0
    assert store.counts()["audit_log"] >= 1


def test_keep_speculation_flag_overrides_the_filter(store):
    add(store, "d", "BTC price target", "price target: will hit $200k, bull run")
    report = pipeline.run(store, StubLLM(), skip_speculation=False)
    assert report.stored == 1


def test_failures_are_counted_and_do_not_stop_the_run(store):
    add(store, "e", "One", "stablecoin")
    add(store, "f", "Two", "tokenized")
    report = pipeline.run(store, BoomLLM())
    assert report.attempted == 2 and report.failed == 2 and report.stored == 0


def test_prompt_version_and_model_are_recorded(store):
    """PROMPTS.md rule 4: a behaviour change must be traceable to a diff."""
    add(store, "g", "Visa stablecoin", "stablecoin settlement")
    pipeline.run(store, StubLLM())
    row = store.intelligence_for("g")
    assert row["prompt_version"] == "intelligence.v1@stub-deterministic-v1"


def test_all_six_sentiments_persist(store):
    add(store, "h", "Visa stablecoin", "stablecoin settlement")
    pipeline.run(store, StubLLM())
    row = store.intelligence_for("h")
    for dim in SENTIMENT_DIMENSIONS:
        assert f"{dim}_sentiment" in row, dim


# --- the wall-clock budget ----------------------------------------------------

class _Clock:
    """A monotonic clock the test advances by hand, so no test sleeps."""

    def __init__(self, step=0.0):
        self.now = 0.0
        self.step = step

    def __call__(self):
        value = self.now
        self.now += self.step
        return value


def _fill(store, count):
    for i in range(count):
        add(store, f"i{i}", f"Stablecoin settlement item {i}", "settlement rails")


def test_a_pass_stops_at_its_budget_and_says_what_is_left(store):
    """A pass that normally takes 20 seconds an item managed 7 items in three hours
    once the subscription started rate limiting. Without a budget the daily cycle
    has no end, and a cycle that never ends sends no brief at all."""
    _fill(store, 10)
    report = pipeline.run(store, StubLLM(), budget_seconds=90, now=_Clock(step=30.0))
    assert report.stopped_early
    assert 0 < report.attempted < 10
    assert report.remaining == 10 - report.attempted


def test_no_budget_means_no_early_stop(store):
    _fill(store, 3)
    report = pipeline.run(store, StubLLM())
    assert not report.stopped_early and report.attempted == 3


def test_a_generous_budget_completes_the_pass(store):
    _fill(store, 3)
    report = pipeline.run(store, StubLLM(), budget_seconds=3600, now=_Clock(step=1.0))
    assert not report.stopped_early and report.attempted == 3


def test_what_was_extracted_before_the_budget_is_kept(store):
    """Stopping early must not discard work: extraction is resumable precisely
    because an item already extracted is never re-sent."""
    _fill(store, 10)
    report = pipeline.run(store, StubLLM(), budget_seconds=60, now=_Clock(step=30.0))
    assert report.stored == report.attempted > 0
    assert store.counts()["intelligence"] == report.stored
