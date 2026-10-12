# PROMPTS — versioning guide

Prompts live in `prompts/` and are version-controlled because, like scoring weights,
they materially change system behaviour (§7.2). A prompt change is a reviewable diff.

## Rules

1. **One file per stage.** `prompts/<stage>.v<N>.md`. Never edit a released version in
   place — add `v2` and switch the reference in config.
2. **Every prompt declares its output schema.** LLM stages use structured outputs
   (CLAUDE.md rule 6); the schema lives beside the prompt and is validated on return.
3. **A prompt never computes a score.** It may judge a dimension (e.g. "how relevant
   is this to these capabilities, 0–1"); the weighted arithmetic is Python.
4. **Record which prompt version produced which row.** `intelligence`,
   `opportunities` and `qa_reviews` carry the prompt version in `metadata` so a
   behaviour change is traceable to a diff.
5. **Do not over-prescribe.** The blueprint's §2.3 priorities and §2.2 exclusions
   belong in the prompt; step-by-step scripts for judgement tasks do not.

## Stages that call the LLM

| Stage | Prompt | Output schema |
|---|---|---|
| Intelligence extraction | `prompts/intelligence.v1.md` | §11 schema |
| Narrative naming | `prompts/narrative_naming.v1.md` | name + description |
| Antier fit judgement | `prompts/antier_fit.v1.md` | the seven §15 dimensions, 0–1 each |
| Contrarian angle | `prompts/contrarian_angle.v1.md` | §17 four questions |
| Persona and format | `prompts/persona_format.v1.md` | §18 matrix |
| AI QA | `prompts/ai_qa.v1.md` | §19 decision object |
| Research dossier | `prompts/dossier.v1.md` | §22 fifteen sections |

None are written yet — they land with their stages in the vertical slice.
