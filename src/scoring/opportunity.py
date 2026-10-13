"""Turn a scored narrative into a section 9.5 opportunity record.

The weighted sum is the one calculation the whole system turns on, so it lives here,
in Python, computed from version-pinned weights (CLAUDE.md rule 7). No model is called
in this module.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from src.scoring import relevance as rel
from src.scoring import saturation as sat
from src.scoring.weights import DIMENSIONS, ScoringConfig, load_services

# Ceiling applied when any dimension is unmeasured. Sits just under the "good"
# threshold, so an un-extracted narrative can be monitored but never promoted.
CAP_WHEN_UNMEASURED = 6.99


@dataclass
class Opportunity:
    id: str
    narrative_id: str
    narrative_name: str
    dimensions: dict[str, rel.DimensionScore]
    score_0_1: float
    score_0_10: float
    band: str
    saturation: sat.Saturation
    weights_version: int
    unmeasured: list[str] = field(default_factory=list)
    service_rank: int | None = None

    def as_row(self) -> dict[str, Any]:
        d = {k: v.value for k, v in self.dimensions.items()}
        return {
            "id": self.id,
            "narrative_id": self.narrative_id,
            "thesis": "",                     # section 17/18 LLM stage, not built
            "antier_relevance": d["antier_relevance"],
            "audience_relevance": d["audience_relevance"],
            "commercial_relevance": d["commercial_relevance"],
            "authority_potential": d["authority_potential"],
            "novelty": d["novelty"],
            "source_credibility": d["source_credibility"],
            "trend_velocity": d["trend_velocity"],
            "whitespace": self.saturation.as_text(),
            "opportunity_score": self.score_0_10,
            "persona": None,                  # section 18 LLM stage, not built
            "format": None,
            "status": self.band,
            "weights_version": str(self.weights_version),
        }


def score_narrative(narrative_id: str, narrative_name: str,
                    items: list[dict[str, Any]], momentum,
                    intelligence: dict[str, dict[str, Any]],
                    config: ScoringConfig,
                    services: dict[int, dict[str, Any]] | None = None,
                    proof_points: list[str] | None = None) -> Opportunity:
    services = services if services is not None else load_services()
    proof_points = proof_points or []

    dims = {
        "trend_velocity": rel.trend_velocity(momentum),
        "antier_relevance": rel.antier_relevance(items, services),
        "audience_relevance": rel.audience_relevance(items, services),
        "commercial_relevance": rel.commercial_relevance(items, intelligence, services),
        "authority_potential": rel.authority_potential(items, services, proof_points),
        "novelty": rel.novelty(momentum),
        "source_credibility": rel.source_credibility(momentum),
    }
    if set(dims) != set(DIMENSIONS):
        # Not an assert: asserts vanish under -O, and a weights/dimension mismatch
        # would then silently drop a dimension from the weighted sum.
        raise RuntimeError(
            "dimension mismatch: scored %s, weights expect %s"
            % (sorted(dims), sorted(DIMENSIONS))
        )

    score = sum(config.weights[name] * dims[name].value for name in DIMENSIONS)
    score_10 = round(score * 10, 2)
    unmeasured = [n for n, d in dims.items() if not d.measured]
    band = config.band(score_10)

    # A dimension we could not measure must not be allowed to produce a confident
    # band. This is the same rule saturation already follows: a missing input is not
    # a pass. Without it, an unextracted narrative with a generous fallback
    # out-ranks an extracted one -- the first live run put a forum thread
    # ("thanks, test, really, appreciate") above a Chainlink cross-chain narrative.
    if unmeasured:
        band = config.band(min(score_10, CAP_WHEN_UNMEASURED))

    return Opportunity(
        id=str(uuid.uuid4()),
        narrative_id=narrative_id,
        narrative_name=narrative_name,
        dimensions=dims,
        score_0_1=round(score, 4),
        score_0_10=score_10,
        band=band,
        saturation=sat.assess(items, config.saturation),
        weights_version=config.version,
        unmeasured=unmeasured,
        service_rank=dims["antier_relevance"].detail.get("best_rank"),
    )


def score_all(store, config: ScoringConfig,
              services: dict[int, dict[str, Any]] | None = None,
              proof_points: list[str] | None = None,
              ) -> list[tuple[Opportunity, list[dict[str, Any]]]]:
    """Score every stored narrative. Returns (opportunity, items) highest first."""
    from src.narratives import momentum as mom

    authority = store.source_authority()
    source_types = store.source_types()
    intelligence = {}
    for item in store.content_items():
        row = store.intelligence_for(item["id"])
        if row:
            intelligence[item["id"]] = row

    out = []
    for narrative in store.narratives():
        items = store.narrative_items(narrative["id"])
        if not items:
            continue
        opportunity = score_narrative(
            narrative["id"], narrative["name"], items,
            mom.compute(items, authority, source_types=source_types),
            intelligence, config, services,
            proof_points,
        )
        out.append((opportunity, items))
    out.sort(key=lambda pair: -pair[0].score_0_10)
    return out


def persist(store, opportunities: list[Opportunity]) -> None:
    """Replace the opportunities table with this run.

    Scoring is a pure function of the corpus, so a re-run supersedes rather than
    accumulates -- and because qa_reviews references opportunity ids, QA must review
    rows that are actually in the table. Reviewing in-memory scores while the table
    held an earlier run's ids was a foreign-key failure waiting to happen, and was.
    """
    store.conn.execute("DELETE FROM qa_reviews")
    store.conn.execute("DELETE FROM opportunities")
    for opportunity in opportunities:
        row = opportunity.as_row()
        cols = ", ".join(row)
        marks = ", ".join(":" + k for k in row)
        store.conn.execute(
            f"INSERT INTO opportunities ({cols}, created_at) "
            f"VALUES ({marks}, datetime('now'))", row)
    store.conn.commit()
