"""Text similarity behind an interface.

Section 12 specifies embeddings. The vertical slice uses TF-IDF cosine instead, for
the same reason the store uses SQLite: section 40 says validate the architecture
before investing, and embeddings need an API key the project does not yet have.

Clustering depends only on this Protocol, so swapping in embeddings later is a second
implementation -- not a rewrite of the clustering logic.

No sklearn: TF-IDF over a few hundred documents is twenty lines of standard library,
and CLAUDE.md rule 2 asks that a dependency justify itself.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from typing import Protocol

# Function words carrying no topical signal. Kept short on purpose: an aggressive
# list strips the domain vocabulary that distinguishes one narrative from another.
_STOPWORD_TEXT = """
a an the and or but if then than that this these those of in on at to for from by
with without about into over under again further once here there when where why how
all any both each few more most other some such no nor not only own same so too very
is are was were be been being have has had having do does did doing will would shall
should can could may might must as it its they them their we our us you your
new said says say also amid via per
"""

# Publisher boilerplate. Without these, cosine matches house writing style rather
# than subject: the first live run grouped three J.P. Morgan pages on
# "clients, demands, leveraging, issuers" and nothing else.
_BOILERPLATE_TEXT = """
cookie cookies privacy policy terms subscribe newsletter sign login register
contact careers about read more learn click here follow share linkedin twitter
copyright rights reserved disclaimer insights solutions services products
clients client customers leveraging cutting-edge harnessed manage demands
expanding announces announced announcement press release media home page site
navigation menu search language english intro feeds overview
"""

STOPWORDS = frozenset(_STOPWORD_TEXT.split()) | frozenset(_BOILERPLATE_TEXT.split())

_TOKEN = re.compile(r"[a-z][a-z0-9\-']{2,}")


def tokenize(text: str) -> list[str]:
    return [t for t in _TOKEN.findall((text or "").lower()) if t not in STOPWORDS]


class Similarity(Protocol):
    """Turn documents into vectors and compare them."""

    def fit(self, documents: list[str]) -> None:
        """Learn whatever corpus statistics the implementation needs."""

    def vector(self, document: str) -> dict[str, float]:
        """Vector for one document. Sparse, so a dict rather than a list."""

    def similarity(self, a: dict[str, float], b: dict[str, float]) -> float:
        """Cosine in [0, 1]."""

    @property
    def name(self) -> str: ...


class TfidfSimilarity:
    """TF-IDF with L2-normalised cosine.

    Deterministic: the same corpus always produces the same vectors, which matters
    because ARCHITECTURE.md puts all arithmetic outside the LLM.
    """

    def __init__(self, min_df: int = 1):
        self.min_df = min_df
        self.idf: dict[str, float] = {}
        self._n_docs = 0

    @property
    def name(self) -> str:
        return "tfidf-cosine-v1"

    def fit(self, documents: list[str]) -> None:
        self._n_docs = len(documents)
        df: Counter[str] = Counter()
        for doc in documents:
            df.update(set(tokenize(doc)))
        # Smoothed IDF: +1 on both sides keeps a term appearing in every document at
        # a small positive weight rather than exactly zero, so a one-term overlap is
        # still worth marginally more than none.
        self.idf = {
            term: math.log((1 + self._n_docs) / (1 + count)) + 1.0
            for term, count in df.items()
            if count >= self.min_df
        }

    def vector(self, document: str) -> dict[str, float]:
        counts = Counter(tokenize(document))
        if not counts:
            return {}
        most = max(counts.values())
        raw = {
            term: (0.5 + 0.5 * count / most) * self.idf[term]
            for term, count in counts.items()
            if term in self.idf
        }
        norm = math.sqrt(sum(v * v for v in raw.values()))
        if norm == 0:
            return {}
        return {term: value / norm for term, value in raw.items()}

    def similarity(self, a: dict[str, float], b: dict[str, float]) -> float:
        if not a or not b:
            return 0.0
        # Iterate the shorter vector: both are already L2-normalised, so the dot
        # product is the cosine.
        if len(b) < len(a):
            a, b = b, a
        return max(0.0, min(1.0, sum(value * b.get(term, 0.0)
                                     for term, value in a.items())))
