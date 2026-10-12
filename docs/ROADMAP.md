# ROADMAP

Phases from `MASTER_BLUEPRINT.md` §39; build sequence from §31.2; first milestone
from §40.

| Phase | Deliverable | Outcome | Status |
|---|---|---|---|
| 0 | Git repo + documentation | Single source of truth | **done** |
| 1 | Antier brand brain | System understands company and personas | **done** |
| 2 | Excel ingestion | Curated source universe online | **done** |
| 3 | Ingestion + DB | Reliable content pipeline | next |
| 4 | Intelligence | Structured market signals | |
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

## Deferred by §32

- LinkedIn publishing automation — **NO**, not in scope
- Full competitor intelligence — later
- Advanced self-learning optimization — later

## Blocked, not deferred

| Item | Blocker |
|---|---|
| Remote repo `antier-content-intelligence` | `gh auth login` — browser OAuth, owner action |
| Any LLM stage running | `ANTHROPIC_API_KEY` not set |
| Proof-of-expertise engine (§23) | No machine-readable Antier case-study corpus exists |
| Competitor saturation (§16 competitor axis) | No competitor set defined |
| Feedback loop (§30) | No published-performance data source |
