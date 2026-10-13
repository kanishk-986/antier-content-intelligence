"""Load and validate scoring configuration.

Weights are version-controlled because they materially change behaviour (section
7.2). A weight set that does not sum to 1.0 is a startup error, never a silent
renormalization -- SCORING.md requires that, because quietly rescaling would make two
runs incomparable without anything in the output saying so.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import yaml

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
WEIGHTS_PATH = os.path.join(REPO, "config", "scoring", "weights.yaml")
SERVICES_PATH = os.path.join(REPO, "config", "brand", "services.yaml")

DIMENSIONS = (
    "trend_velocity", "antier_relevance", "audience_relevance",
    "commercial_relevance", "authority_potential", "novelty", "source_credibility",
)


class ConfigError(ValueError):
    pass


@dataclass
class ScoringConfig:
    version: int
    weights: dict[str, float]
    thresholds: dict[str, float]
    saturation: dict[str, Any]

    def band(self, score_0_10: float) -> str:
        """Action band for a 0-10 score (section 15 thresholds)."""
        ordered = sorted(self.thresholds.items(), key=lambda kv: -kv[1])
        for name, floor in ordered:
            if score_0_10 >= floor:
                return name
        return "reject"


def load(weights_path: str = WEIGHTS_PATH) -> ScoringConfig:
    with open(weights_path) as fh:
        raw = yaml.safe_load(fh) or {}

    weights = raw.get("opportunity_weights") or {}
    missing = [d for d in DIMENSIONS if d not in weights]
    if missing:
        raise ConfigError(f"weights missing dimensions: {', '.join(missing)}")
    extra = [k for k in weights if k not in DIMENSIONS]
    if extra:
        raise ConfigError(f"weights has unknown dimensions: {', '.join(extra)}")
    total = sum(float(v) for v in weights.values())
    if abs(total - 1.0) > 1e-9:
        raise ConfigError(
            f"weights sum to {total}, not 1.0 — fix weights.yaml rather than "
            "letting the scorer rescale silently"
        )

    thresholds = raw.get("thresholds") or {}
    if not thresholds:
        raise ConfigError("thresholds missing")

    return ScoringConfig(
        version=int(raw.get("version", 0)),
        weights={k: float(v) for k, v in weights.items()},
        thresholds={k: float(v) for k, v in thresholds.items()},
        saturation=raw.get("saturation") or {},
    )


def load_services(path: str = SERVICES_PATH) -> dict[int, dict[str, Any]]:
    with open(path) as fh:
        return (yaml.safe_load(fh) or {})["services"]
