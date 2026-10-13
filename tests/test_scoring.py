"""Section 15 scoring. Deterministic arithmetic, so it is fully testable offline."""

import os
import sys
from dataclasses import dataclass

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.scoring import relevance as rel
from src.scoring import saturation as sat
from src.scoring import weights as wcfg
from src.scoring.opportunity import CAP_WHEN_UNMEASURED, score_narrative

CONFIG = wcfg.load()
SERVICES = wcfg.load_services()


@dataclass
class FakeMomentum:
    velocity: float = 1.0
    novelty: float = 0.5
    authority_coverage: float = 1.0
    independent_authority_coverage: float = 1.0
    independence: float = 1.0
    independent_sources: int = 1
    self_reported_sources: int = 0
    distinct_publishers: int = 3
    max_publisher_share: float = 0.34
    publisher_breadth: float = 1.0
    baseline_rule: str = "ratio"


def item(i, title, text="", source="s1"):
    return {"id": f"i{i}", "source_id": source, "title": title, "clean_text": text}


# --- config -------------------------------------------------------------------

def test_weights_must_sum_to_one(tmp_path):
    """A silent rescale would make two runs incomparable with nothing saying so."""
    bad = tmp_path / "w.yaml"
    bad.write_text(
        "version: 1\nopportunity_weights:\n"
        + "".join(f"  {d}: 0.5\n" for d in wcfg.DIMENSIONS)
        + "thresholds:\n  reject: 0.0\n"
    )
    with pytest.raises(wcfg.ConfigError) as exc:
        wcfg.load(str(bad))
    assert "sum to" in str(exc.value)


def test_missing_dimension_is_an_error(tmp_path):
    bad = tmp_path / "w.yaml"
    bad.write_text("version: 1\nopportunity_weights:\n  novelty: 1.0\n"
                   "thresholds:\n  reject: 0.0\n")
    with pytest.raises(wcfg.ConfigError) as exc:
        wcfg.load(str(bad))
    assert "missing dimensions" in str(exc.value)


def test_unknown_dimension_is_an_error(tmp_path):
    bad = tmp_path / "w.yaml"
    body = "".join(f"  {d}: {1/7:.6f}\n" for d in wcfg.DIMENSIONS)
    bad.write_text(f"version: 1\nopportunity_weights:\n{body}  vibes: 0.0\n"
                   "thresholds:\n  reject: 0.0\n")
    with pytest.raises(wcfg.ConfigError) as exc:
        wcfg.load(str(bad))
    assert "unknown" in str(exc.value)


@pytest.mark.parametrize("score,band", [
    (9.5, "immediate_editorial"), (8.0, "priority"), (7.0, "good"),
    (5.0, "monitor"), (4.9, "reject"), (0.0, "reject"),
])
def test_threshold_bands(score, band):
    assert CONFIG.band(score) == band


# --- dimensions ---------------------------------------------------------------

def test_no_service_match_scores_zero_and_says_why():
    """Nothing Antier could be hired to do about it."""
    got = rel.antier_relevance([item(1, "Local football results")], SERVICES)
    assert got.value == 0.0
    assert "no service signal" in got.basis


def test_title_evidence_outranks_body_noise():
    """A stray 'payment' in a forum signature is not a capability match. The first
    live run scored a support thread 0.68 on stablecoin rails from body noise alone."""
    titled = rel.antier_relevance(
        [item(1, "Stablecoin settlement rails for regional banks")], SERVICES)
    body_only = rel.antier_relevance(
        [item(2, "Thanks, test, really appreciate it",
              "my payment went through fine")], SERVICES)
    assert titled.value > body_only.value * 2


def test_relevance_is_bounded():
    got = rel.antier_relevance(
        [item(1, "stablecoin tokeniz rwa agent payment settle custod audit mica")],
        SERVICES)
    assert 0.0 <= got.value <= 1.0


def test_named_icp_beats_an_unnamed_one():
    named = rel.audience_relevance(
        [item(1, "Stablecoin rails for regional banks and NBFCs")], SERVICES)
    unnamed = rel.audience_relevance(
        [item(2, "Stablecoin settlement expands")], SERVICES)
    assert named.value > unnamed.value


def test_commercial_relevance_without_intelligence_is_marked_unmeasured():
    """'No data' and 'scored low' are different facts."""
    got = rel.commercial_relevance([item(1, "Stablecoin rails")], {}, SERVICES)
    assert got.measured is False
    assert "no intelligence" in got.basis


def test_commercial_relevance_uses_stored_importance():
    intel = {"i1": {"importance_score": 0.9}}
    high = rel.commercial_relevance([item(1, "Stablecoin rails")], intel, SERVICES)
    low = rel.commercial_relevance([item(1, "Stablecoin rails")],
                                   {"i1": {"importance_score": 0.1}}, SERVICES)
    assert high.measured and high.value > low.value


def test_velocity_is_normalised_into_range():
    assert rel.trend_velocity(FakeMomentum(velocity=10.0)).value == 1.0
    assert rel.trend_velocity(FakeMomentum(velocity=0.0)).value == 0.0


def test_velocity_basis_records_a_zero_baseline_rule():
    got = rel.trend_velocity(FakeMomentum(baseline_rule="treat_as_emerging"))
    assert "treat_as_emerging" in got.basis


def test_source_credibility_comes_from_tiers_not_volume():
    """Section 5.2: popularity is never authority."""
    m = FakeMomentum(authority_coverage=0.25, independent_authority_coverage=0.25)
    assert rel.source_credibility(m).value == 0.25


def test_source_credibility_reads_the_independence_corrected_figure():
    """A vendor's own newsroom is tier 9 and corroborates nothing. The dimension
    asks whether the topic can be evidenced, so it must not read the raw figure."""
    m = FakeMomentum(authority_coverage=1.0, independent_authority_coverage=0.35,
                     independence=0.0, independent_sources=0, self_reported_sources=3)
    dim = rel.source_credibility(m)
    assert dim.value == 0.35
    assert "3 of 3 sources are primary parties" in dim.basis
    assert dim.detail["authority_coverage"] == 1.0, "raw figure stays visible"


# --- saturation ---------------------------------------------------------------

def test_competitor_axis_is_never_a_number():
    """A missing input read as 0 means 'no saturation', which inflates every score."""
    got = sat.assess([item(1, "x")], CONFIG.saturation)
    assert got.competitor == "not_measured"
    assert got.antier_coverage == "not_measured"
    assert "saturation unknown" in got.verdict


# --- opportunity --------------------------------------------------------------

def _score(items, intel=None, momentum=None):
    return score_narrative("n1", "test narrative", items, momentum or FakeMomentum(),
                           intel or {}, CONFIG, SERVICES, ["stablecoin remittance platform"])


def test_weighted_sum_matches_the_weights():
    o = _score([item(1, "Stablecoin settlement for regional banks")])
    expected = sum(CONFIG.weights[k] * v.value for k, v in o.dimensions.items())
    assert abs(o.score_0_1 - round(expected, 4)) < 1e-9
    assert abs(o.score_0_10 - round(expected * 10, 2)) < 1e-9


def test_all_seven_dimensions_are_scored():
    o = _score([item(1, "Stablecoin rails")])
    assert set(o.dimensions) == set(wcfg.DIMENSIONS)


def test_unmeasured_dimension_caps_the_band():
    """An un-extracted narrative may be monitored, never promoted. Without this a
    generous fallback let junk out-rank a real narrative."""
    o = _score([item(1, "Stablecoin settlement rails for regional banks and NBFCs")])
    assert "commercial_relevance" in o.unmeasured
    assert o.band in ("monitor", "reject")
    assert CONFIG.band(o.score_0_10) != o.band or o.score_0_10 <= CAP_WHEN_UNMEASURED


def test_measured_narrative_is_not_capped():
    intel = {"i1": {"importance_score": 0.95}}
    o = _score([item(1, "Stablecoin settlement rails for regional banks and NBFCs")],
               intel=intel, momentum=FakeMomentum(velocity=2.0, novelty=1.0))
    assert o.unmeasured == []
    assert o.band == CONFIG.band(o.score_0_10)


def test_scoring_is_deterministic():
    items = [item(1, "Stablecoin settlement rails")]
    scores = {_score(items).score_0_10 for _ in range(5)}
    assert len(scores) == 1


def test_row_carries_the_weights_version_for_traceability():
    row = _score([item(1, "Stablecoin rails")]).as_row()
    assert row["weights_version"] == str(CONFIG.version)
    assert "not_measured" in row["whitespace"]


def test_thesis_and_persona_are_empty_not_invented():
    """Sections 17 and 18 are LLM stages that are not built; leaving them blank is
    honest, filling them would be fabrication."""
    row = _score([item(1, "Stablecoin rails")]).as_row()
    assert row["thesis"] == ""
    assert row["persona"] is None


def test_credibility_is_scaled_by_publisher_breadth():
    """The gap QA caught deterministically: one independent publisher carrying three
    items scored full credibility because that publisher really is independent."""
    one = FakeMomentum(independent_authority_coverage=1.0, publisher_breadth=0.667,
                       distinct_publishers=1)
    three = FakeMomentum(independent_authority_coverage=1.0, publisher_breadth=1.0,
                         distinct_publishers=3)
    assert rel.source_credibility(one).value == 0.667
    assert rel.source_credibility(three).value == 1.0
    assert "1 publisher)" in rel.source_credibility(one).basis


def test_the_two_corrections_compound():
    """A single vendor newsroom is both self-reported and concentrated."""
    m = FakeMomentum(authority_coverage=1.0, independent_authority_coverage=0.35,
                     self_reported_sources=1, independent_sources=0,
                     publisher_breadth=0.667, distinct_publishers=1)
    dim = rel.source_credibility(m)
    assert dim.value == 0.233
    assert "primary parties" in dim.basis and "breadth" in dim.basis


def test_breadth_absent_leaves_the_figure_alone():
    """An older momentum object must not be silently zeroed by a missing field."""
    @dataclass
    class Old:
        authority_coverage: float = 0.8
        independent_authority_coverage: float = 0.8
    assert rel.source_credibility(Old()).value == 0.8
