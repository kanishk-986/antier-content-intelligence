# CLAUDE.md — system constitution

**Read `docs/PRD.md` and `docs/ARCHITECTURE.md` before making changes.**

This file is the coding constitution for the Antier Content Intelligence & Opportunity
Engine. It is derived from the Master Blueprint v1.0 (September 2026), §31.1. Where
this file and the blueprint disagree, the blueprint governs and this file is wrong —
fix it rather than working around it.

## Hard rules

1. **Do not invent product requirements.** Everything buildable is in `docs/`. If a
   requirement is missing, say so and ask — do not fill the gap with a guess.
2. **Do not add dependencies without explaining why.** State the reason in the commit
   message. Prefer the standard library.
3. **Keep all configuration externalized.** Brand, personas, scoring weights, source
   registry and prompts live in `config/` and `prompts/`, never hard-coded. A new
   source must be addable through configuration alone (§41).
4. **Never commit secrets.** `.env.example` holds variable names only. Real values go
   in `.env` (gitignored) or a secret manager.
5. **Write tests for scoring and parsing logic.** These are the parts that silently
   go wrong. See `docs/SCORING.md` for the fixtures contract.
6. **Use structured outputs for LLM stages.** Every model call returns a schema, not
   prose. Schemas live beside their stage.
7. **Preserve deterministic scoring outside the LLM.** The LLM extracts and judges;
   arithmetic is Python. The same inputs must always produce the same score.
8. **Keep agent stages independently testable.** A stage takes data in and returns
   data out. No stage reaches across into another's internals.

## What this system is, and is not

It is an **intelligence layer between the public information ecosystem and Antier's
content team** (§1). It is not a scraper, not a topic generator, and not a publisher.

**It must never silently publish.** The human team is the final editorial authority
(§20). AI QA narrows the queue; humans decide.

## Priorities when they conflict (§2.3)

```
insight > news
analysis > reporting
narrative > event
commercial relevance > popularity
evidence > speculation
original angle > generic commentary
```

## What the system must avoid (§2.2)

Generic crypto news with no Antier connection · price-only commentary and token
predictions · topics already saturated across competitors unless Antier has a
genuinely differentiated thesis · unverified social-media claims presented as fact ·
AI-generated topics unsupported by credible evidence · content that forces a service
mention where no genuine expertise exists.

## Engineering conventions

- **Python 3.10+**, `src/` layout, one concern per module.
- **Storage goes through `src/database/store.py`.** The vertical slice runs on SQLite;
  Postgres + pgvector is a swap, not a rewrite. Never import a driver directly from a
  pipeline stage.
- **Efficiency rule (§10.2):** never reprocess the whole source universe. Track
  last-seen ids, content hashes and timestamps; fetch only new or changed content, and
  pass only new relevant material to the LLM.
- **Every content item carries source attribution and a retrieval timestamp** (§33).
- **Keep an audit trail for AI decisions and human overrides** (§33).
- **Version prompts and scoring weights** — they materially change behaviour (§7.2).
  A change to either is a reviewable diff, never an untracked tweak.

## Git rules (§7.2)

Remote is canonical. Feature branches, merged through pull requests. `main` protected.
Tests pass before merge. CI via GitHub Actions. Large or raw datasets live in object
storage or the database, never the repo.

## Build order

Follow `docs/ROADMAP.md`. The first milestone is a **working vertical slice, not
hundreds of files** (§40): Excel → 10 test sources → 50–100 items → dedupe → Claude
extraction → narrative clustering → Antier scoring → 10 opportunities → AI QA → JSON
plus a simple dashboard. Expand coverage only once that runs end to end.
