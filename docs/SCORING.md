# SCORING

All formulas from `MASTER_BLUEPRINT.md` §14, §15, §16. **Every formula here is
computed in Python, never by the LLM** (CLAUDE.md rule 7). Weights live in
`config/scoring/weights.yaml` and are version-controlled because they materially
change behaviour (§7.2).

## Trend and momentum (§14)

Per narrative, over 24h / 7d / 30d windows so breaking events are distinguishable
from durable narratives:

```
trend_velocity    = current_mentions / baseline_mentions
acceleration      = change_in_velocity
authority_coverage= weighted_authoritative_sources / total_sources
emergence         = velocity + acceleration + novelty + source_diversity
```

Also tracked: current volume, baseline volume, growth rate, unique-source count,
authoritative-source count, recency.

**Edge case the blueprint does not specify:** `baseline_mentions` can be zero for a
genuinely new narrative, which makes velocity undefined. Implementation must handle
this explicitly and record which rule it used — it must not silently divide by zero or
emit infinity.

## Opportunity score (§15)

The central differentiator. Weighted sum of seven dimensions:

| Dimension | Weight | Meaning |
|---|---|---|
| Trend velocity | 20% | Is attention increasing? |
| Antier relevance | 20% | Does it map to actual capabilities? |
| Audience relevance | 15% | Does it matter to target buyers/readers? |
| Commercial relevance | 15% | Can it create meaningful business context? |
| Authority potential | 10% | Can Antier add expert insight? |
| Novelty | 10% | Is there a differentiated angle? |
| Source credibility | 10% | Can the topic be evidenced reliably? |

Weights sum to 100%. A change is a diff in `weights.yaml`, reviewed like code.

## Thresholds (§15)

| Score | Action |
|---|---|
| < 5 | reject |
| 5 – 7 | monitor |
| 7 – 8 | good |
| 8 – 9 | priority |
| 9 – 10 | immediate editorial review |

## Saturation and whitespace (§16)

A topic can score high on relevance and still be a poor opportunity if every
competitor has published the same take.

| Market demand | Competitor saturation | Interpretation |
|---|---|---|
| High | High | Likely crowded |
| High | Low | **Strong opportunity** |
| Low | Low | Monitor |
| High Antier capability | Low Antier coverage | **Potential authority whitespace** |

Inputs: competitor themes, Antier's own historical themes, market-wide coverage.

**MVP limitation.** §32 defers full competitor intelligence. Until a competitor set
exists (`PRD.md` §12 open question 2), whitespace is computed from Antier's own
coverage and market-wide volume only. The competitor axis must report as
**not yet measured** rather than defaulting to zero — a missing input must never read
as "no saturation", which would inflate every score.

## Authority, not popularity

From §5.2: *the system should never treat source popularity as equivalent to source
authority.* Authority comes from the registry tier, never from engagement volume.

## Testing contract

Per CLAUDE.md rule 5, scoring and parsing are the tested surfaces. Required:

- **known inputs → expected scores**, as fixtures (§34)
- weights that do not sum to 1.0 are a startup error, not a silent renormalization
- a zero baseline is covered explicitly
- a missing dimension is an error, not a zero
- similar stories cluster; unrelated stories separate (§34)
