"""Clustering and momentum. Offline: synthetic corpora, deterministic maths."""

import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.narratives import momentum as mom
from src.narratives.cluster import cluster_items, shared_terms, slugify
from src.narratives.similarity import STOPWORDS, TfidfSimilarity, tokenize

NOW = datetime(2026, 10, 13, 12, 0, tzinfo=timezone.utc)


def item(i, title, text, source="s1", hours_ago=1):
    return {"id": f"i{i}", "source_id": source, "title": title,
            "clean_text": text,
            "published_at": (NOW - timedelta(hours=hours_ago)).isoformat()}


# --- similarity ---------------------------------------------------------------

def test_tokenize_drops_stopwords_and_short_tokens():
    assert tokenize("The stablecoin is a rail") == ["stablecoin", "rail"]


def test_publisher_boilerplate_is_a_stopword():
    """Without this, cosine matches house style instead of subject -- the first live
    run clustered three pages on 'clients, demands, leveraging'."""
    for word in ("clients", "leveraging", "insights", "subscribe", "cookie"):
        assert word in STOPWORDS, word


def test_cosine_is_symmetric_and_bounded():
    s = TfidfSimilarity()
    s.fit(["stablecoin settlement rails", "tokenized treasury funds"])
    a, b = s.vector("stablecoin settlement rails"), s.vector("tokenized treasury funds")
    assert abs(s.similarity(a, b) - s.similarity(b, a)) < 1e-12
    assert 0.0 <= s.similarity(a, b) <= 1.0
    assert abs(s.similarity(a, a) - 1.0) < 1e-9


def test_empty_document_is_safe():
    s = TfidfSimilarity()
    s.fit(["anything at all here"])
    assert s.vector("") == {}
    assert s.similarity({}, s.vector("anything at all here")) == 0.0


def test_similarity_is_deterministic():
    """ARCHITECTURE.md: the same inputs must always produce the same numbers."""
    docs = ["stablecoin rails for banks", "banks adopt stablecoin rails"]
    runs = []
    for _ in range(3):
        s = TfidfSimilarity()
        s.fit(docs)
        runs.append(s.similarity(s.vector(docs[0]), s.vector(docs[1])))
    assert len(set(runs)) == 1


# --- clustering ---------------------------------------------------------------

def test_related_items_cluster_and_unrelated_separate():
    items = [
        item(1, "Visa expands stablecoin settlement", "stablecoin settlement banks rails"),
        item(2, "Stripe adds stablecoin settlement", "stablecoin settlement rails banks"),
        item(3, "DePIN sensors prove uptime", "depin iot sensors uptime logistics"),
    ]
    got = cluster_items(items, TfidfSimilarity(), threshold=0.05)
    sizes = sorted(n.size for n in got)
    assert sizes == [1, 2], f"expected a pair and a singleton, got {sizes}"


def test_empty_corpus_returns_no_narratives():
    assert cluster_items([], TfidfSimilarity()) == []


def test_single_item_is_its_own_narrative():
    got = cluster_items([item(1, "One story", "stablecoin")], TfidfSimilarity())
    assert len(got) == 1 and got[0].size == 1


def test_clustering_is_deterministic():
    items = [item(i, f"stablecoin settlement {i}", "stablecoin settlement rails")
             for i in range(6)]
    shapes = [tuple(sorted(n.size for n in cluster_items(items, TfidfSimilarity())))
              for _ in range(3)]
    assert len(set(shapes)) == 1


def test_narrative_tracks_distinct_sources():
    items = [item(1, "stablecoin rails", "stablecoin settlement", source="a"),
             item(2, "stablecoin rails", "stablecoin settlement", source="b")]
    got = cluster_items(items, TfidfSimilarity(), threshold=0.05)
    assert got[0].source_ids() == {"a", "b"}


def test_shared_terms_describe_the_cluster():
    items = [item(i, "tokenized treasury fund", "tokenized treasury fund custody")
             for i in range(4)]
    got = cluster_items(items, TfidfSimilarity(), threshold=0.05)
    assert any("tokenized" in t or "treasury" in t for t in shared_terms(got[0]))


def test_slugify():
    assert slugify("Stablecoins & Payments!") == "stablecoins-payments"
    assert slugify("") == "narrative"


# --- momentum -----------------------------------------------------------------

AUTH = {"s1": 10, "s2": 7}


def test_zero_baseline_records_the_rule_it_applied():
    """Section 14 leaves baseline==0 undefined; SCORING.md requires the rule be
    recorded rather than silently dividing by zero."""
    m = mom.compute([item(1, "new thing", "text")], AUTH, now=NOW)
    assert m.baseline == 0
    assert m.baseline_rule == "treat_as_emerging"
    assert m.status == "emerging"
    assert m.velocity == 1.0


def test_no_recent_items_is_declining():
    m = mom.compute([item(1, "old", "text", hours_ago=500)], AUTH, now=NOW)
    assert m.current == 0
    assert m.status == "declining"


def test_authority_coverage_uses_tiers_not_counts():
    """Section 5.2: popularity is never authority."""
    items = [item(1, "a", "x", source="s1"), item(2, "b", "y", source="s2")]
    m = mom.compute(items, AUTH, now=NOW)
    assert m.authority_coverage == 0.5          # s1 is tier 10, s2 is tier 7


def test_undated_items_are_counted_separately_not_dropped():
    items = [item(1, "dated", "x"), {"id": "i2", "source_id": "s1",
                                     "title": "undated", "clean_text": "y",
                                     "published_at": None}]
    m = mom.compute(items, AUTH, now=NOW)
    assert m.dated_items == 1
    assert m.undated_items == 1


def test_acceleration_is_zero_not_invented():
    """One snapshot cannot measure a change in velocity."""
    m = mom.compute([item(1, "a", "x")], AUTH, now=NOW)
    assert m.acceleration == 0.0


def test_novelty_decays_with_age():
    fresh = mom.compute([item(1, "a", "x", hours_ago=1)], AUTH, now=NOW)
    stale = mom.compute([item(1, "a", "x", hours_ago=160)], AUTH, now=NOW)
    assert fresh.novelty > stale.novelty
