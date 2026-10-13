# CHANGELOG

## [0.1.0] — 2026-10-12

Phase 0: repository and documentation (§39 Phase 0, §44.24–27).

### Added
- Repository scaffold matching §7.1 — `docs/`, `config/{brand,scoring,sources}/`,
  `src/{ingestion,intelligence,narratives,scoring,agents,briefs,database,api}/`,
  `prompts/`, `dashboard/`, `migrations/`, `tests/`, `scripts/`, `.github/workflows/`.
- `CLAUDE.md` — system constitution from §31.1.
- `docs/MASTER_BLUEPRINT.md` — the owner specification, verbatim, under version
  control per §44.25. Governs every derived document.
- `docs/` set — PRD, ARCHITECTURE, DATA_MODEL, SCORING, SOURCE_POLICY, QA_POLICY,
  PROMPTS, RUNBOOK, CHANGELOG, ROADMAP.
- `.gitignore` and `.env.example` — variable names only, per §7.2 and §33.

### Added (follow-up)
- `scripts/check.sh` — lint, tests and secret scan, identical to CI.
- `scripts/install-hooks.sh` — installs a pre-push hook running that gate, so
  §7.2's "tests before merge" holds even though Actions cannot run yet.
- Explicit `[tool.ruff.lint]` rule selection: E, F, I, B, SIM, RUF. Modernization
  opinions (UP, FURB) are excluded deliberately — they produce formatting churn
  rather than catching defects.

### Known gap
- **GitHub Actions is not running.** Pushing `.github/workflows/` needs a token with
  `workflow` scope; the available credential has `repo` only. The workflow is
  preserved on local branch `pending/ci-workflow`.

### Added — Phase 3 (ingestion + DB)
- `migrations/001_initial_schema.sql` — the §9 schema verbatim, 9 tables, plus
  `narrative_items`, `audit_log` (§33) and `fetch_state` (§10.2).
- `src/database/store.py` — storage Protocol. No pipeline stage imports a driver.
- `src/database/sqlite_store.py` — SQLite implementation.
- `src/ingestion/fetcher.py` — feed discovery, conditional fetch, trafilatura
  extraction, content hashing, strict date parsing.
- `src/ingestion/pipeline.py` — registry → fetch → dedupe → store with per-source
  coverage reporting.
- `scripts/run_ingestion.py` — CLI with `--limit`, `--max-items`, `--no-bodies`.
- 25 further tests (41 total).

### Fixed
- `insert_content` caught every `IntegrityError` and reported it as a duplicate, so a
  dangling `source_id` was silently swallowed. It now distinguishes the content_hash
  uniqueness conflict — the expected §10.2 duplicate — from genuine integrity errors,
  which raise. Found by a test asserting foreign-key enforcement.

### Finding
- **Feed coverage is the real constraint.** Of the 12 highest-authority sources, 3
  have a usable feed, 6 have none, 3 are blocked. The no-feed set is the
  primary-announcement layer (DTCC, Euroclear, Clearstream, LSEG, Mastercard,
  Circle). An HTML listing extractor is a prerequisite, not an enhancement.

### Added — Phase 3b (static listing extraction)
- `src/ingestion/listing.py` — listing-page extraction for feedless sources, with
  trafilatura metadata for confirmed dates.
- `config/sources/listing_rules.yaml` — per-host listing paths and reject patterns,
  so a source's news path is configuration, not code (§41.1).
- Pipeline tries the feed first and falls back to listing extraction on `no_feed`;
  `run_ingestion.py --no-listing` disables it. Each report row records `via`.
- 11 further tests (52 total).

### Fixed during 3b
- The slug heuristic matched product pages — `/products-and-services/
  capital-liquidity-optimization` is three hyphenated words. Added a path-prefix
  constraint: a candidate must sit under the listing page's own path. Caught on the
  first live run, which had ingested "Capital & Liquidity Optimization" and
  "Brand Kit" as articles.
- First fix for template timestamps nulled the date, which also destroyed LSEG's
  genuine same-day batch. Changed to flag `date_confidence: low` and keep the value —
  the §14 momentum engine needs the date, and annotation preserves the choice.

### Added — Phase 7 (adversarial AI QA, §19)
- `prompts/ai_qa.v1.md` — §19's ten questions, versioned. Carries an explicit
  mandate on question 3: reject when timing is doing the work and substance is not,
  naming the four tells (single-source clusters, novelty≈1.0 against low relevance,
  velocity from `treat_as_emerging`, items that are not events).
- `src/agents/qa.py` — `QA_SCHEMA`, `validate()`, prompt assembly, `as_row()`. The
  reviewer receives the per-dimension scoring provenance and the unmeasured list,
  labelled "audit this, do not trust it".
- `migrations/002_qa_review_fields.sql` — `problems`, `failed_questions`,
  `prompt_version` as first-class columns on `qa_reviews`.
- `scripts/run_qa.py` — `--top N`, `--dry-run`, and a `StubQA` for wiring tests.
- `tests/test_qa.py` — 25 tests. 166 pass in total.

### Resolved — the Phase 6 open decision
The recency artefact is handled by QA, not by reweighting (owner's choice). It works:
first live pass over the top four gave **3 REJECT, 1 RESEARCH_MORE, 0 APPROVE** at
confidence 0.80–0.93, with the model citing `treat_as_emerging` by name. §15's
weights are unchanged.

### Fixed during 7
- **A directive sat above `## SYSTEM` in `prompts/ai_qa.v1.md`**, so `load_prompt()`
  discarded it and the model never received the "you judge, you do not score" rule.
  Caught by a test, not by reading. A parametrised regression guard now asserts no
  prompt file strands a directive in its preamble — which immediately found a dead
  duplicate of the same rule in `prompts/intelligence.v1.md` and removed it.
- `validate()` rejects a non-APPROVE decision with an empty `problems` list. A
  rejection without a reason is invisible to §27's dashboard and useless to §30's
  feedback loop.
- Scoring ran twice with fresh UUIDs while `opportunities` still held the earlier
  ids, so inserting a review raised `FOREIGN KEY constraint failed`. `score_all()`
  and `persist()` now live in `src/scoring/opportunity.py` and both `run_scoring.py`
  and `run_qa.py` call them; QA persists before it reviews.
- The migration runner split DDL on bare `;`, which mangled statements containing
  one. Replaced with `sqlite3.complete_statement`. Its `ADD COLUMN` idempotency
  guard then missed every statement carrying a leading `--` comment; fixed with
  `_strip_leading_comments()`. Verified: a fresh database migrates three times
  cleanly, an existing one upgrades with data intact.
- Replaced an `__problems__:` prefix smuggled into `risk_flags` with the real
  columns in migration 002.

### Found by QA, not yet fixed
Both are upstream defects the deterministic score cannot express:
- Several clusters count one vendor's own newsroom pages as independent sources.
  Source diversity needs to key on publisher, not URL.
- Navigation boilerplate reaches the model in place of article text on some pages.

### Open decision
- **Playwright for client-rendered sources (Phase 3c).** DTCC and Clearstream serve a
  navigation-only shell. Reported `js_rendered` rather than silently empty. §8
  sanctions Playwright "where permitted"; ~150 MB of browser binaries is not
  installed on a guess.

### Added — Phase 5 (narrative clustering)
- `src/narratives/similarity.py` — `Similarity` Protocol plus TF-IDF cosine. No
  sklearn; TF-IDF over a few hundred documents is standard library.
- `src/narratives/cluster.py` — average-link agglomerative clustering. Average-link
  over single-link because single-link chains: one article mentioning stablecoins and
  DePIN would merge two unrelated narratives.
- `src/narratives/momentum.py` — §14 velocity, acceleration, authority coverage,
  source diversity, novelty, emergence, with the zero-baseline rule recorded.
- `scripts/run_narratives.py` — cluster, score, persist, report.
- Store gains `replace_narratives`, `narratives`, `narrative_items`,
  `source_authority`.
- 18 further tests (75 total), including determinism checks on both similarity and
  clustering.

### Fixed during 5
- First threshold (0.28, guessed) produced 130 narratives from 148 items with **zero**
  cross-source clusters — it clustered by publisher house style, the opposite of §12.
  Three changes fixed it: sweeping the threshold to 0.05 against the live corpus,
  clustering on title plus a 600-character lede rather than the whole article, and
  adding publisher boilerplate ("clients", "leveraging", "insights") to the stopword
  list. Cross-source clusters went 0 → 16.

### Added — Phase 4 (intelligence extraction)
- `prompts/intelligence.v1.md`, `src/intelligence/{schema,extractor,pipeline,stub}.py`,
  `scripts/run_intelligence.py`, store support for the `intelligence` table.
- 27 further tests (102 total), all offline via the stub.

### Fixed during 4
- A test caught a real prompt defect: the rule "you judge, you do not score"
  (CLAUDE.md rule 7) sat in the file's preamble **above** `## SYSTEM`, so the model
  would never have received it. Moved into the system message.
- A truncation test counted `"x"` characters, but the user template contains one
  itself. Replaced with a substring assertion — the test was brittle, not the code.

### Added — subscription backend
- `src/intelligence/claude_cli.py` — `LLM` implementation over the authenticated
  `claude` CLI, so the model stages run on a Claude.ai subscription rather than
  metered API credits. Now the **default**; `--backend api` selects the key path.
- 13 further tests (115 total).

The CLI exposes no `output_config.format`, so the schema is requested in the prompt
and enforced afterwards by `schema.validate`. That is only safe because the validator
already rejects rather than clamps: a malformed record fails loudly and is recorded as
a failure instead of stored.

### Added — Phase 6 (Antier relevance scoring)
- `src/scoring/{weights,relevance,saturation,opportunity}.py`,
  `scripts/run_scoring.py`. All seven §15 dimensions, weighted sum in Python from
  version-pinned weights. No model is called in this phase.
- 26 further tests (141 total), including a determinism check.
- `docs/SCORING.md` gains an implementation-notes section recording where each
  dimension comes from and what is still a proxy.

### Fixed during 6 — both found by reading ranked live output
- Relevance scored body noise: a support thread scored 0.68 on stablecoin rails
  because "payment" appeared in a signature. Title hits now count double and
  body-only evidence is halved; that thread scores 0.23.
- Service priority floored commercial relevance: averaging model importance with
  priority gave a Richmond Fed economics paper rated 0.10 a score of 0.55. Priority
  now scales the judgement rather than substituting for it; the same item scores 0.33.
- Unmeasured dimensions now cap the band below `good`, so an un-extracted narrative
  can be monitored but never promoted.

### Open decision
- **30% of §15's weight is recency** (velocity 20% + novelty 10%), which on a
  single-batch corpus favours whatever published that morning. Not silently
  reweighted — the weights are the owner's. `docs/SCORING.md` sets out three
  resolutions; Phase 7's adversarial QA is the one the blueprint intends.

### Decisions recorded
- **SQLite before PostgreSQL** for the vertical slice, behind `src/database/store.py`.
  Postgres, pgvector and Docker are absent from the build machine; installing them
  before any pipeline code exists inverts §40. The §9 schema is implemented verbatim
  either way, and the swap is an interface implementation, not a rewrite.
- **In-process cosine similarity before pgvector**, same interface, same reason.
- **New repository** rather than extending `antier-intelligence-agent`, per §44.24,
  porting the reusable parts of the predecessor.
