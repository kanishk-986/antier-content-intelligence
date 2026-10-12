# ARCHITECTURE

Derived from `MASTER_BLUEPRINT.md` §6, §7, §8. The blueprint governs.

## Stage pipeline

```
Sources: web / RSS / APIs / approved social / research
                      |
         [1] INGESTION        src/ingestion/
             clean -> normalize -> deduplicate
                      |
         [2] INTELLIGENCE     src/intelligence/
             entities - topics - sentiment - claims
                      |
         [3] NARRATIVE        src/narratives/
             embeddings -> clustering -> momentum -> emergence
                      |
         [4] ANTIER FIT       src/scoring/
             capability - audience - commercial - authority
                      |
         [5] CONTENT STRATEGY src/agents/
             whitespace - persona - hook - angle - format
                      |
         [6] AI QA            src/agents/
             evidence - novelty - risk - brand fit - conflicts
                      |
         [7] HUMAN QA         dashboard/ + src/api/
                      |
             approved opportunities
                      |
         briefs               src/briefs/
             LinkedIn brief / article dossier / blog brief
                      |
             performance feedback
```

## Stage contracts

Every stage is a function from data to data, independently testable (CLAUDE.md rule 8).
No stage reaches into another's internals; they communicate through the store.

| Stage | Reads | Writes | LLM? |
|---|---|---|---|
| 1 Ingestion | `sources` | `content_items` | No |
| 2 Intelligence | `content_items` | `intelligence` | **Yes** — structured output |
| 3 Narrative | `intelligence` | `narratives` | Embeddings + deterministic clustering |
| 4 Antier fit | `narratives`, `config/brand`, `config/scoring` | `opportunities` | Partly — judgement scored, arithmetic deterministic |
| 5 Content strategy | `opportunities`, `config/brand` | `opportunities` (persona, angle, format) | **Yes** |
| 6 AI QA | `opportunities` | `qa_reviews` | **Yes** — adversarial |
| 7 Human QA | `opportunities`, `qa_reviews` | `qa_reviews.human_decision` | No |
| Briefs | approved `opportunities` | dossier files | **Yes** |

**Ingestion must not decide whether a topic is good for Antier** (§10). It discovers
and normalizes. Judgement belongs to stages 4–6.

## Determinism boundary

The single most important architectural rule (CLAUDE.md rule 7):

- **LLM does:** extraction, classification, sentiment, thesis generation, adversarial QA.
- **Python does:** all arithmetic — trend velocity, acceleration, authority coverage,
  weighted opportunity score, thresholds.

The same inputs must always produce the same score. A scoring change is a diff in
`config/scoring/weights.yaml`, never a prompt tweak.

## Storage

All persistence goes through `src/database/store.py`. The vertical slice uses
`sqlite_store.py`; `pg_store.py` lands later with Postgres + pgvector. **No pipeline
stage imports a database driver directly.**

Vector search starts as in-process cosine similarity over stored embeddings — adequate
at the §40 vertical-slice scale of 50–100 items — and moves to pgvector behind the
same interface.

## Technology (§8)

| Layer | Choice | Status |
|---|---|---|
| Application | Python + FastAPI | FastAPI deferred to the dashboard milestone |
| LLM | Claude (`claude-opus-5`) | — |
| LLM orchestration | Explicit agent stages in Python, no multi-agent framework | — |
| Database | PostgreSQL | **SQLite first** behind the store interface, per §40 |
| Vector search | pgvector | **In-process cosine** first, same interface |
| Extraction | Trafilatura / BeautifulSoup / Playwright where permitted | — |
| RSS | feedparser | — |
| Scheduling | cron first, Celery/worker later | — |
| Dashboard | Next.js or Streamlit MVP | — |
| CI/CD | GitHub Actions | — |
| Containerization | Docker | Not installed on the current machine |
| Hosting | Railway / Render / AWS / DigitalOcean | Undecided |

### Deviations from §8, and why

Two, both sanctioned by §40 ("validate the architecture before investing in a large
crawler or polished UI") and both reversible behind an interface:

1. **SQLite instead of PostgreSQL for the vertical slice.** Postgres, pgvector and
   Docker are absent from the build machine. Installing them before any pipeline code
   exists inverts §40. The §9 schema is implemented verbatim either way.
2. **In-process cosine similarity instead of pgvector.** Same reason, same interface.

Everything else follows §8 as written.

## Efficiency rule (§10.2)

Never reprocess the entire source universe on every run. Track last-seen identifiers,
content hashes and timestamps per source. Fetch only new or changed content, and pass
only new relevant material into the LLM pipeline — LLM calls are the dominant cost.

## Audit trail (§33)

Every AI decision and every human override is recorded with actor, timestamp and
reason. Model calls are logged without storing unnecessary sensitive content. Every
content item carries source attribution and a retrieval timestamp.
