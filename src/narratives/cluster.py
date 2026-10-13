"""Cluster content items into narratives.

Section 12: the system should not rank articles. 100 items become 10-20 narratives --
several separate stories about Visa, Stripe, banks and stablecoin settlement are one
narrative about stablecoins becoming payment infrastructure.

Average-link agglomerative clustering. Chosen over single-link because single-link
chains: one article mentioning both stablecoins and DePIN would merge two unrelated
narratives. Average-link requires a candidate to resemble the cluster as a whole.
Deterministic -- items are processed in a stable order, so the same corpus always
yields the same clusters (ARCHITECTURE.md determinism boundary).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from src.narratives.similarity import Similarity, tokenize

# Above this, two items belong to the same narrative.
#
# Tuned by sweeping a 148-item live corpus, not guessed. TF-IDF cosine on titles plus
# ledes yields much lower absolute similarities than intuition suggests, and the first
# attempt at 0.28 produced 130 narratives from 148 items with **zero** cross-source
# clusters -- it was grouping by publisher, which is the opposite of section 12.
#
#   thr   narratives  largest  cross-source
#   0.03      26         23        15        <- largest cluster starts to blob
#   0.04      31         17        16
#   0.05      40         15        16        <- chosen
#   0.06      47         10        12
#   0.08      63         10         7
#   0.28     130          8         0        <- original guess
#
# Section 12 wants 10-20 narratives from ~100 items. This corpus spans all eight
# charter services rather than one theme, so 40 is the honest analogue; forcing it
# lower merges unrelated services. Embeddings should separate similarities better and
# allow a higher, more stable threshold -- which is what the Similarity interface is
# for.
DEFAULT_THRESHOLD = 0.05
MIN_CLUSTER_SIZE = 1


@dataclass
class Narrative:
    items: list[dict[str, Any]] = field(default_factory=list)
    vectors: list[dict[str, float]] = field(default_factory=list)
    name: str = ""
    description: str = ""

    @property
    def size(self) -> int:
        return len(self.items)

    def source_ids(self) -> set[str]:
        return {i["source_id"] for i in self.items}


# Chars of body to use. The lede carries the subject; the rest of a 4,000-character
# article carries the publisher's voice, which is what made the first run cluster by
# source instead of topic.
LEDE_CHARS = 600


def _document(item: dict[str, Any]) -> str:
    """What to cluster on: the title, weighted, plus the lede.

    Title repetition is deliberate -- it is the most topical text available, and
    without weighting even a short body drowns it.
    """
    title = item.get("title") or ""
    lede = (item.get("clean_text") or "")[:LEDE_CHARS]
    return f"{title} {title} {title} {lede}"


def cluster_items(items: list[dict[str, Any]], similarity: Similarity,
                  threshold: float = DEFAULT_THRESHOLD) -> list[Narrative]:
    """Group items into narratives. Returns largest first."""
    if not items:
        return []

    ordered = sorted(items, key=lambda i: (i.get("published_at") or "", i["id"]))
    documents = [_document(i) for i in ordered]
    similarity.fit(documents)
    vectors = [similarity.vector(d) for d in documents]

    narratives: list[Narrative] = []
    for item, vector in zip(ordered, vectors, strict=True):
        best, best_score = None, 0.0
        for narrative in narratives:
            # Average link: resemble the cluster, not just its closest member.
            scores = [similarity.similarity(vector, v) for v in narrative.vectors]
            mean = sum(scores) / len(scores)
            if mean > best_score:
                best, best_score = narrative, mean
        if best is not None and best_score >= threshold:
            best.items.append(item)
            best.vectors.append(vector)
        else:
            narratives.append(Narrative(items=[item], vectors=[vector]))

    for narrative in narratives:
        narrative.name, narrative.description = describe(narrative, similarity)
    narratives.sort(key=lambda n: (-n.size, n.name))
    return [n for n in narratives if n.size >= MIN_CLUSTER_SIZE]


def describe(narrative: Narrative, similarity: Similarity) -> tuple[str, str]:
    """A provisional name from the cluster's highest-weight shared terms.

    Deliberately mechanical. Section 12 wants a readable narrative name, and
    PROMPTS.md reserves naming for an LLM stage; until that exists this is a label,
    not a thesis, and should read as one.
    """
    weights: dict[str, float] = {}
    for vector in narrative.vectors:
        for term, value in vector.items():
            weights[term] = weights.get(term, 0.0) + value
    top = sorted(weights, key=lambda t: -weights[t])[:6]
    name = ", ".join(top[:4]) if top else "unnamed"

    titles = [i.get("title") or "" for i in narrative.items if i.get("title")]
    sample = "; ".join(t[:70] for t in titles[:3])
    return name, f"{narrative.size} item(s). e.g. {sample}"


def shared_terms(narrative: Narrative, limit: int = 8) -> list[str]:
    """Terms appearing in most of a cluster's items -- what actually unites it."""
    counts: dict[str, int] = {}
    for item in narrative.items:
        for term in set(tokenize(_document(item))):
            counts[term] = counts.get(term, 0) + 1
    floor = max(2, int(narrative.size * 0.6))
    common = [t for t, c in counts.items() if c >= floor]
    return sorted(common, key=lambda t: -counts[t])[:limit]


def slugify(text: str, limit: int = 60) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return slug[:limit] or "narrative"
