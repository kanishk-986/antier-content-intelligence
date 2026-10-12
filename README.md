# Antier Content Intelligence & Opportunity Engine

An intelligence layer between the public information ecosystem and Antier's content
team. It discovers market signals, analyses narratives and sentiment, evaluates Antier
relevance, detects content whitespace, recommends differentiated topics per persona,
and routes them through AI QA into human editorial approval.

**It is not a scraper, a topic generator, or a publisher. It never publishes.** The
human team is the final editorial authority.

Specification: [`docs/MASTER_BLUEPRINT.md`](docs/MASTER_BLUEPRINT.md) v1.0. Every other
document in `docs/` derives from it; where they disagree, the blueprint governs.

## Read these first

| Document | What it covers |
|---|---|
| [`CLAUDE.md`](CLAUDE.md) | System constitution and coding rules |
| [`docs/PRD.md`](docs/PRD.md) | Problem, objective, non-goals, MVP scope, definition of done |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | Stage pipeline, contracts, determinism boundary |
| [`docs/DATA_MODEL.md`](docs/DATA_MODEL.md) | Schema |
| [`docs/SCORING.md`](docs/SCORING.md) | Every formula, all computed in Python |
| [`docs/SOURCE_POLICY.md`](docs/SOURCE_POLICY.md) | Authority tiers, social policy, crawl discipline |
| [`docs/QA_POLICY.md`](docs/QA_POLICY.md) | Adversarial AI QA, human authority |
| [`docs/ROADMAP.md`](docs/ROADMAP.md) | Phases, first milestone, what is blocked |
| [`docs/RUNBOOK.md`](docs/RUNBOOK.md) | Setup, daily cycle, troubleshooting |

## Setup

```bash
uv venv --python 3.12 .venv
VIRTUAL_ENV=.venv uv pip install -e ".[dev]"

cp .env.example .env     # fill in ANTHROPIC_API_KEY
chmod 600 .env
```

The key lives in `.env` and nowhere else — never in a shell command, never committed.

## Current state

**Phases 0–2 complete.** Repo and documentation, the Antier brand brain, and the
source registry are in place and tested. The pipeline itself is not built yet; the
next milestone is the §40 vertical slice.

```
Phase 0  Git repo + documentation          done
Phase 1  Antier brand brain                done
Phase 2  Excel/sheet source registry       done   89 sources
Phase 3  Ingestion + DB                    next
```

### Source registry

89 sources imported from the live Google Sheet into
[`config/sources/source_registry.csv`](config/sources/source_registry.csv), scored on
the §5.2 authority tiers:

| Tier | Class | Count |
|---|---|---|
| 10 | Regulators, official bodies, primary company announcements | 21 |
| 9 | Major institutions, protocols, standards bodies | 16 |
| 8 | Established research firms, data platforms, specialist media | 41 |
| 7 | Industry publications, specialist blogs | 11 |

Refresh it with `python3 scripts/import_source_registry.py` and review the diff — the
registry is configuration, so a change to it changes system behaviour.

**6 sources are measured unreachable** (Dune ×2 and DefiLlama ×2 return HTTP 403,
SSRN 403, research.4pillars 429) and are annotated in the registry. A bot-block must
never read as an empty feed.

## Tests

```bash
./.venv/bin/python -m pytest tests/ -q
```

Scoring and parsing are the tested surfaces, per `CLAUDE.md` rule 5 — they are where
things go wrong silently.

## Architecture decisions that deviate from §8

Two, both sanctioned by §40 and both reversible behind an interface:

1. **SQLite before PostgreSQL** for the vertical slice. Postgres, pgvector and Docker
   are absent from the build machine, and installing them before any pipeline code
   exists inverts §40. The §9 schema is implemented verbatim either way.
2. **In-process cosine similarity before pgvector**, same interface, same reason.

Recorded in [`docs/CHANGELOG.md`](docs/CHANGELOG.md).
