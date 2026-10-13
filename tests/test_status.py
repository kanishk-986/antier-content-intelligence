"""The ingestion status vocabulary. Every status the pipeline can emit must have an
owner, or the health report silently offers no guidance on it."""

import os
import re
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.ingestion import status as st

SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")


def _emitted_statuses() -> set[str]:
    """Every string literal assigned to a status field in the ingestion code."""
    found = set()
    patterns = (
        re.compile(r'out\.status\s*=\s*"([a-z_]+)"'),
        re.compile(r'out\.status,\s*out\.detail\s*=\s*"([a-z_]+)"'),
        re.compile(r'outcome\.status\s*=\s*"([a-z_]+)"'),
        re.compile(r'"status":\s*"([a-z_]+)"'),
        re.compile(r'return\s+"([a-z_]+)",\s*text\['),
        re.compile(r'ListingOutcome\([^)]*"([a-z_]+)"\)'),
    )
    for name in ("listing.py", "fetcher.py", "pipeline.py"):
        with open(os.path.join(SRC, "ingestion", name)) as fh:
            body = fh.read()
        for pattern in patterns:
            found.update(pattern.findall(body))
    return found


def test_every_emitted_status_is_classified():
    """Three statuses were added while fixing the listing extractor. Each time, the
    health report's hardcoded sets classified the new one as "no guidance"."""
    emitted = _emitted_statuses()
    assert emitted, "the scan found nothing; the patterns are stale"
    unclassified = sorted(s for s in emitted if s not in st.ALL_STATUSES)
    assert not unclassified, (
        f"emitted but unclassified: {unclassified}. Add each to "
        "src/ingestion/status.py and decide who can act on it."
    )


def test_an_unknown_status_fails_loudly():
    with pytest.raises(KeyError, match="unclassified"):
        st.classify("something_new")


def test_the_buckets_do_not_overlap():
    """A status in two buckets would get whichever guidance came first."""
    seen: set[str] = set()
    for members in (st.HEALTHY, st.ACTIONABLE, st.DEFERRED,
                    st.PUBLISHER_CHOICE, st.REGISTRY_FIX):
        assert not (seen & members), f"overlap at {seen & members}"
        seen |= members


def test_every_bucket_has_guidance():
    for status in st.ALL_STATUSES:
        st.guidance(status)      # raises on a bucket missing from GUIDANCE


@pytest.mark.parametrize("status,bucket", [
    ("ok", "healthy"),
    ("no_feed", "actionable"),
    ("js_rendered", "deferred"),
    ("blocked_transport", "publisher_choice"),
    ("offsite_redirect", "registry_fix"),
    ("not_a_listing", "registry_fix"),
])
def test_known_statuses_land_in_the_right_bucket(status, bucket):
    assert st.classify(status) == bucket
