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

### Open decision
- **Playwright for client-rendered sources (Phase 3c).** DTCC and Clearstream serve a
  navigation-only shell. Reported `js_rendered` rather than silently empty. §8
  sanctions Playwright "where permitted"; ~150 MB of browser binaries is not
  installed on a guess.

### Decisions recorded
- **SQLite before PostgreSQL** for the vertical slice, behind `src/database/store.py`.
  Postgres, pgvector and Docker are absent from the build machine; installing them
  before any pipeline code exists inverts §40. The §9 schema is implemented verbatim
  either way, and the swap is an interface implementation, not a rewrite.
- **In-process cosine similarity before pgvector**, same interface, same reason.
- **New repository** rather than extending `antier-intelligence-agent`, per §44.24,
  porting the reusable parts of the predecessor.
