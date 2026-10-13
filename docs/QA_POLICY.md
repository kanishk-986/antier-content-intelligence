# QA_POLICY

From `MASTER_BLUEPRINT.md` §19, §20, §13.

## AI QA is adversarial (§19)

**Its job is to find reasons not to publish.** An agent that approves everything has
failed. It asks:

1. Are the sources credible?
2. Are the important claims supported?
3. Is the narrative genuinely emerging, or merely noisy?
4. Is the topic too saturated?
5. Is the topic genuinely relevant to Antier?
6. Can Antier demonstrate legitimate expertise?
7. Is the recommended thesis stronger than a generic news summary?
8. Are there regulatory, reputational or factual risks?
9. Does the opportunity overlap with an already-approved topic?
10. Does the proposed persona make sense?

Structured output:

```json
{
  "decision": "APPROVE | REJECT | RESEARCH_MORE",
  "confidence": 0.0,
  "problems": [],
  "recommended_persona": "",
  "recommended_priority": "high|medium|low"
}
```

## Human QA is final (§20)

```
all discovered items -> AI ranking -> top 10-20 -> AI QA
    -> 5-10 human-review candidates
    -> human: Approve / Reject / Research More / Reassign Persona
    -> approved research dossier
```

**The human team remains the final editorial authority. The system must not silently
publish.** It reduces research and comparison work; it does not decide.

Every human decision is recorded with reviewer and timestamp in `qa_reviews` — the
§33 audit trail. Rejections keep their reason, because the dashboard must show
"rejected topics with reasons" (§27) and the feedback loop consumes them (§30).

## Fact / analysis / signal / speculation

Carried from the discovery predecessor and consistent with §19 and §26. Every claim in
a brief or dossier is labelled:

- **FACT** — what has happened, with a source and a confirmed date
- **ANALYSIS** — what it could indicate
- **SIGNAL** — what it may suggest about an emerging trend
- **SPECULATION** — possible future implications, not confirmed

**Speculation is never presented as fact.**

## Sentiment tension (§13)

Multidimensional sentiment, not a single polarity: market · institutional · developer
· regulatory · enterprise · community.

The engine must detect **tension** — e.g. strong institutional optimism alongside
developer frustration. Tension often produces the strongest thought-leadership
opportunities, so it is a feature to surface, not noise to average away.

## Claims requiring verification

Every research dossier carries an explicit "claims requiring verification" list
(§22.13). An unverifiable load-bearing claim blocks the dossier.

## How §19 is implemented

The reviewer is handed the **per-dimension scoring provenance** — each dimension's
value, the reason string behind it, and the list of dimensions that could not be
measured — under the heading "audit this, do not trust it". This matters: without
the provenance a reviewer can only re-read the articles and form a second opinion,
which is not an audit. With it, the reviewer can name the mechanism that produced a
score. In the first live run it did exactly that, citing the `treat_as_emerging`
rule by name.

**A non-APPROVE decision must state a problem.** The validator rejects an empty
`problems` list on REJECT or RESEARCH_MORE. A rejection with no reason cannot appear
in §27's "rejected topics with reasons" and carries nothing into §30's feedback
loop, so it is treated as malformed output rather than a judgement.

**Question 3 carries an explicit mandate.** 30% of the §15 weighting is recency
(velocity 20%, novelty 10%), so a fresh item can rank highly on timing alone. Rather
than retune the owner's weights, the prompt instructs rejection on question 3 when
timing is doing the work and substance is not, listing the tells: a cluster of one
or two items from a single source; novelty near 1.0 against low Antier relevance;
velocity produced by the `treat_as_emerging` zero-baseline rule, which means there
was no baseline rather than that attention is rising; and items that are not events
at all — job postings, conference listings, product pages, draft specifications,
support threads.

**The score is evidence, not a verdict.** The prompt says so, and says the output
carries no number except `confidence`. §15 arithmetic stays in Python (CLAUDE.md
rule 7); the reviewer argues about the inputs, never the total.

**`human_decision` is written by a person, never by the model.** `as_row()` leaves
it null and records `prompt_version` as `ai_qa.v1@<model>`, so a later change of
prompt or model is visible in the audit trail.
