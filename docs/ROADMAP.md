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
| 4 | Intelligence | Structured market signals | **built**, awaiting API key |
| 5 | Narratives | Market themes instead of article lists | **done** (TF-IDF) |
| 6 | Scoring | Antier-specific opportunity ranking | |
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

Extraction is built, wired and tested. It cannot run: `ANTHROPIC_API_KEY` is not set
and there is no credential on the machine (`~/.claude.json` is Claude Code's own auth,
not something a production service should borrow).

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

**To run it for real:** put the key in `.env`, then
`python3 scripts/run_intelligence.py --limit 20`. Start with a small `--limit`; the
full pending corpus is 125 items.

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
