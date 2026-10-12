# RUNBOOK

## Prerequisites

| Requirement | Status on the build machine (2026-10-12) |
|---|---|
| Python 3.10+ | ✅ 3.12.13 via uv |
| Node 18+ | ✅ v24.19.0 |
| `gh` CLI | ⚠️ installed (2.97.0) but **not logged in** |
| Docker | ❌ not installed |
| PostgreSQL / pgvector | ❌ not installed — SQLite used for the vertical slice |
| `ANTHROPIC_API_KEY` | ❌ not set |

## Setup

```bash
uv venv --python 3.12 .venv
VIRTUAL_ENV=.venv uv pip install -e ".[dev]"

cp .env.example .env     # fill in ANTHROPIC_API_KEY, then:
chmod 600 .env
```

The key goes in `.env` and nowhere else — never in a shell command, never committed.
Load it with `export $(grep -v '^#' .env | xargs)`; that keeps it out of shell history
and out of `ps`.

## Daily operating cycle (§28)

Example timings from the blueprint. **Implementation uses configurable schedules, not
hard-coded times** (§28).

| Time | Activity |
|---|---|
| 06:00 | Poll curated sources and APIs |
| 06:15 | Normalize and deduplicate |
| 06:30 | LLM intelligence extraction |
| 06:50 | Narrative clustering |
| 07:10 | Trend / sentiment calculation |
| 07:25 | Antier relevance and whitespace scoring |
| 07:40 | Persona / angle generation |
| 07:55 | AI QA |
| 08:10 | Dashboard ready for human review |

## Refreshing the source registry

```bash
python3 scripts/import_source_registry.py     # live sheet -> config/sources/source_registry.csv
```

Review the diff before committing — the registry is configuration, so a change to it
is a reviewable change to system behaviour.

## Troubleshooting

**A source returns nothing.** Check `SOURCE_POLICY.md` → known-unreachable sources
first. Dune, DefiLlama, SSRN and research.4pillars are bot-blocked; that is expected
and must be reported as blocked, not as empty.

**Scores look inflated.** Check whether the competitor-saturation axis is reporting
`not yet measured` rather than zero (`SCORING.md`). A missing input must never read as
"no saturation".

**Velocity is infinite or undefined.** A narrative with a zero baseline. See the
`SCORING.md` edge case — the implementation must record which rule it applied.

**Git push fails with a credential error.** The predecessor repo used a
session-scoped credential file. Run `gh auth login` for a durable credential.

## Weekly intelligence report (§29)

Top rising narratives · emerging but not yet saturated · gaining institutional
traction · regulatory tension · topics competitors overuse · topics competitors ignore
· topics Antier should own · CEO opportunities · CTO opportunities · long-form
opportunities · previous-week performance.
