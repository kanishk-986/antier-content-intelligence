"""The registry is parsed configuration, so parsing is tested."""

import csv
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "scripts"))

from import_source_registry import (  # noqa: E402
    COLUMNS, DEFAULT_TIER, build_rows, classify, normalise_url,
)

REGISTRY = os.path.join(REPO, "config", "sources", "source_registry.csv")


def rows():
    with open(REGISTRY) as fh:
        return list(csv.DictReader(fh))


def test_registry_has_the_blueprint_columns():
    """Section 5.1 column set, exactly."""
    with open(REGISTRY) as fh:
        assert next(csv.reader(fh)) == COLUMNS


def test_every_source_has_a_url_and_an_id():
    for row in rows():
        assert row["source_id"].startswith("src-")
        assert row["url"].startswith("http"), row


def test_source_ids_are_unique():
    ids = [r["source_id"] for r in rows()]
    assert len(ids) == len(set(ids))


def test_urls_are_deduplicated():
    urls = [r["url"].rstrip("/").lower() for r in rows()]
    assert len(urls) == len(set(urls))


def test_authority_scores_are_valid_tiers():
    valid = {10, 9, 8, 7, 5, 3, 1}      # section 5.2
    for row in rows():
        assert int(row["authority_score"]) in valid, row


def test_bare_domains_become_fetchable():
    """The Generic tab carries bare domains; SOURCE_POLICY requires working URLs."""
    assert normalise_url("mckinsey.com") == "https://mckinsey.com"
    assert normalise_url("https://bis.org") == "https://bis.org"
    assert normalise_url("") == ""


def test_regulators_outrank_specialist_blogs():
    assert classify("International Monetary Fund", "https://imf.org")[0] == 10
    assert classify("Teroxx", "https://teroxx.com/research")[0] == 7


def test_wef_is_not_classified_a_regulator():
    """A convening body must not inherit regulator authority (section 5.2)."""
    score, stype = classify("World Economic Forum (WEF)", "https://weforum.org")
    assert stype != "regulator"
    assert score == 9


def test_unknown_source_is_flagged_not_silently_trusted():
    score, stype = classify("Some Random Blog", "https://example-unknown-source.xyz")
    assert score == DEFAULT_TIER
    assert stype == "unclassified"


def test_blocked_sources_are_annotated():
    """A bot-block must never read as an empty feed."""
    blocked = [r for r in rows() if "BLOCKED" in r["notes"]]
    assert blocked, "expected the measured-blocked sources to be annotated"
    assert any("dune.com" in r["url"] for r in blocked)


def test_header_rows_are_not_imported_as_sources():
    names = [r["source_name"].lower() for r in rows()]
    assert "company / entity name" not in names
    assert not any(n.startswith("s.no") for n in names)


def test_empty_sheet_yields_no_rows_rather_than_junk():
    assert build_rows("===== SHEET: Specific People =====\nName | Profile Link\n") == []
