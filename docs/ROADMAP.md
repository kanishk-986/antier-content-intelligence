# ROADMAP

Phases from `MASTER_BLUEPRINT.md` §39; build sequence from §31.2; first milestone
from §40.

| Phase | Deliverable | Outcome | Status |
|---|---|---|---|
| 0 | Git repo + documentation | Single source of truth | **done** |
| 1 | Antier brand brain | System understands company and personas | **done** |
| 2 | Excel ingestion | Curated source universe online | **done** |
| 3 | Ingestion + DB | Reliable content pipeline | **done** (feed-based) |
| 3b | HTML listing extractor | Reach the no-feed primary sources | **done** (static) |
| 3c | Browser rendering (Playwright) | Reach client-rendered sources | open decision |
| 4 | Intelligence | Structured market signals | **done** — runs on the subscription |
| 5 | Narratives | Market themes instead of article lists | **done** (TF-IDF) |
| 6 | Scoring | Antier-specific opportunity ranking | **done** |
| 7 | QA | High-confidence editorial queue | |
| 8 | Dashboard | Human review workflow | |
| 9 | Research dossiers | Long-form content pipeline | |
| 10 | Feedback loop | Performance-informed intelligence | |
| 11 | Competitors / social | Broader market intelligence | |
| 12 | Optimization | Continuous quality improvement | |

## First coding milestone (§40)

A **working vertical slice, not hundreds of files**:

```
Excel -> 10 test sources -> fetch 50-100 recent items -> deduplicate
      -> Claude extraction -> cluster into narratives -> score for Antier
      -> generate 10 opportunities -> AI QA -> JSON + simple dashboard
```

Expand source coverage only once that runs end to end. This validates the
architecture before investing in a large crawler or a polished UI.

## Phase 3 result

Feed-based ingestion runs end to end: registry → discover feed → fetch → normalize →
dedupe on content hash → store, with per-source coverage reporting and the §10.2
efficiency rule verified (a second run stored 0 new items).

**The finding that changes the plan:** only 3 of the 12 highest-authority sources
expose a feed. Six of the most valuable — DTCC, Euroclear, Clearstream, LSEG,
Mastercard, Circle — have none. Phase 3b (an HTML listing extractor) is therefore a
prerequisite for the §40 vertical slice to be representative, not a later nicety.

## Phase 3b result

Static listing extraction doubled reach over the same 12 sources: **3 → 6 reached,
18 → 41 items**, adding Circle, LSEG and Mastercard — including "Mastercard unveils
Agent Pay" and "A conversation on USDC, AI, and the end of banking hours", both
directly on the §3.1 pillars.

**Phase 3c is an open decision, not a deferral.** DTCC and Clearstream are
client-rendered; their server HTML is a navigation shell. Reaching them needs
Playwright, which §8 sanctions "where permitted" but which costs ~150 MB of browser
binaries. Not installed on a guess — it is a call for the owner.

Still unreached after 3b: DTCC and Clearstream (`js_rendered`), Euroclear, FATF and
IMF (HTTP 403), Digital Asset (no listing page found).

## Phase 5 result

148 items cluster into 40 narratives, 16 of them cross-source — the §12 behaviour:
several separate stories becoming one theme. Real examples from the live corpus:

- **Centrifuge + Chainlink + Ondo** (15 items) — tokenized distribution and on-chain value
- **ESMA + Circle** — EU securities regulation and tokenised collateral
- **Mastercard + Stripe/Bridge** — card-linked stablecoin spend
- **CMS + Anthropic** — healthcare AI and verification programmes

Similarity sits behind `src/narratives/similarity.py`, so embeddings replace TF-IDF
as a second implementation rather than a rewrite — the same pattern as the store.

**The threshold was swept, not guessed**, and the first guess was badly wrong: 0.28
gave 130 narratives from 148 items with **zero** cross-source clusters, grouping by
publisher instead of topic. The table in `cluster.py` records the sweep. Two fixes
mattered: clustering on title plus lede rather than the full body, and adding
publisher boilerplate to the stopword list.

**Honest deviation from §12:** it asks for 10–20 narratives from ~100 items. This
corpus spans all eight charter services rather than one theme, so 40 is the analogue;
forcing it lower merges unrelated services. Embeddings should separate similarities
better and allow a higher, more stable threshold.

**Acceleration is 0.0 and says so.** §14 defines it as change in velocity, which needs
two snapshots. One run cannot measure it, so it is not interpolated.

## Phase 4 result

**It runs, with no API credits.** The owner cannot supply a metered key, so a second
`LLM` implementation routes the model stages through the authenticated `claude` CLI
and the existing Claude.ai subscription. The injected-client design made this a
drop-in; nothing downstream changed. `--backend api` remains for a key-based run.

Verified on live data: 11 items extracted, 0 failures. Importance discriminates
correctly on a corpus that contains noise — a **BIS job posting scored 0.05**, ERC
draft threads 0.05–0.25, Richmond Fed academic economics 0.10. The §11 instruction
that importance is "about this business, not the internet" is doing real work.

What exists:

- `prompts/intelligence.v1.md` — the §11 extraction prompt, versioned.
- `src/intelligence/schema.py` — the §11 JSON schema plus a validator that **rejects**
  out-of-range values rather than clamping them, because clamping hides a misbehaving
  prompt and QA depends on sentiment being comparable across items.
- `src/intelligence/extractor.py` — client injected, not constructed, so the pipeline
  is testable without a key. Uses `output_config.format` for structured output.
- `src/intelligence/stub.py` — a deterministic stand-in. Structurally valid,
  analytically worthless, and its sentiment is **all zeros** rather than invented, so
  a test cannot pass for the wrong reason.
- `src/intelligence/pipeline.py` — §10.2 applied to the LLM stage: an item already
  extracted is never re-sent, because here the cost is money.
- `scripts/run_intelligence.py --dry-run` proves the wiring end to end with no key;
  `--estimate` reports volume and rough input tokens before spending anything.

Dry run over the live corpus: 25 attempted, 23 stored, 2 filtered as price
speculation (§2.2), 0 failed. Re-run attempted 0 — the efficiency rule holds.

**To run it:** `python3 scripts/run_intelligence.py --limit 20`. No key needed. Use
`--limit` and resume — subscription rate limits apply instead of a credit balance,
and 137 items remain pending.

## Phase 6 result

All seven §15 dimensions are computed in Python from `config/scoring/weights.yaml`
v1 — no model sees the arithmetic (CLAUDE.md rule 7). Changing a weight is a config
edit with a version bump, not a code change.

Two defects surfaced only by reading the ranked live output, not by the tests:
relevance was scoring body noise (a support thread at 0.68 on stablecoin rails,
because "payment" sat in a signature), and service priority was substituting for
judgement (a Richmond Fed economics paper the model rated 0.10 scoring 0.55). Both
fixed in the formula — title hits count double, body-only evidence halves, and
priority now scales the judgement multiplicatively. Those items now score 0.23 and
0.33.

A narrative with unmeasured dimensions is **capped below `good`**: it can be
monitored, never promoted on the strength of what was never measured.

## Phase 7 result

**The QA rejects the recency artefact, which is why it was built.** 30% of §15's
weight is recency, and rather than quietly retuning the owner's weights, the
blueprint's own gate was given the scoring provenance it needs to argue against a
score. It does. From the live run, unprompted:

> `trend_velocity` is 1.0 only via the `treat_as_emerging` rule, meaning there was
> no baseline to compare against.

> The cluster is not a narrative. The three items share only the surface tokens
> "mobile/technology".

> Two of the three items are not events — product and press marketing pages.

First live pass over the top four: **3 REJECT, 1 RESEARCH_MORE, 0 APPROVE** at
confidence 0.80–0.93. That is the correct reading of this corpus, not a failure of
the gate — §19 says an analyst who approves everything has failed.

It also found two upstream defects, both since fixed — see CHANGELOG. The serious
one: §15's `source_credibility` was reading §14's `authority_coverage`, so a cluster
of nothing but vendor press releases scored perfect credibility. **28 of 40
narratives scored 1.0 that way and 24 had no independent source at all.** Authority
and corroboration are different questions and the score was answering the wrong one.

The reviewer's second complaint — navigation boilerplate in place of article text —
was overstated at "four of six items"; measured, it is 1 of 144. But it pointed at
something real: the feed-summary fallback was unrecorded, so 18 items reached the
model as sub-60-word blurbs dressed as full articles. An adversarial reviewer
exaggerating in the right direction is still worth more than a silent one.

What exists:

- `prompts/ai_qa.v1.md` — §19's ten questions, versioned, with an explicit mandate
  on question 3: reject when timing is doing the work and substance is not, listing
  the four recency tells.
- `src/agents/qa.py` — schema, validator, prompt assembly. The validator **rejects a
  non-APPROVE decision that states no problem**, because §27's dashboard must show
  "rejected topics with reasons" and §30's feedback loop consumes them. A silent
  rejection is data loss.
- The reviewer is handed the **dimension-by-dimension provenance** and the list of
  unmeasured dimensions, labelled "audit this, do not trust it". Without it, QA can
  only re-read the articles; with it, QA can name the mechanism.
- `migrations/002_qa_review_fields.sql` — `problems`, `failed_questions` and
  `prompt_version` as first-class columns.
- `scripts/run_qa.py` — scores and persists before reviewing, so a review can never
  reference an opportunity row that does not exist.

**Section 20 holds.** This narrows the queue; it does not decide. `human_decision`
is left null for a person, and nothing in the pipeline publishes.

**To run it:** `python3 scripts/run_qa.py --top 5`. No key needed; `--dry-run` for
the wiring.

## Deferred by §32

- LinkedIn publishing automation — **NO**, not in scope
- Full competitor intelligence — later
- Advanced self-learning optimization — later

## Blocked, not deferred

| Item | Blocker |
|---|---|
| GitHub Actions CI | token needs `workflow` scope; held on branch `pending/ci-workflow`. Local gate `scripts/check.sh` + pre-push hook covers it meanwhile |
| Branch protection on `main` (§7.2) | deferred until CI exists, so the required status check can be named |
| Any LLM stage running | `ANTHROPIC_API_KEY` not set |
| Proof-of-expertise engine (§23) | No machine-readable Antier case-study corpus exists |
| Competitor saturation (§16 competitor axis) | No competitor set defined |
| Feedback loop (§30) | No published-performance data source |
