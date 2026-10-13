# SOURCE COVERAGE — sheet mapped onto core services and ICPs

> **Updated 2026-10-13.** 23 curated sources added and 7 pruned; every service now
> has at least one reachable source, pinned by a test. The matrix below is the
> original 2026-10-12 measurement of the sheet **alone** — kept because it is the
> answer to "is the sheet useful". Current state:
>
> | # | Service | Open (sheet only) | Open (now) |
> |---|---|---:|---:|
> | 1 | RWA Tokenization | 20 | 21 |
> | 2 | Stablecoin Rails | 27 | 30 |
> | 3 | AI Agent Infrastructure | **1** | **12** |
> | 4 | Enterprise AI / InsurTech | **0** | **3** |
> | 5 | Institutional DeFi | 5 | 5 |
> | 6 | DePIN | **0** | **4** |
> | 7 | ZK Privacy | 2 | 7 |
> | 8 | Audits & Compliance | 21 | 23 |
>
> Live-tested: **17 of 23 additions work, 90 items** — a 74% hit rate against the
> sheet's 36%. Four are blocked (NAIC, InsurTech Insights and Healthcare IT News all
> 403; Coinbase 429) and two expose nothing (Aleo, Helium). Those are annotated in
> the registry, so Service 4 reads **adequate** rather than well covered — its
> coverage rests on CMS, Anthropic and IoT Analytics. **The open-web InsurTech and
> healthcare trade press is bot-blocked, so Service 4 remains the weakest service.**

Generated 2026-10-12 from `config/sources/source_registry.csv` (89 sources, all four
tabs of the owner's Research Resources sheet) against `config/brand/services.yaml`.

Regenerate: `python3 scripts/map_source_coverage.py`

## Verdict

| # | Service | ICPs | Sources | Open | Tier 9–10 | Verdict |
|---|---|---|---:|---:|---:|---|
| 1 | RWA Tokenization Infrastructure | mid-market asset managers, regional banks, private credit funds, family offices, commodity desks | 22 | 20 | 16 | well covered |
| 2 | Agentic Micropayments & Stablecoin Rails | mid-market fintechs, neobanks, NBFCs, AI-native startups | 30 | 27 | 18 | well covered |
| 3 | **AI Agent Infrastructure & Orchestration** | enterprise AI firms, crypto protocols, DAOs | **1** | **1** | 1 | **critical gap** |
| 4 | **Enterprise AI Orchestration & Data Modernization** | specialty insurance/InsurTech, healthcare, mid-cap vertical SaaS | 4 | **0** | 0 | **no reachable source** |
| 5 | Institutional DeFi & White-Label Lending | mid-tier community banks, credit unions, Islamic finance | 7 | 5 | 3 | well covered |
| 6 | **DePIN Integration & Monitoring** | logistics, retail, specialty manufacturing | **0** | **0** | 0 | **no source at all** |
| 7 | **ZK Privacy for Regulated Finance** | traditional banks, asset managers, government | 2 | 2 | 1 | thin |
| 8 | Protocol Security Audits & Compliance | DeFi protocols, Web3 infra, exchanges | 22 | 21 | 12 | well covered |

**The sheet is a stablecoins-and-tokenization list.** Services 1, 2, 5 and 8 are
genuinely well served. Services 3, 4, 6 and 7 — half the charter — are close to blind.

Service 3 is the sharpest problem: it is a **very-high** priority offering with
exactly one mapped source (Stripe/Bridge, matched on "orchestration" — a weak hit).
Service 4's four sources are **all gated** (Gartner, Kantar, NielsenIQ, Emergen), so
coverage is nominal rather than real.

## Recommended additions, by gap

Not from the sheet. These are open, primary-or-near-primary, and chosen to serve the
named ICPs rather than to add volume.

### Service 3 — AI Agent Infrastructure (ICPs: enterprise AI firms, protocols, DAOs)

| Source | Why | Tier |
|---|---|---|
| Ethereum Magicians / EIP repo (ERC-8004) | Primary venue for the agent-identity standard | 10 |
| Coinbase Developer Blog · x402 Foundation | x402 is the agent-payments protocol; primary announcements | 10 |
| Cloudflare Blog | Shipped agent identity + wallets; primary | 10 |
| MetaMask / Consensys Blog | Agent Wallet, permissioning patterns | 9 |
| Skyfire · Know Your Agent Network | The KYA layer the charter names as a service line | 7 |
| a16z crypto — AI x crypto | Agenda-setting thesis work | 8 |
| Fetch.ai / ASI, Ritual, EigenCloud | Agent infra protocol primaries | 8 |

### Service 4 — Enterprise AI Orchestration (ICPs: InsurTech, healthcare, vertical SaaS)

Nothing in the sheet is both relevant and open. This gap is total.

| Source | Why | Tier |
|---|---|---|
| CMS / HHS newsroom | Prior authorization and claims rules drive healthcare AI demand | 10 |
| NAIC (insurance commissioners) | Model AI governance bulletins for insurers | 10 |
| Anthropic / OpenAI enterprise blogs | Primary on agent orchestration capability | 9 |
| Celent (insurance practice) | Already in the sheet but gated — note the limit |  8 |
| InsurTech Insights · Digital Insurance | Open specialist trade press | 7 |
| Healthcare IT News · Fierce Healthcare | Open specialist trade press | 7 |

### Service 6 — DePIN (ICPs: logistics, retail, manufacturing)

| Source | Why | Tier |
|---|---|---|
| Helium Foundation, Akash, Render, peaq | Protocol primaries | 8 |
| IoT Analytics | Enterprise IoT market research, partly open | 8 |
| Messari DePIN research | Already in sheet; tag it to this service | 8 |
| DePIN Hub / Escape Velocity | Sector aggregation | 5 |

### Service 7 — ZK Privacy for Regulated Finance (ICPs: banks, asset managers, government)

| Source | Why | Tier |
|---|---|---|
| BIS Innovation Hub (Projects Tourbillon, Aurum) | Primary central-bank privacy work | 10 |
| EY Nightfall | Already mapped; the one real asset here | 8 |
| Zcash/ECC, Aztec, Aleo, Boundless | ZK protocol primaries | 8 |
| ZKProof.org | Standards body | 8 |
| a16z crypto — privacy | Thesis work | 8 |

## Quality problems inside the sheet

Measured by running all 22 *Specific Websites* through the pipeline (49 items):

- **35% of retrieved titles match any Antier pillar keyword.** Two sources returned
  **zero**: **Teroxx** (retail trading psychology — the price/speculation content §2.2
  excludes) and **Mento** (onchain FX protocol news, no institutional buyer angle).
- **Getorbital's most recent items are from November 2024** — two years stale.
- **Four duplicate rows**: Artemis ×2, Dune ×2, DefiLlama ×2, 4 Pillars ×2. 23 rows
  resolve to ~17 distinct properties.
- **6 of 22 are bot-blocked** (Dune, DefiLlama, SSRN, research.4pillars) and
  **3 are client-rendered** (Celent, 4 Pillars, Visa Onchain Analytics). Neither is
  fixable by configuration.
- **Only 8 of 22 produce content at all.**

## Structural note

The *Specific Websites* tab is **analysts and data platforms commenting on the
market**. §5.2 puts primary sources at tier 10 — regulators and *primary
company/protocol announcements* — and those live on the **Generic** tab. The
pipeline's best results came from exactly there: BIS, ESMA, FSB, Circle, Mastercard,
LSEG.

Treat *Specific Websites* as a secondary interpretation layer, not the research
universe. On its own it would build narratives out of commentary rather than events,
and §12 requires a narrative to rest on the underlying announcement.

## Still empty

*Specific People* and *Inspirational LinkedIn Posts* remain headers with no rows.
Both agents are blind to named individuals as a result.
