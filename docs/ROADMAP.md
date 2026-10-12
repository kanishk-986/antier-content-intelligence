# ROADMAP

Phases from `MASTER_BLUEPRINT.md` §39; build sequence from §31.2; first milestone
from §40.

| Phase | Deliverable | Outcome | Status |
|---|---|---|---|
| 0 | Git repo + documentation | Single source of truth | **done** |
| 1 | Antier brand brain | System understands company and personas | **done** |
| 2 | Excel ingestion | Curated source universe online | **done** |
| 3 | Ingestion + DB | Reliable content pipeline | **done** (feed-based) |
| 3b | HTML listing extractor | Reach the no-feed primary sources | **required next** |
| 4 | Intelligence | Structured market signals | blocked on API key |
| 5 | Narratives | Market themes instead of article lists | |
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
