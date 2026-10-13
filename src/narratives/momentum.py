"""Trend and momentum per section 14.

All arithmetic, no LLM (ARCHITECTURE.md determinism boundary):

    trend_velocity     = current_mentions / baseline_mentions
    acceleration       = change_in_velocity
    authority_coverage = weighted authoritative sources / total sources
    emergence          = velocity + acceleration + novelty + source_diversity

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


@dataclass
class Momentum:
    current: int
    baseline: int
    velocity: float
    acceleration: float
    authority_coverage: float
    source_diversity: float
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
            zero_baseline: dict[str, Any] | None = None) -> Momentum:
    """Momentum for one narrative's items."""
    now = now or datetime.now(timezone.utc)
    windows = windows or load_windows()
    zero_baseline = zero_baseline if zero_baseline is not None else load_zero_baseline()
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
                    source_diversity=round(source_diversity, 3),
                    novelty=round(novelty, 3), emergence=round(emergence, 3),
                    status=status, baseline_rule=rule,
                    dated_items=len(timed), undated_items=undated)
