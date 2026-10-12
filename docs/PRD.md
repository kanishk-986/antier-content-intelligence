# PRD — Antier Content Intelligence & Opportunity Engine

Derived from `MASTER_BLUEPRINT.md` v1.0 (September 2026). The blueprint governs.

## 1. Problem

Antier's content team spends its time on research and comparison: reading the market,
working out what matters, and arguing about what to publish. The volume of public
information is not the constraint — relevance is. Generic crypto news, price
commentary and saturated takes all look like signal until someone reads them closely.

## 2. What this is

An **intelligence layer between the public information ecosystem and Antier's content
team** (§1). It discovers market signals, analyses narratives and sentiment, evaluates
Antier relevance, detects content whitespace, recommends differentiated topics per
persona, and routes them through AI QA into human editorial approval.

It is **not** a scraper, a topic generator, or a publisher.

## 3. Primary objective (§2.1)

Identify emerging narratives that are:

- important to Antier's target audiences
- aligned with Antier's actual capabilities
- commercially meaningful
- sufficiently novel
- evidence-backed
- suitable for differentiated thought leadership

## 4. Non-goals (§2.2)

- Generic crypto news with no Antier connection
- Price-only commentary and speculative token predictions
- Topics saturated across competitors, unless Antier has a genuinely differentiated thesis
- Unverified social-media claims presented as fact
- AI-generated topics that cannot be supported by credible evidence
- Content that forces a service mention where no genuine expertise exists

## 5. Ranking principle (§2.3)

`insight > news` · `analysis > reporting` · `narrative > event` ·
`commercial relevance > popularity` · `evidence > speculation` ·
`original angle > generic commentary`

## 6. Users and personas (§4)

| Persona | Content territory | Typical angle |
|---|---|---|
| **Antier Corporate** | solutions, market intelligence, enterprise use cases, case studies, technology | What enterprises need to build next |
| **CEO / Founder** | strategy, market structure, institutional adoption, regulation, capital markets | Why the market is changing and what leaders should do |
| **CTO / technical leader** | architecture, security, protocols, interoperability, wallets, scaling, AI infra | What is technically difficult and what infrastructure is missing |
| **Subject-matter expert** | deep specialist themes tied to real expertise | How a specific technology or problem works |

The same market event must produce **different** recommendations per persona, not
duplicate content (§18).

## 7. Content pillars (§3.1)

| Pillar | Priority |
|---|---|
| RWA & tokenization | Very High |
| Stablecoin infrastructure | Very High |
| Blockchain infrastructure | Very High |
| Enterprise AI | Very High |
| Institutional DeFi | High |
| Digital-asset infrastructure | High |
| Digital money & payments | High |
| Security & compliance | High |

## 8. Pipeline (§6)

Ingestion → intelligence extraction → narrative engine → Antier fit engine →
content strategy engine → AI QA → human QA dashboard → approved opportunities →
LinkedIn brief / article dossier / blog brief → performance feedback.

## 9. MVP scope (§32)

**In:** Excel source registry · RSS/web ingestion · database · deduplication ·
Claude structured extraction · sentiment · narrative clustering · trend score ·
Antier relevance · content opportunity cards · AI QA · human dashboard.

**Out:** LinkedIn publishing automation (NO).
**Later:** full competitor intelligence · advanced self-learning optimization.

## 10. Definition of done for MVP (§41)

1. A new source can be added through configuration without changing application code.
2. New content is fetched only when needed.
3. Duplicate stories are removed.
4. Every content item has structured intelligence.
5. Similar stories become narratives.
6. Each narrative receives trend and sentiment signals.
7. Every narrative receives an Antier relevance score.
8. Top opportunities include evidence, thesis, persona and format.
9. AI QA can reject weak or unsupported opportunities.
10. Human reviewers can approve / reject opportunities.
11. Approved opportunities generate research dossiers.
12. All code, configuration and prompts are version-controlled.
13. Secrets and raw operational data are not committed.
14. CI runs tests before changes merge.

## 11. Success metrics (§35)

Relevant opportunities per run (quality, not volume) ↑ · human approval rate ↑ ·
false-positive rate ↓ · unsupported-claim rate → near zero · duplicate-topic rate ↓ ·
novelty/whitespace quality ↑ · time saved per editorial cycle ↑ · published-topic
performance ↑ · business-qualified opportunities ↑.

## 12. Open questions carried from the blueprint

These are **not** invented requirements — they are gaps the blueprint leaves open and
that implementation must not silently decide:

1. **Antier knowledge base (§23).** The proof-of-expertise engine needs Antier's own
   services, case studies, playbooks and insights in machine-readable form. No such
   corpus exists yet in this repo.
2. **Competitor set (§24).** Named competitors and their content feeds are required
   for saturation analysis. Deferred to post-MVP by §32, so the MVP computes
   whitespace against Antier's own coverage and market-wide volume only.
3. **Published-performance data (§30).** The feedback loop needs impressions, likes,
   comments and lead data. Source and access are unspecified.
4. **LinkedIn access (§25).** Must use official APIs or approved access. The
   architecture keeps LinkedIn signals pluggable so this can be added or removed
   without touching the rest of the pipeline.
