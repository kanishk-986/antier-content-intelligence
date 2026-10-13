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

## Four defects in the listing extractor, all found by chasing independence

The §15 independence correction said the corpus was too self-reported. Fixing that
meant reading the independent sources that yielded nothing, and 24 of them reported
`no_feed` with a listing page sitting right there. The extractor could not read
them, for four separate reasons.

**1. A listing URL ending in a filename rejected every link.** The path-prefix
constraint tested `path.startswith(prefix + "/")`, and KPMG, Deloitte and EY list at
`/xx/en/our-insights.html`. Nothing is below a filename, so the pass rate was zero.
`_listing_prefix()` now reduces such a URL to its directory.

**2. Articles under a sibling path were dropped.** The World Bank lists at
`/ext/en/news` and publishes at `/en/news/press-release/2026/...`. A strict prefix
test rejected all eight press releases, each of which carried a date and a clean
slug. The constraint is now "under the listing's directory **or** inside one of its
topical segments", which still excludes
`/products-and-services/capital-liquidity-optimization` — the Phase 3b regression
that put the constraint there.

**3. A locale segment was treated as a topic.** With segment matching in place,
`ey.com/en_gl/insights` admitted 88 service pages, because `en_gl` matched every
path on the site. Enumerating locales is a losing game — `/xx`, `/en_gl`, `/en_us`,
`/global/en` — so `_is_locale()` matches the *shape*: one or two letters, optionally
a two-part tag. A prefix made only of locale segments is discarded entirely, since
`/global/en` prefixes an entire site.

**4. The post-redirect URL was never used.** `candidate_links()` received the URL
that was *requested*, not the one that answered. `kpmg.com/news` lands on
`/xx/en/media.html` whose articles live under `/xx/en/media/press-releases/`, so the
section was computed from a path that no longer existed. This one bug alone hid
KPMG's entire newsroom.

### And one data-integrity bug the fix exposed

With redirects followed properly, `cadwalader.com/press-releases` resolved to
**`hlc.com`** — a different firm. Same-host filtering then measures against the
*new* host, so every link on it qualifies, and the corpus gains items attributed to
a publisher that never wrote them. `_same_site()` now compares registrable domains
and the outcome is reported as `offsite_redirect`. A redirect that leaves the domain
changes who is speaking.

### What was actually gained

Three independent sources now read, verified by running the extractor and reading
the output:

| source | items | dates | bodies |
|---|---|---|---|
| World Bank | 8 | 2026-09 to 2026-10 | 319–750 words |
| KPMG | 5 | 2026-06 to 2026-08 | 1051–1258 words |
| EY | 12 | 2025 | 557–1138 words |

Deliberately **not** added, with the reason recorded in `listing_rules.yaml`:
BlackRock (its `/corporate/newsroom` redirects to the homepage, whose links are
evergreen marketing), Cadwalader (off-domain), and J.P. Morgan, Accenture and
NielsenIQ — only their `/insights` hubs resolve, and a page titled
"Agentic AI in M&A | Transaction Advisory | Accenture" is the marketing content
§2.2 keeps out. A readable page is not the same as a source.

## Finding a listing path is a repeatable operation

    python3 scripts/probe_listing.py --status no_feed error --independent-only
    python3 scripts/probe_listing.py --name "World Bank" "KPMG"

It probes candidate paths concurrently and scores each by the extractor's own
`candidate_links()`, so a path that scores is a path the pipeline can read — not
merely one that exists. It prints an `overrides:` block for `listing_rules.yaml`.

§41.1 requires a new source to be addable through configuration rather than code.
That only holds if *finding* the configuration is repeatable; otherwise every new
source is a hand investigation, which is how 24 of them stayed silent.

## Independence is a registry property, not a scoring one

§15's `source_credibility` now discounts self-reported and single-publisher evidence
(`SCORING.md`). That stops the score flattering a vendor-only corpus; it does not
make the corpus better. The registry has to.

Measured on the first full corpus:

| source type | in registry | yielded items | items | role |
|---|---|---|---|---|
| primary_company | 15 | 7 | 61 | primary party |
| protocol | 19 | 6 | 50 | primary party |
| regulator | 12 | 6 | 27 | independent |
| institution | 6 | 1 | 10 | independent |
| standards_body | 2 | **0** | 0 | independent |
| specialist | 12 | **0** | 0 | independent |
| research_firm | 29 | **0** | 0 | independent |
| data_platform | 10 | **0** | 0 | independent |

**75% of items came from primary parties, and 53 independent sources across four
types produced nothing at all.** The registry is not short of independent sources —
it is short of independent sources that can be *read*. Vendors publish clean feeds
on marketing infrastructure; research firms gate their work, and data platforms
render in JavaScript.

So the corpus composition is an *ingestion* outcome, not an editorial choice, and it
was invisible: a source that yields nothing leaves no trace in `content_items`.

## Every run records why a source was silent

`source_fetch_log` (migration 003) keeps one row per source per run: status, `via`,
HTTP status, counts and detail. `fetch_state` records the items a source produced
and so is silent about the runs where it produced none — which is the case that
matters, because a 403, a JavaScript-rendered listing and a genuinely quiet week are
indistinguishable in a corpus and only the third is acceptable.

    python3 scripts/source_health.py               # yield by type, independence share
    python3 scripts/source_health.py --actionable   # independent sources we can fix

The report sorts failures by who can fix them:

- `no_feed`, `no_listing`, `error` — **ours**: a missing listing rule or feed URL.
- `js_rendered` — needs a headless browser, deferred by §32 (Phase 3c).
- `blocked`, `blocked_known` — the publisher's decision. §10.2 and §33: a measured
  bot-block is reported, never retried blindly.

An independent source with a fixable status is the highest-value work in the system,
because it changes what every later stage is reasoning about.

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
