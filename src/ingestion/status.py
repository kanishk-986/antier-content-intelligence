"""The vocabulary of ingestion outcomes, and who can act on each.

Kept beside the code that produces these statuses rather than in the reporting
script. Three new statuses were added while fixing the listing extractor, and each
time the health report's hardcoded sets silently classified the new one as "no
guidance" -- a source would appear in the table with an empty recommendation and
nothing would say the vocabulary had moved.

`classify()` raises on an unknown status, so adding one to the pipeline without
deciding who owns it fails loudly.
"""

from __future__ import annotations

# Ours to fix: a missing listing rule, a wrong feed URL, or a bug.
ACTIONABLE = {"no_feed", "no_listing", "no_sitemap", "error"}

# Deferred by section 32: needs a headless browser (Phase 3c).
DEFERRED = {"js_rendered"}

# The publisher's decision. Section 10.2 and 33: a measured block is reported, never
# retried blindly. `blocked_transport` is a server that completes the handshake and
# then drops the connection, which is a refusal however it is dressed.
PUBLISHER_CHOICE = {"blocked", "blocked_known", "blocked_transport"}

# The stored URL does not lead to this publisher's editorial index. No listing rule
# fixes that; the registry row needs correcting or pruning.
REGISTRY_FIX = {"offsite_redirect", "not_a_listing"}

# Nothing to do.
HEALTHY = {"ok"}

GUIDANCE = {
    "actionable": "fixable here — listing rule or feed URL",
    "deferred": "needs a headless browser (Phase 3c, deferred by section 32)",
    "publisher_choice": "the publisher's choice; do not retry blindly",
    "registry_fix": "the registry URL is wrong — correct it or prune the row",
    "healthy": "",
}

_BUCKETS = (
    ("healthy", HEALTHY),
    ("actionable", ACTIONABLE),
    ("deferred", DEFERRED),
    ("publisher_choice", PUBLISHER_CHOICE),
    ("registry_fix", REGISTRY_FIX),
)

ALL_STATUSES = frozenset().union(*(s for _, s in _BUCKETS))


def classify(status: str) -> str:
    for name, members in _BUCKETS:
        if status in members:
            return name
    raise KeyError(
        f"unclassified ingestion status {status!r}. Add it to src/ingestion/status.py "
        "and decide who can act on it, or the health report will offer no guidance."
    )


def guidance(status: str) -> str:
    return GUIDANCE[classify(status)]
