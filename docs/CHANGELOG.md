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

### Decisions recorded
- **SQLite before PostgreSQL** for the vertical slice, behind `src/database/store.py`.
  Postgres, pgvector and Docker are absent from the build machine; installing them
  before any pipeline code exists inverts §40. The §9 schema is implemented verbatim
  either way, and the swap is an interface implementation, not a rewrite.
- **In-process cosine similarity before pgvector**, same interface, same reason.
- **New repository** rather than extending `antier-intelligence-agent`, per §44.24,
  porting the reusable parts of the predecessor.
