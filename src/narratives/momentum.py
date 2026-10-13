"""Trend and momentum per section 14.

All arithmetic, no LLM (ARCHITECTURE.md determinism boundary):

    trend_velocity     = current_mentions / baseline_mentions
    acceleration       = change_in_velocity
    authority_coverage = weighted authoritative sources / total sources
    emergence          = velocity + acceleration + novelty + source_diversity

`authority_coverage` is section 14's figure, untouched. Section 15's
`source_credibility` instead reads `independent_authority_coverage`, which discounts
a primary party reporting on itself — see `source_independence` in weights.yaml.

Windows come from config/scoring/weights.yaml (24h / 7d / 30d) so a breaking event is
distinguishable from a durable narrative.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import yaml

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
WEIGHTS = os.path.join(REPO, "config", "scoring", "weights.yaml")

# Section 5.2 calls tier 8 and above authoritative: regulators, major institutions,
# established research firms. Below that is community and secondary commentary.
AUTHORITATIVE_FLOOR = 8

# Fallback only; the real values come from weights.yaml so a change is a config diff.
PRIMARY_PARTY_TYPES = ("protocol", "primary_company")
SELF_REPORTED_WEIGHT = 0.35
TARGET_PUBLISHERS = 3
SINGLE_PUBLISHER_FLOOR = 0.5


@dataclass
class Momentum:
    current: int
    baseline: int
    velocity: float
    acceleration: float
    authority_coverage: float
    independent_authority_coverage: float
    independence: float
    independent_sources: int
    self_reported_sources: int
    source_diversity: float
    distinct_publishers: int
    max_publisher_share: float
    publisher_breadth: float
    novelty: float
    emergence: float
    status: str                 # emerging | rising | stable | declining
    baseline_rule: str          # which zero-baseline rule applied (SCORING.md)
    dated_items: int
    undated_items: int


def load_windows(path: str = WEIGHTS) -> list[int]:
    with open(path) as fh:
        return yaml.safe_load(fh).get("windows_hours", [24, 168, 720])


def load_zero_baseline(path: str = WEIGHTS) -> dict[str, Any]:
    with open(path) as fh:
        return yaml.safe_load(fh).get("zero_baseline", {})


def load_independence(path: str = WEIGHTS) -> dict[str, Any]:
    with open(path) as fh:
        cfg = yaml.safe_load(fh).get("source_independence") or {}
    return {
        "primary_party_types": set(cfg.get("primary_party_types", PRIMARY_PARTY_TYPES)),
        "self_reported_weight": float(cfg.get("self_reported_weight",
                                              SELF_REPORTED_WEIGHT)),
    }


def load_breadth(path: str = WEIGHTS) -> dict[str, Any]:
    with open(path) as fh:
        cfg = yaml.safe_load(fh).get("source_breadth") or {}
    return {
        "target_publishers": int(cfg.get("target_publishers", TARGET_PUBLISHERS)),
        "single_publisher_floor": float(
            cfg.get("single_publisher_floor", SINGLE_PUBLISHER_FLOOR)),
    }


def _parse(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def compute(items: list[dict[str, Any]], authority: dict[str, int],
            now: datetime | None = None, windows: list[int] | None = None,
            zero_baseline: dict[str, Any] | None = None,
            source_types: dict[str, str] | None = None,
            independence: dict[str, Any] | None = None,
            breadth: dict[str, Any] | None = None) -> Momentum:
    """Momentum for one narrative's items.

    `source_types` maps source id to its registry type. Absent it, no source can be
    identified as a primary party, so the independence correction cannot apply and
    independent_authority_coverage equals authority_coverage. That is a visible
    degradation rather than a silent one: `independence` reports 1.0 only because
    nothing said otherwise.
    """
    now = now or datetime.now(timezone.utc)
    windows = windows or load_windows()
    zero_baseline = zero_baseline if zero_baseline is not None else load_zero_baseline()
    independence = independence if independence is not None else load_independence()
    breadth = breadth if breadth is not None else load_breadth()
    source_types = source_types or {}
    short, mid = windows[0], windows[1]

    dated = [(i, _parse(i.get("published_at"))) for i in items]
    timed = [(i, d) for i, d in dated if d]
    undated = len(items) - len(timed)

    current = sum(1 for _, d in timed if d >= now - timedelta(hours=short))
    # Baseline is the comparable earlier span, so velocity compares like with like
    # rather than a day against a month.
    span = timedelta(hours=mid - short)
    window_start = now - timedelta(hours=mid)
    prior = [d for _, d in timed if window_start <= d < now - timedelta(hours=short)]
    scale = max(1.0, span / timedelta(hours=short))
    baseline = len(prior) / scale

    rule = "ratio"
    if baseline <= 0:
        # Section 14 leaves this undefined and it is the common case for a genuinely
        # new narrative. The rule applied is recorded rather than hidden.
        rule = zero_baseline.get("rule", "treat_as_emerging")
        velocity = float(zero_baseline.get("assigned_velocity", 1.0)) if current else 0.0
    else:
        velocity = current / baseline

    # Acceleration needs a third point: this window's velocity against the previous
    # window's. With one snapshot there is no change to measure, so it is 0.0 and
    # honest, not interpolated.
    acceleration = 0.0

    source_ids = {i["source_id"] for i in items}
    authoritative = {s for s in source_ids if authority.get(s, 0) >= AUTHORITATIVE_FLOOR}
    authority_coverage = len(authoritative) / len(source_ids) if source_ids else 0.0
    source_diversity = len(source_ids) / len(items) if items else 0.0

    # A primary party is authoritative about its own actions and is not outside
    # confirmation that they matter. Section 15 asks whether the topic can be
    # evidenced reliably, so it gets the corrected figure; section 14's
    # authority_coverage above is left as the blueprint defines it.
    party_types = independence["primary_party_types"]
    self_weight = independence["self_reported_weight"]
    self_reported = {s for s in source_ids if source_types.get(s) in party_types}
    independent = source_ids - self_reported
    if source_ids:
        credited = (len(authoritative & independent)
                    + self_weight * len(authoritative & self_reported))
        independent_authority_coverage = credited / len(source_ids)
        independence_ratio = len(independent) / len(source_ids)
    else:
        independent_authority_coverage = 0.0
        independence_ratio = 0.0

    # Breadth, not section 14's ratio: how many publishers carried this, against a
    # target. Counting distinct publishers rather than dividing by item count means
    # wide coverage is never punished for being voluminous.
    counts: dict[str, int] = {}
    for i in items:
        counts[i["source_id"]] = counts.get(i["source_id"], 0) + 1
    distinct_publishers = len(counts)
    max_publisher_share = (max(counts.values()) / len(items)) if items else 0.0
    floor = breadth["single_publisher_floor"]
    target = max(1, breadth["target_publishers"])
    if distinct_publishers:
        reach = min(1.0, distinct_publishers / target)
        publisher_breadth = floor + (1.0 - floor) * reach
    else:
        publisher_breadth = 0.0

    newest = max((d for _, d in timed), default=None)
    if newest is None:
        novelty = 0.0
    else:
        age_h = max(0.0, (now - newest).total_seconds() / 3600)
        novelty = max(0.0, 1.0 - age_h / mid)

    emergence = velocity + acceleration + novelty + source_diversity

    if current == 0:
        status = "declining"
    elif baseline <= 0:
        status = "emerging"
    elif velocity >= 1.5:
        status = "rising"
    else:
        status = "stable"

    return Momentum(current=current, baseline=round(baseline, 3),
                    velocity=round(velocity, 3), acceleration=acceleration,
                    authority_coverage=round(authority_coverage, 3),
                    independent_authority_coverage=round(
                        independent_authority_coverage, 3),
                    independence=round(independence_ratio, 3),
                    independent_sources=len(independent),
                    self_reported_sources=len(self_reported),
                    source_diversity=round(source_diversity, 3),
                    distinct_publishers=distinct_publishers,
                    max_publisher_share=round(max_publisher_share, 3),
                    publisher_breadth=round(publisher_breadth, 3),
                    novelty=round(novelty, 3), emergence=round(emergence, 3),
                    status=status, baseline_rule=rule,
                    dated_items=len(timed), undated_items=undated)
