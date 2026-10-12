"""Weights are configuration that changes behaviour, so they are tested."""

import os
import re

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEIGHTS = os.path.join(REPO, "config", "scoring", "weights.yaml")

EXPECTED = {           # SCORING.md, from blueprint section 15
    "trend_velocity": 0.20,
    "antier_relevance": 0.20,
    "audience_relevance": 0.15,
    "commercial_relevance": 0.15,
    "authority_potential": 0.10,
    "novelty": 0.10,
    "source_credibility": 0.10,
}


def read_weights():
    with open(WEIGHTS) as fh:
        return fh.read()


def load_opportunity_weights():
    text = read_weights()
    block = text.split("opportunity_weights:")[1].split("\n\n")[0]
    return {
        k: float(v)
        for k, v in re.findall(r"^\s{2}(\w+):\s+([0-9.]+)", block, re.M)
    }


def test_weights_sum_to_one():
    """A mismatch must be a startup error, never a silent renormalization."""
    assert abs(sum(load_opportunity_weights().values()) - 1.0) < 1e-9


def test_all_seven_dimensions_present_with_blueprint_values():
    assert load_opportunity_weights() == EXPECTED


def test_thresholds_are_ordered():
    text = read_weights()
    block = text.split("thresholds:")[1].split("\n\n")[0]
    found = [float(v) for _, v in re.findall(r"^\s{2}(\w+):\s+([0-9.]+)", block, re.M)]
    assert found == sorted(found), (
        "thresholds must ascend: reject < monitor < good < priority < immediate"
    )


def test_competitor_saturation_is_not_measured_not_zero():
    """A missing input read as 'no saturation' would inflate every score."""
    assert "competitor_axis: not_measured" in read_weights()
