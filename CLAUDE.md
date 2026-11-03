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

## Behaviour guidelines (karpathy-guidelines)

Follow these on every task. Skill copy: `.claude/skills/karpathy-guidelines/SKILL.md`. Project-specific instructions above take precedence where they conflict.
**Tradeoff:** These guidelines bias toward caution over speed. For trivial tasks, use judgment.

### 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

### 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

### 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it - don't delete it.

When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

### 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:
```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

---

**These guidelines are working if:** fewer unnecessary changes in diffs, fewer rewrites due to overcomplication, and clarifying questions come before implementation rather than after mistakes.
