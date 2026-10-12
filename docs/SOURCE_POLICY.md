# SOURCE_POLICY

From `MASTER_BLUEPRINT.md` §5, §12, §25, §26, §33.

## Registry

`config/sources/source_registry.csv` is the source universe, under version control as
configuration (§5). Columns (§5.1):

```
source_id, source_name, url, source_type, category, authority_score,
crawl_frequency, region, topics, personas, active, last_seen_at, notes
```

A new source is added by editing this file. **No code change** (§41.1).

## Authority tiers (§5.2)

| Tier | Source class | Default authority |
|---|---|---|
| 10 | Regulators, official government/institutional releases, primary company/protocol announcements | 10 |
| 9 | Major financial institutions, established protocols, primary research | 9 |
| 8 | Established research firms, high-quality specialist media | 8 |
| 7 | Industry publications, specialist blogs | 7 |
| 5 | Community and secondary commentary | 5 |
| 3 | Social posts, early signals | 3 |
| 1 | Anonymous, unverified, low-quality | 1 |

**Popularity is not authority** (§5.2).

## Source-quality order (§12)

official/primary → regulatory/government → institutional research → established
financial publication → established specialist publication → reputable industry
publication → company commentary → social media → unverified.

Uncertain information is labelled **"Unverified"** or **"Reported by X; not
independently confirmed."** An unverified social post is never established fact.

## Social signals (§26)

Early-signal layer, not truth.

- Use social volume to detect emerging questions and narratives.
- Verify factual claims against primary sources.
- Record source type and confidence on every item.
- **Never convert a viral social claim directly into an Antier fact.**
- Recurring community questions are themselves content signals.

## LinkedIn (§25)

Use official APIs or approved data access. **Do not build the system around
unauthorized scraping.** LinkedIn signals must be addable or removable without
affecting the rest of the pipeline — it is a plug-in signal source, not a dependency.

## Crawl discipline (§10.2, §33)

Track last-seen ids, content hashes and timestamps per source; fetch only new or
changed content. Respect site terms, API limits and platform policies. Keep raw
crawled content out of Git. Define retention policies. Use least-privilege
credentials.

## Known-unreachable sources

Reachability is **measured, not assumed**, and re-probed periodically. As of
2026-10-06, probing the predecessor source list found these blocked — they must be
reported as blocked rather than silently empty, and their figures sourced from citing
secondary coverage, never invented:

| Source | Status |
|---|---|
| `dune.com` | HTTP 403 |
| `defillama.com` | HTTP 403 |
| `ssrn.com` | HTTP 403 |
| `research.4pillars.io` | HTTP 429 (rate limited) |

Gated sources (Celent, FXC Intelligence, parts of SSRN, most strategy houses) are
declared **GATED** and not spent on. The registry's `notes` column records this.
