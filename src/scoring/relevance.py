"""The seven section 15 dimensions.

Every function returns a float in [0, 1] and is **deterministic** (CLAUDE.md rule 7):
the same narrative, items and config always produce the same number. Where a
dimension depends on model judgement, it consumes a stored `intelligence` row rather
than calling a model here -- so scoring is reproducible and auditable, and a score can
be recomputed from the database without spending anything.

Each function documents which inputs it uses and what it does when they are absent,
because "no data" and "scored zero" are different facts and SCORING.md requires they
not be conflated.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from src.narratives.similarity import tokenize

# Charter priority -> multiplier. Ranks 1-3 are "very high" (section 3.1) and are the
# strongest pass in Test 1; 4-8 pass but weaker.
PRIORITY_WEIGHT = {"very_high": 1.0, "high": 0.75}
RANK_FLOOR = 0.45          # a rank 4-8 match still maps to a real offering


@dataclass
class DimensionScore:
    value: float
    basis: str                       # how it was derived, for the audit trail
    measured: bool = True            # False when the input was absent
    detail: dict[str, Any] = field(default_factory=dict)


def _narrative_text(items: list[dict[str, Any]]) -> str:
    parts = []
    for item in items:
        parts.append(item.get("title") or "")
        parts.append((item.get("clean_text") or "")[:600])
    return " ".join(parts)


def service_match(items: list[dict[str, Any]],
                  services: dict[int, dict[str, Any]]) -> list[tuple[int, int]]:
    """(rank, weighted signal hits) per service the narrative touches, best first.

    A hit in a **title** counts double. Body text is long enough that a stray
    "payment" in a forum signature matches a service signal; a title is what the
    item is actually about. The first live run scored a support thread
    ("thanks, test, really, appreciate") 0.68 on stablecoin rails purely on body
    noise, which is what motivated the weighting.
    """
    titles = " ".join(sorted(set(tokenize(" ".join(
        (i.get("title") or "") for i in items)))))
    body = " ".join(sorted(set(tokenize(_narrative_text(items)))))
    hits = []
    for rank, svc in services.items():
        matched = 0
        for sig in svc["signals"]:
            if sig in titles:
                matched += 2
            elif sig in body:
                matched += 1
        if matched:
            hits.append((rank, matched))
    return sorted(hits, key=lambda rh: (-rh[1], rh[0]))


def antier_relevance(items, services) -> DimensionScore:
    """Test 1, service rank. Does the topic map to an actual capability?

    Signal matching against config/brand/services.yaml. A narrative matching no
    service scores 0 and says so -- there is nothing Antier could be hired to do
    about it.
    """
    hits = service_match(items, services)
    if not hits:
        return DimensionScore(0.0, "no service signal matched", detail={"ranks": []})
    best_rank, best_hits = hits[0]
    priority = services[best_rank].get("priority", "high")
    base = PRIORITY_WEIGHT.get(priority, RANK_FLOOR)
    # Breadth of evidence, capped: one weak keyword is not a capability match, and
    # fifty is not ten times more convincing than five. Weighted hits, so the floor
    # is effectively "one title hit or two body hits".
    confidence = min(1.0, best_hits / 6.0)
    # Body-only evidence cannot reach a full capability claim.
    title_evidence = best_hits >= 2
    value = base * (0.35 + 0.65 * confidence)
    if not title_evidence:
        value *= 0.5
    value = round(value, 3)
    return DimensionScore(
        value, f"service {best_rank} ({priority}), {best_hits} signal(s)",
        detail={"ranks": [r for r, _ in hits], "best_rank": best_rank},
    )


def audience_relevance(items, services) -> DimensionScore:
    """Test 2 input. Does it matter to the named ICPs?

    An ICP named in the text is direct evidence; otherwise the matched service's own
    ICPs are the indirect signal, since a service exists for its buyer.
    """
    text = _narrative_text(items).lower()
    hits = service_match(items, services)
    if not hits:
        return DimensionScore(0.0, "no service, so no ICP")
    named = []
    for rank, _ in hits:
        for icp in services[rank]["icps"]:
            head = icp.split("/")[0].strip().lower()
            if head and head in text:
                named.append(icp)
    if named:
        value = round(min(1.0, 0.6 + 0.2 * len(set(named))), 3)
        return DimensionScore(value, f"ICP named: {', '.join(sorted(set(named))[:3])}",
                              detail={"icps": sorted(set(named))})
    return DimensionScore(0.45, "service matched but no ICP named in the text",
                          detail={"icps": []})


def commercial_relevance(items, intelligence: dict[str, dict[str, Any]],
                         services) -> DimensionScore:
    """Can it create meaningful business context?

    Uses the model's `business_implication` and importance where extraction has run.
    Falls back to service priority, and reports which basis it used -- an unextracted
    narrative must not look the same as one judged commercially thin.
    """
    extracted = [intelligence[i["id"]] for i in items if i["id"] in intelligence]
    hits = service_match(items, services)
    priority_base = (
        PRIORITY_WEIGHT.get(services[hits[0][0]].get("priority", "high"), RANK_FLOOR)
        if hits else 0.0
    )
    if not extracted:
        return DimensionScore(
            round(priority_base * 0.6, 3),
            "no intelligence yet; service priority only", measured=False,
        )
    importances = [float(r.get("importance_score") or 0.0) for r in extracted]
    mean = sum(importances) / len(importances)
    # Multiplicative, not an average. Averaging let service priority floor the score:
    # a Richmond Fed economics paper the model rated 0.10 still scored 0.55 and
    # out-ranked a Chainlink cross-chain narrative. Priority now scales the model's
    # judgement instead of substituting for it, so an unimportant item in a
    # high-priority service stays unimportant.
    value = round(priority_base * (0.25 + 0.75 * mean), 3)
    return DimensionScore(
        value, f"mean importance {mean:.2f} over {len(extracted)} extracted item(s)",
        detail={"extracted": len(extracted), "of": len(items)},
    )


def authority_potential(items, services, proof_points: list[str]) -> DimensionScore:
    """Can Antier add expert insight?

    Service priority, lifted when the narrative touches something Antier has actually
    shipped. The proof-point list is deliberately short (no case-study corpus exists
    yet, PRD section 12), so this dimension is capped until one does.
    """
    hits = service_match(items, services)
    if not hits:
        return DimensionScore(0.0, "no service, so no authority claim")
    base = PRIORITY_WEIGHT.get(services[hits[0][0]].get("priority", "high"), RANK_FLOOR)
    text = _narrative_text(items).lower()
    matched = [p for p in proof_points
               if sum(1 for w in tokenize(p) if w in text) >= 2]
    if matched:
        return DimensionScore(round(min(1.0, base + 0.2), 3),
                              f"proof point: {matched[0][:50]}",
                              detail={"proof_points": matched})
    return DimensionScore(round(base * 0.7, 3),
                          "service priority only; no proof point matched",
                          detail={"proof_points": []})


def novelty(momentum) -> DimensionScore:
    """Is there a differentiated angle? Proxied by recency until the section 17
    contrarian-angle agent exists, which is an LLM stage not yet built."""
    return DimensionScore(round(float(momentum.novelty), 3),
                          f"recency proxy (novelty={momentum.novelty})",
                          detail={"proxy": "recency"})


def source_credibility(momentum) -> DimensionScore:
    """Can the topic be evidenced reliably? Registry tiers, never volume (section
    5.2) — and never a primary party's account of itself.

    Section 14's `authority_coverage` answers "how authoritative are these sources",
    on which a vendor's own newsroom scores top marks by design (tier 10 includes
    primary company and protocol announcements). Section 15 asks something else:
    whether the topic "can be evidenced reliably". Fifteen Chainlink and Ondo press
    releases are authoritative and corroborate nothing, so this dimension reads the
    independence-corrected figure instead.

    That alone misses concentration: three items from one regulator's newsroom score
    full coverage, because that regulator genuinely is independent. So the figure is
    scaled by publisher breadth — how many distinct publishers carried the narrative.
    Three is treated as full corroboration and one is floored, not zeroed, because a
    single regulator's publication is still evidence."""
    coverage = getattr(momentum, "independent_authority_coverage",
                       momentum.authority_coverage)
    breadth = getattr(momentum, "publisher_breadth", 1.0)
    publishers = getattr(momentum, "distinct_publishers", None)
    value = coverage * breadth

    reason = f"independent authority coverage {coverage}"
    self_reported = getattr(momentum, "self_reported_sources", 0)
    if self_reported:
        reason += (f" ({self_reported} of "
                   f"{self_reported + getattr(momentum, 'independent_sources', 0)}"
                   " sources are primary parties, discounted)")
    if publishers is not None and breadth < 1.0:
        reason += (f", x{breadth} breadth ({publishers} publisher"
                   f"{'' if publishers == 1 else 's'})")
    return DimensionScore(
        round(float(value), 3), reason,
        detail={"tier_based": True,
                "authority_coverage": momentum.authority_coverage,
                "independent_authority_coverage": coverage,
                "independence": getattr(momentum, "independence", None),
                "self_reported_sources": self_reported,
                "distinct_publishers": publishers,
                "max_publisher_share": getattr(momentum, "max_publisher_share", None),
                "publisher_breadth": breadth})


def trend_velocity(momentum) -> DimensionScore:
    """Is attention increasing? Normalised: velocity is an unbounded ratio, and the
    weighted score needs [0, 1]. 2x or better saturates."""
    raw = float(momentum.velocity)
    value = round(min(1.0, raw / 2.0), 3)
    basis = f"velocity {raw}"
    if momentum.baseline_rule != "ratio":
        basis += f" via {momentum.baseline_rule}"
    return DimensionScore(value, basis,
                          detail={"raw_velocity": raw,
                                  "baseline_rule": momentum.baseline_rule})
