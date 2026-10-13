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

Plus an independence correction that §14 does not define but §15 needs:

```
self_reported     = sources whose registry type is a primary party
independence      = independent_sources / total_sources
independent_authority_coverage
                  = (authoritative_independent
                     + self_reported_weight * authoritative_self_reported)
                    / total_sources
max_publisher_share
                  = items_from_largest_publisher / total_items
publisher_breadth = floor + (1 - floor) * min(1, distinct_publishers / target)
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
| Source credibility | `independent_authority_coverage` × `publisher_breadth` | Registry tiers, never volume (§5.2); never a primary party's account of itself; never one publisher read as several. See below |

## Authority is not corroboration

§5.2 puts "primary company/protocol announcements" at tier 10, and that is right:
a vendor is the most authoritative source in the world about what it just did.
But §15's `source_credibility` asks a different question — whether the topic "can
be evidenced reliably" — and that is about corroboration.

Conflating the two produced a real defect. On the live corpus, a 15-item cluster of
Chainlink, Ondo and Centrifuge press releases scored `authority_coverage` **1.0**,
because all three are tier-9 primary parties. Across the whole corpus **28 of 40
narratives** scored a perfect 1.0 this way, and **24 of 40 had no independent source
at all**.

So §14's `authority_coverage` is left exactly as the blueprint defines it, and
`source_credibility` reads `independent_authority_coverage` instead. A source whose
registry type is in `source_independence.primary_party_types` is **discounted, not
discarded** — weight `0.35`, in `weights.yaml` so it is a config diff. A primary
party is genuine evidence of its own actions and no evidence that they matter to
anyone else; zero would be the opposite error.

The raw figure stays in the dimension's `detail`, so nothing is hidden from the
audit trail and the QA reviewer can see both numbers.

**When registry types are unavailable** no source can be identified as a primary
party, so the corrected figure equals the raw one and `self_reported_sources` is 0.
That is a visible degradation, not a silent one.

## One publisher is not several

Independence by source type leaves a second hole: three items from one regulator's
newsroom score full coverage, because that regulator genuinely *is* independent.
The live FSB cluster was exactly this — three items, one publisher, credibility 1.0.
On this corpus **24 of 40 narratives come from a single publisher**.

§14's `source_diversity` (distinct sources ÷ items) measures the concentration, but
it cannot feed §15, because it falls as item count rises:

| narrative | §14 `source_diversity` | `publisher_breadth` |
|---|---|---|
| 1 item, 1 publisher | 1.0 | 0.667 |
| 3 items, 1 publisher | 0.333 | 0.667 |
| 3 items, 3 publishers | 1.0 | 1.0 |
| **15 items, 3 publishers** | **0.2** | **1.0** |

The ratio rates a well-covered 15-item narrative *below* a single stray item. That
penalises coverage, which inverts the intent, so §14's figure stays where the
blueprint put it — feeding `emergence` only.

`publisher_breadth` counts distinct publishers against a target instead
(`source_breadth` in `weights.yaml`: target 3, floor 0.5). Three independent
publishers is full corroboration; a single publisher is **floored at 0.667, not
zeroed**, because one regulator's publication is still evidence. Nothing is gained
by piling on past the target.

The two corrections compound, as they should — a lone vendor newsroom is both
self-reported and concentrated:

| cluster | coverage | breadth | credibility |
|---|---|---|---|
| 3 independent publishers | 1.0 | 1.0 | **1.0** |
| FSB: 3 items, 1 standards body | 1.0 | 0.667 | **0.667** |
| Chainlink/Ondo/Centrifuge: 3 vendors | 0.35 | 1.0 | **0.35** |
| Paxos: 5 items, 1 vendor | 0.35 | 0.667 | **0.233** |

Every component stays in the dimension's `detail`, so the audit trail shows which
correction did what.

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
