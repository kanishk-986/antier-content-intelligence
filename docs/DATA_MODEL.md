# DATA_MODEL

Schema from `MASTER_BLUEPRINT.md` §9, implemented verbatim. Same tables on SQLite and
PostgreSQL; only column types and the vector index differ.

## sources (§9.1)

| Column | Notes |
|---|---|
| `id` | |
| `name` | |
| `url` | |
| `source_type` | regulator, institution, research, media, blog, community, social |
| `authority_score` | 1–10, from `SOURCE_POLICY.md` tiers |
| `topics` | list |
| `active` | |
| `last_checked_at` | drives the §10.2 efficiency rule |
| `last_item_at` | |

The registry in `config/sources/source_registry.csv` is the configured input; this
table is its runtime state. Adding a source must require no code change (§41.1).

## content_items (§9.2)

`id` · `source_id` · `url` · `title` · `author` · `published_at` · `retrieved_at` ·
`raw_text` · `clean_text` · `content_hash` · `language` · `metadata`

`content_hash` is the deduplication key (§10.2). `published_at` is only trusted when
confirmed from the page — never inferred from a URL slug.

## intelligence (§9.3)

`content_id` · `entities` · `topics` · `claims` · `market_sentiment` ·
`institutional_sentiment` · `developer_sentiment` · `regulatory_sentiment` ·
`enterprise_sentiment` · `importance_score`

One row per content item. Written by the LLM extraction stage using the §11 schema.
Note the blueprint lists five sentiment columns here while §13 defines six dimensions
— `community` is the sixth and is stored in the same group.

## narratives (§9.4)

`id` · `name` · `description` · `embedding` · `first_seen_at` · `last_seen_at` ·
`velocity` · `acceleration` · `saturation` · `status`

`status` ∈ `emerging` | `rising` | `stable` | `declining` (§12).
A narrative is a cluster of items, not an article. 100 items should become 10–20
narratives.

## opportunities (§9.5)

`id` · `narrative_id` · `thesis` · `antier_relevance` · `audience_relevance` ·
`commercial_relevance` · `authority_potential` · `novelty` · `source_credibility` ·
`whitespace` · `opportunity_score` · `persona` · `format` · `status`

The seven scored dimensions are the §15 weighted metrics. `opportunity_score` is
computed deterministically in Python from `config/scoring/weights.yaml`.

## qa_reviews (§9.6)

`opportunity_id` · `ai_decision` · `confidence` · `evidence_issues` ·
`factual_issues` · `brand_issues` · `risk_flags` · `human_decision` · `reviewer` ·
`reviewed_at`

`ai_decision` ∈ `APPROVE` | `REJECT` | `RESEARCH_MORE` (§19).
`human_decision` ∈ `APPROVE` | `REJECT` | `RESEARCH_MORE` | `REASSIGN_PERSONA` (§20).
This table is the §33 audit trail — rows are appended, never rewritten.
