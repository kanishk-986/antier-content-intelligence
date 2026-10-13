"""Section 16 saturation and whitespace.

A topic can score high on relevance and still be a poor opportunity if every
competitor has published the same take.

**The competitor axis is deferred by section 32**, and that matters more than it
sounds: a missing input treated as zero reads as "no saturation", which inflates every
score. So this module returns `not_measured` for that axis and never a number, and the
opportunity score excludes the dimension entirely rather than assuming a value.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class Saturation:
    competitor: str                  # always "not_measured" until a competitor set exists
    market_volume: int               # items in this narrative, the only volume we see
    antier_coverage: str             # "not_measured" until a published-content corpus exists
    verdict: str

    def as_text(self) -> str:
        return (f"competitor={self.competitor}; market_volume={self.market_volume}; "
                f"antier_coverage={self.antier_coverage}; verdict={self.verdict}")


def assess(items: list[dict[str, Any]], config_saturation: dict[str, Any]) -> Saturation:
    competitor = str(config_saturation.get("competitor_axis", "not_measured"))
    volume = len(items)

    # Section 16's matrix needs demand and saturation. We can observe demand (how many
    # sources carried it) and not saturation, so the verdict says which half is known.
    if competitor != "not_measured":
        verdict = "competitor axis available; implement the full section 16 matrix"
    elif volume >= 5:
        verdict = "high market volume, saturation unknown — needs a competitor set"
    elif volume >= 2:
        verdict = "moderate market volume, saturation unknown"
    else:
        verdict = "single-source signal, saturation unknown"

    return Saturation(competitor=competitor, market_volume=volume,
                      antier_coverage="not_measured", verdict=verdict)
