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


---

# Implementation notes (added Phase 6, 2026-10-13)

## Where each dimension comes from

| Dimension | Source | Notes |
|---|---|---|
| Trend velocity | `momentum.velocity`, normalised | Unbounded ratio; 2× or better saturates to 1.0 |
| Antier relevance | signal match vs `config/brand/services.yaml` | **Title hits count double.** Body text is long enough that a stray "payment" matches; a title is what an item is about. Body-only evidence is halved. |
| Audience relevance | ICP named in text, else the matched service's ICPs | Direct naming beats indirect inference |
| Commercial relevance | `intelligence.importance_score` × service priority | **Multiplicative, not averaged** — see below |
| Authority potential | service priority, lifted by a `proof_points` match | Capped until a real case-study corpus exists (PRD §12) |
| Novelty | `momentum.novelty` (recency) | A **proxy**. The real §17 contrarian-angle agent is an unbuilt LLM stage. |
| Source credibility | `momentum.authority_coverage` | Registry tiers, never volume (§5.2) |

## Unmeasured dimensions cap the band

If any dimension could not be measured, the band is capped just below `good`
(6.99). An un-extracted narrative can be **monitored but never promoted**.

This is the same rule the competitor axis follows: a missing input is not a pass.
Without it, the first live run put a support-forum thread
("thanks, test, really, appreciate") **above** a Chainlink cross-chain narrative,
because a generous fallback beat a real but unextracted signal.

## Two defects found by reading live output

Both were invisible in theory and obvious in a ranked list.

1. **Relevance scored body noise.** A support thread scored 0.68 on stablecoin rails
   because the word "payment" appeared in a signature. Fixed by weighting title hits
   double and halving body-only evidence; that thread now scores 0.23.
2. **Service priority floored commercial relevance.** The formula averaged model
   importance with service priority, so a Richmond Fed economics paper the model rated
   **0.10** still scored **0.55** — high enough to out-rank real narratives. Priority
   now *scales* the judgement rather than substituting for it: the same item scores
   0.33.

## Known limitation: 30% of the weight is recency

§15 assigns trend velocity 20% and novelty 10%. On a corpus ingested in one batch,
recency is largely an artefact of which feed happened to publish that morning, so a
fresh low-value item can still out-rank older substance. After both fixes above, the
Richmond Fed paper sits at 6.43 against Chainlink's 6.10 — much closer, but still
ahead.

**This is not silently reweighted.** The weights are the owner's, in
`config/scoring/weights.yaml`, and changing them is an editorial decision. Three ways
to resolve it:

1. **Adjust the weights** — e.g. velocity 15% / novelty 5%, with the 10% moved to
   Antier relevance. One diff in `weights.yaml`, version-bumped.
2. **Let Phase 7 handle it.** §19's AI QA asks exactly this: *"is the narrative
   genuinely emerging, or merely noisy?"* The adversarial reviewer is the designed
   place to reject a recency artefact.
3. **Extract more.** Every item extracted makes `commercial_relevance` real instead of
   a fallback, and the Richmond Fed paper falls as its 0.10 importance propagates.
   25 of 148 items are extracted so far.

Option 2 is what the blueprint intends.
