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

## Feed coverage is the real ingestion constraint

Measured on the first live run (2026-10-12), over the 12 highest-authority sources:

| Outcome | Count | Sources |
|---|---|---|
| RSS/Atom feed found and parsed | **3** | BIS, ESMA, FSB |
| **No discoverable feed** | **6** | Circle, Clearstream, Canton/Digital Asset, DTCC, LSEG, Mastercard |
| Blocked (HTTP 403) | 3 | Euroclear, FATF, IMF |

**Only a quarter of tier-10 sources are reachable by feed.** The no-feed set is
exactly the primary-announcement layer the blueprint values most — central
securities depositories, card networks, stablecoin issuers.

### After Phase 3b (static listing extraction)

Re-measured over the same 12 sources with the listing fallback enabled:

| Outcome | Before | After | Sources |
|---|---|---|---|
| Items stored | **18** | **41** | — |
| Reached | **3** | **6** | + Circle, LSEG, Mastercard |
| `js_rendered` | — | 2 | DTCC, Clearstream |
| Blocked (403) | 3 | 3 | Euroclear, FATF, IMF |
| No listing found | — | 1 | Digital Asset |

Listing extraction is config-driven (`config/sources/listing_rules.yaml`), so a new
source's news path is added without touching code (§41.1).

### What static extraction cannot reach

**Client-rendered sites.** DTCC and Clearstream ship a Next.js shell whose server
HTML carries navigation only — no amount of link heuristics will find articles that
the browser assembles. These are reported `js_rendered`, never silently empty, and
need Playwright (§8 "where permitted"). That is a deliberate open decision: Playwright
adds ~150 MB of browser binaries, so it is not installed on a guess.

### Two quality guards worth knowing

1. **Path-prefix constraint.** A candidate must sit under the listing page's own
   path. Without it, a three-word product slug like
   `/products-and-services/capital-liquidity-optimization` qualifies, and marketing
   copy enters the corpus — exactly what §2.2 forbids. This was a real defect caught
   on the first live run.
2. **Shared timestamps are flagged, not deleted.** Some sites stamp every page with
   one template date; others genuinely publish a batch same-day. Both look identical
   from here, so the date is kept and annotated `date_confidence: low` rather than
   nulled — nulling destroys what the §14 momentum engine needs.

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
