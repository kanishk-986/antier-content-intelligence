# MASTER BLUEPRINT — verbatim export

Source: Google Doc `1hWQDsaGewDoJyocQpputcMgXJi9ZJWOc`, exported 2026-10-12.
This is the owner specification. Every other file in `docs/` is derived from it.
Where a derived doc disagrees with this file, **this file governs**.

---

Antier Content Intelligence & Opportunity Engine
Master Product Requirements, System Architecture, Git-First Implementation Roadmap & Claude Code Build Blueprint
Version 1.0 • September 2026
Purpose: build a production-oriented content intelligence system for Antier that discovers market signals, analyzes narratives and sentiment, evaluates Antier relevance, detects content whitespace, recommends differentiated topics for the company/CEO/CTO, and routes them through AI QA and human editorial approval.
1. Executive Summary
The proposed system is not a simple content scraper or topic generator. It is an intelligence layer between the public information ecosystem and Antier's content team.
Internet + curated sources
       ↓
Collection → normalization → deduplication
       ↓
Entity/topic/sentiment extraction
       ↓
Narrative clustering + momentum detection
       ↓
Antier capability + audience + commercial-fit scoring
       ↓
Content whitespace + competitor saturation analysis
       ↓
Persona + angle + format recommendation
       ↓
Adversarial AI QA
       ↓
Human QA approval
       ↓
Research dossier → LinkedIn / long-form article / blog
Antier's current site positions the company around purpose-built AI and blockchain infrastructure for institutions and enterprises, with infrastructure disciplines including RWA tokenization, stablecoin rails, protocol engineering, enterprise AI, institutional DeFi and enterprise wallets. The site also highlights advisory, pre-built and tailored applications and production-oriented digital asset infrastructure. citeturn0search0
The system should therefore optimize for authority, commercial relevance and differentiated insight—not raw news volume.
2. Antier Content Intelligence Objective
2.1 Primary objective
Identify emerging narratives that are important to Antier's target audiences, aligned with Antier's actual capabilities, commercially meaningful, sufficiently novel, evidence-backed, and suitable for differentiated thought leadership.
2.2 What the system must avoid
* Generic crypto news with no Antier connection.
* Price-only commentary and speculative token predictions.
* Topics already saturated across competitors unless Antier has a genuinely differentiated thesis.
* Unverified social-media claims presented as facts.
* AI-generated topics that cannot be supported by credible evidence.
* Content that forces a service mention where no genuine expertise exists.
2.3 Core principle
Prefer:
insight > news
analysis > reporting
narrative > event
commercial relevance > popularity
evidence > speculation
original angle > generic commentary
3. Antier Content Brain
The first implementation task is to turn Antier's public positioning into a machine-readable brand knowledge base. Antier's About page describes its purpose around engineering trust on blockchain and applying intelligence with AI, and identifies Vikram R Singh as CEO & Founder. citeturn0search3
3.1 Initial content pillars
Pillar
	Examples
	Priority
	RWA & tokenization
	asset tokenization, funds, real estate, commodities, securities, token standards, compliance
	Very High
	Stablecoin infrastructure
	stablecoin rails, payments, remittance, settlement, issuance, treasury workflows
	Very High
	Institutional DeFi
	institutional lending, liquidity, custody, settlement, compliant DeFi
	High
	Digital-asset infrastructure
	wallets, custody, exchanges, payments, MPC, account infrastructure
	High
	Blockchain infrastructure
	protocol engineering, L1/L2, rollups, interoperability, chain abstraction, smart contracts
	Very High
	Enterprise AI
	AI infrastructure, agentic systems, AI + blockchain, autonomous workflows
	Very High
	Digital money & payments
	digital banking, cross-border payments, tokenized money, payment rails
	High
	Security & compliance
	smart-contract security, monitoring, KYC/AML, governance, regulatory architecture
	High
	Antier's RWA infrastructure pages specifically describe enterprise tokenization infrastructure, lifecycle support from issuance through corporate actions and secondary-market connectivity, and standards including ERC-20, ERC-3643, ERC-4626 and ERC-7943. citeturn0search1
Antier's asset-tokenization offering also spans equities, funds, real estate, commodities and alternative assets, with issuance, investor onboarding, compliance, custody, secondary-market and interoperability capabilities. citeturn0search2
4. Personas
Persona
	Primary content territory
	Typical angle
	Antier Corporate
	solutions, market intelligence, enterprise use cases, case studies, technology
	What enterprises need to build next
	CEO / Founder
	strategy, market structure, institutional adoption, regulation, capital markets, future of digital assets
	Why the market is changing and what leaders should do
	CTO / technical leader
	architecture, security, protocols, interoperability, wallets, scaling, AI infrastructure
	What is technically difficult and what infrastructure is missing
	Subject-matter expert
	deep specialist themes tied to actual expertise
	How a specific technology/problem works
	5. Source Universe & Excel Registry
The user's existing Excel workbook becomes the source registry. It should be imported into Git as configuration/data—not kept as an opaque local-only artifact.
5.1 Recommended source columns
source_id
source_name
url
source_type
category
authority_score
crawl_frequency
region
topics
personas
active
last_seen_at
notes
5.2 Source tiers
Tier
	Source class
	Default authority
	10
	Regulators, official government/institutional releases, primary company/protocol announcements
	10
	9
	Major financial institutions, established protocols, primary research
	9
	8
	Established research firms and high-quality specialist media
	8
	7
	Industry publications and specialist blogs
	7
	5
	Community and secondary commentary
	5
	3
	Social posts / early signals
	3
	1
	Anonymous, unverified or low-quality sources
	1
	The system should never treat source popularity as equivalent to source authority.
6. End-to-End Architecture
                    ANTIER CONTENT INTELLIGENCE ENGINE

Sources / Web / APIs / RSS / approved social signals / research
                             ↓
                   [1] INGESTION LAYER
                             ↓
              Clean → Normalize → Deduplicate
                             ↓
                 [2] INTELLIGENCE LAYER
          Entities • Topics • Sentiment • Claims
                             ↓
                  [3] NARRATIVE ENGINE
      Embeddings → clustering → momentum → emergence
                             ↓
                  [4] ANTIER FIT ENGINE
      Capability • Audience • Commercial • Authority
                             ↓
               [5] CONTENT STRATEGY ENGINE
      Whitespace • Persona • Hook • Angle • Format
                             ↓
                   [6] AI QA ENGINE
      Evidence • novelty • risk • brand fit • conflicts
                             ↓
                   [7] HUMAN QA DASHBOARD
                             ↓
              Approved research opportunities
                             ↓
          LinkedIn brief / article dossier / blog brief
                             ↓
                    Performance feedback
7. Git-First Architecture
The requirement is that the project be stored and versioned in Git rather than treated as a local-only project. The correct interpretation is: Git is the source of truth; local workspaces are disposable working copies. Do not commit secrets, private credentials, caches, raw crawl dumps, or database volumes.
7.1 Recommended repository
antier-content-intelligence/
├── README.md
├── CLAUDE.md
├── .gitignore
├── .env.example
├── docker-compose.yml
├── pyproject.toml
├── package.json
├── docs/
│   ├── PRD.md
│   ├── ARCHITECTURE.md
│   ├── DATA_MODEL.md
│   ├── SCORING.md
│   ├── SOURCE_POLICY.md
│   ├── QA_POLICY.md
│   └── RUNBOOK.md
├── config/
│   ├── brand/
│   │   ├── antier.yaml
│   │   ├── company.yaml
│   │   ├── ceo.yaml
│   │   └── cto.yaml
│   ├── scoring/
│   │   └── weights.yaml
│   └── sources/
│       └── source_registry.csv
├── src/
│   ├── ingestion/
│   ├── intelligence/
│   ├── narratives/
│   ├── scoring/
│   ├── agents/
│   ├── briefs/
│   ├── database/
│   └── api/
├── prompts/
├── dashboard/
├── migrations/
├── tests/
├── scripts/
└── .github/
   └── workflows/
7.2 Git rules
* Remote repository is the canonical source of code and configuration.
* Use feature branches for changes; merge through pull requests.
* Protect main/master branch.
* Require tests before merge.
* Use GitHub Actions for linting, tests and deployment.
* Use .env.example for variable names only.
* Store production secrets in GitHub Actions/hosting secret managers, never in Git.
* Store large/raw datasets in object storage or a database, not the repository.
* Commit schemas, prompts, configuration, source metadata and documentation.
* Version prompts and scoring weights because they materially change system behavior.
8. Recommended Technology Stack
Layer
	Recommended choice
	Reason
	Application
	Python + FastAPI
	Fast development, APIs, data/AI ecosystem
	LLM orchestration
	Python service with explicit agent stages
	Avoid unnecessary multi-agent complexity
	LLM
	Claude
	Strong reasoning, extraction, synthesis and QA
	Database
	PostgreSQL
	Reliable relational store
	Vector search
	pgvector
	Keeps MVP architecture simple
	Extraction
	Trafilatura / BeautifulSoup / Playwright where permitted
	Article/page extraction
	RSS
	feedparser
	Low-cost source polling
	Scheduling
	cron initially; Celery/worker later
	Simple first, scalable later
	Dashboard
	Next.js or Streamlit MVP
	Fast internal review workflow
	CI/CD
	GitHub Actions
	Git-first automation
	Containerization
	Docker
	Reproducible deployment
	Hosting
	Railway/Render/AWS/DigitalOcean
	Choose based on scale/security requirements
	9. Core Data Model
9.1 Source
sources(
id,
name,
url,
source_type,
authority_score,
topics,
active,
last_checked_at,
last_item_at
)
9.2 Content item
content_items(
id,
source_id,
url,
title,
author,
published_at,
retrieved_at,
raw_text,
clean_text,
content_hash,
language,
metadata
)
9.3 Intelligence record
intelligence(
content_id,
entities,
topics,
claims,
market_sentiment,
institutional_sentiment,
developer_sentiment,
regulatory_sentiment,
enterprise_sentiment,
importance_score
)
9.4 Narrative
narratives(
id,
name,
description,
embedding,
first_seen_at,
last_seen_at,
velocity,
acceleration,
saturation,
status
)
9.5 Opportunity
opportunities(
id,
narrative_id,
thesis,
antier_relevance,
audience_relevance,
commercial_relevance,
authority_potential,
novelty,
source_credibility,
whitespace,
opportunity_score,
persona,
format,
status
)
9.6 QA review
qa_reviews(
opportunity_id,
ai_decision,
confidence,
evidence_issues,
factual_issues,
brand_issues,
risk_flags,
human_decision,
reviewer,
reviewed_at
)
10. Ingestion Agent
Responsibility: discover and normalize new information. It must not decide whether a topic is good for Antier.
10.1 Output schema
{
 "title": "",
 "url": "",
 "source": "",
 "source_type": "",
 "published_at": "",
 "author": "",
 "content": "",
 "entities": [],
 "keywords": [],
 "retrieved_at": ""
}
10.2 Efficiency rule
Never reprocess the entire source universe on every run. Track last-seen identifiers, hashes and timestamps. Fetch only new/changed content, then pass only relevant new material into the LLM pipeline.
11. Intelligence Extraction
Each content item is transformed into structured intelligence: entities, topics, claims, sentiment dimensions, implications and importance.
{
 "primary_topic": "",
 "secondary_topics": [],
 "entities": [],
 "sentiment": {
   "market": 0.0,
   "institutional": 0.0,
   "developer": 0.0,
   "regulatory": 0.0,
   "enterprise": 0.0,
   "community": 0.0
 },
 "market_implication": "",
 "technical_implication": "",
 "business_implication": "",
 "importance": 0.0
}
12. Narrative Detection & Clustering
The system should not simply rank articles. It should combine multiple articles/posts into narratives.
100 individual items
       ↓
embeddings
       ↓
similarity / clustering
       ↓
10–20 narratives
       ↓
narrative velocity
       ↓
narrative acceleration
       ↓
emerging / rising / stable / declining
Example: several separate stories about Visa, Stripe, banks and stablecoin settlement should be recognized as one broader narrative around stablecoins becoming payment infrastructure.
13. Sentiment Engine
Use multidimensional sentiment rather than a single positive/negative label.
Dimension
	Question
	Market
	How is the broader market reacting?
	Institutional
	How are banks, funds and institutions reacting?
	Developer
	How are builders reacting?
	Regulatory
	What is the regulatory tone?
	Enterprise
	Does enterprise sentiment indicate adoption or resistance?
	Community
	What is the broader user/community reaction?
	The system should also detect sentiment tension—for example, strong institutional optimism combined with developer frustration. Such tension often creates stronger thought-leadership opportunities.
14. Trend & Momentum Engine
For each narrative calculate current volume, baseline volume, growth rate, acceleration, unique-source count, authoritative-source count and recency.
Trend Velocity
= current_mentions / baseline_mentions

Acceleration
= change_in_velocity

Authority Coverage
= weighted authoritative sources / total sources

Emergence
= velocity + acceleration + novelty + source diversity
Use windows such as 24 hours, 7 days and 30 days so the system can distinguish breaking events from durable narratives.
15. Antier Relevance Engine
This is the central differentiator.
Metric
	Weight
	Meaning
	Trend velocity
	20%
	Is attention increasing?
	Antier relevance
	20%
	Does the topic map to actual capabilities?
	Audience relevance
	15%
	Does it matter to target buyers/readers?
	Commercial relevance
	15%
	Can it create meaningful business context?
	Authority potential
	10%
	Can Antier add expert insight?
	Novelty
	10%
	Is there a differentiated angle?
	Source credibility
	10%
	Can the topic be evidenced reliably?
	Opportunity score = weighted sum of the above dimensions. Use thresholds: below 5 = reject; 5–7 = monitor; 7–8 = good; 8–9 = priority; 9–10 = immediate editorial review.
16. Content Saturation & Whitespace
A topic can be highly relevant but still be a poor opportunity if every competitor has already published the same take.
Signal
	Interpretation
	High market demand + high competitor saturation
	Likely crowded
	High market demand + low competitor saturation
	Strong opportunity
	Low market demand + low saturation
	Monitor
	High Antier capability + low Antier coverage
	Potential authority whitespace
	Track competitor themes, Antier's own historical themes and market-wide coverage to identify topics that are important but under-discussed.
17. Contrarian / Differentiated Angle Agent
For every high-scoring narrative, ask four questions:
1. What is the market consensus?
2. What is the consensus missing?
3. What is technically misunderstood?
4. What business implication is under-discussed?
Example: instead of publishing another stablecoin announcement, the agent might propose a thesis around the shift from stablecoin issuance to stablecoin orchestration and treasury infrastructure.
18. Persona & Format Engine
Narrative
	Corporate
	CEO
	CTO
	Stablecoin infrastructure
	What enterprises need to deploy
	Why market structure is changing
	What infrastructure is missing
	RWA tokenization
	Enterprise adoption/use cases
	Capital-market implications
	Token standards, compliance and architecture
	Chain abstraction
	Business value of multi-chain access
	Why fragmented liquidity matters
	Technical architecture and interoperability
	AI agents + payments
	Enterprise opportunities
	Autonomous commerce thesis
	Agent identity, wallets and settlement architecture
	The same market event should produce different recommendations rather than duplicate content.
19. AI Quality Analyst
The AI QA agent should be adversarial. Its job is to find reasons not to publish.
* Are the sources credible?
* Are the important claims supported?
* Is the narrative genuinely emerging or merely noisy?
* Is the topic too saturated?
* Is the topic genuinely relevant to Antier?
* Can Antier demonstrate legitimate expertise?
* Is the recommended thesis stronger than a generic news summary?
* Are there regulatory, reputational or factual risks?
* Does the opportunity overlap with an already approved topic?
* Does the proposed persona make sense?
{
 "decision": "APPROVE | REJECT | RESEARCH_MORE",
 "confidence": 0.0,
 "problems": [],
 "recommended_persona": "",
 "recommended_priority": "high|medium|low"
}
20. Human QA Workflow
All discovered items
       ↓
AI ranking
       ↓
Top 10–20 opportunities
       ↓
AI QA
       ↓
5–10 human-review candidates
       ↓
Human:
Approve / Reject / Research More / Reassign Persona
       ↓
Approved research dossier
The human team remains the final editorial authority. The system reduces research and comparison work; it should not silently publish.
21. Content Opportunity Card
CONTENT OPPORTUNITY
Narrative:
Why now:
Evidence:
Trend velocity:
Sentiment:
Antier relevance:
Commercial relevance:
Authority potential:
Saturation:
Content whitespace:
Recommended persona:
Recommended format:
Core thesis:
Contrarian angle:
Supporting sources:
AI QA:
Human status:
22. Research Dossier for Long-Form Content
After human approval, do not immediately generate a finished blog. First generate a research dossier.
1. Working title
2. Core thesis
3. Why now
4. Evidence and statistics
5. Primary sources
6. Secondary sources
7. Technical context
8. Business context
9. Regulatory context
10. Counterarguments
11. Antier perspective
12. Relevant Antier proof/case studies
13. Claims requiring verification
14. Suggested article structure
15. Suggested LinkedIn derivative angles
Antier's current site already publishes research-style material such as RWA licensing and technology playbooks, so the discovery engine should be designed to feed evidence-backed long-form thought leadership rather than only short social posts. citeturn0search0turn0search2
23. Proof-of-Expertise Engine
For every opportunity, search Antier's own knowledge base for relevant services, case studies, playbooks, insights and product capabilities.
Narrative
  ↓
Antier service match
  ↓
Relevant case study?
Relevant insight?
Relevant playbook?
Relevant technical capability?
Relevant spokesperson?
  ↓
Authority score
Antier's site currently highlights production engagements including a regulated tokenized-asset platform, a stablecoin remittance platform, and infrastructure for a regulated enterprise blockchain network. citeturn0search0
24. Competitor Intelligence
Add competitors after the MVP is stable. Track topic coverage, publication frequency, engagement where legally/technically available, positioning, narrative response speed and content saturation.
The objective is not to copy competitors. It is to identify overcrowded narratives and under-served authority positions.
25. LinkedIn Strategy & Compliance
LinkedIn should be treated as a distinct signal and publishing environment. Use official APIs or approved data access where available and avoid building the system around unauthorized scraping. The architecture should allow LinkedIn signals to be added or removed without affecting the rest of the pipeline.
The discovery engine should primarily use LinkedIn for approved/accessible company or public signals and use the broader web, primary sources and research sources for verification.
26. Reddit / X / Social Signals
Social platforms are best treated as early-signal layers rather than unquestioned truth.
* Use social volume to detect emerging questions and narratives.
* Use primary sources to verify factual claims.
* Record the source type and confidence.
* Never convert a viral social claim directly into an Antier fact.
* Use recurring community questions as potential content signals.
27. Dashboard
Recommended first dashboard sections:
* Today's emerging narratives
* Top Antier opportunities
* CEO opportunities
* CTO opportunities
* Corporate opportunities
* Content whitespace
* Competitor saturation
* AI QA queue
* Human review queue
* Approved research dossiers
* Rejected topics with reasons
* Historical topic performance
The primary interface should allow one-click actions: Approve, Reject, Research More, Assign Persona, Create LinkedIn Brief, Create Long-Form Dossier.
28. Daily Operating Cycle
Time
	Activity
	06:00
	Poll curated sources and APIs
	06:15
	Normalize and deduplicate
	06:30
	LLM intelligence extraction
	06:50
	Narrative clustering
	07:10
	Trend/sentiment calculation
	07:25
	Antier relevance and whitespace scoring
	07:40
	Persona/angle generation
	07:55
	AI QA
	08:10
	Dashboard ready for human review
	These are example timings; implementation should use configurable schedules rather than hard-coded times.
29. Weekly Intelligence Report
* Top rising narratives.
* Emerging narratives not yet saturated.
* Narratives gaining institutional traction.
* Narratives with regulatory tension.
* Topics competitors are overusing.
* Topics competitors are ignoring.
* Topics Antier should own.
* CEO thought-leadership opportunities.
* CTO technical opportunities.
* Long-form article opportunities.
* Previous-week topic performance.
30. Feedback Loop
The system becomes substantially more valuable once published content performance feeds back into the scoring engine.
Input
	Stored signal
	Published post
	topic, persona, hook, format, date
	Engagement
	impressions, likes, comments, reposts
	Audience
	profile visits, relevant audience response
	Business
	leads or qualified inquiries where available
	Editorial
	human approval/rejection reason
	Outcome
	strong/weak topic classification
	The system can then learn that certain themes perform better for Antier's actual audience without blindly optimizing for vanity metrics.
31. Claude Code Build Strategy
Claude Code should be used as the software-engineering environment that builds and maintains the repository. The production application should remain a normal version-controlled service with explicit jobs, tests, APIs and model calls.
31.1 First instruction to Claude Code
Read CLAUDE.md, docs/PRD.md and docs/ARCHITECTURE.md before making changes.
Do not invent product requirements.
Do not add dependencies without explaining why.
Keep all configuration externalized.
Never commit secrets.
Write tests for scoring and parsing logic.
Use structured outputs for LLM stages.
Preserve deterministic scoring outside the LLM.
Keep agent stages independently testable.
31.2 Build sequence
5. Create Git repository and branch protection.
6. Create CLAUDE.md and product documentation.
7. Create Antier brand/persona configuration.
8. Import Excel source registry.
9. Build PostgreSQL schema and migrations.
10. Build source ingestion.
11. Build normalization and deduplication.
12. Build structured intelligence extraction.
13. Build embeddings and narrative clustering.
14. Build sentiment and momentum scoring.
15. Build Antier relevance scoring.
16. Build whitespace and saturation analysis.
17. Build persona/angle generation.
18. Build AI QA.
19. Build dashboard.
20. Add scheduler and CI/CD.
21. Add Reddit/search/social signal layers.
22. Add competitor intelligence.
23. Add historical-performance feedback.
32. MVP Scope
Do not build everything at once.
MVP
	Include?
	Excel source registry
	YES
	RSS/web ingestion
	YES
	PostgreSQL
	YES
	Deduplication
	YES
	Claude structured extraction
	YES
	Sentiment
	YES
	Narrative clustering
	YES
	Trend score
	YES
	Antier relevance
	YES
	Content opportunity cards
	YES
	AI QA
	YES
	Human dashboard
	YES
	LinkedIn publishing automation
	NO
	Full competitor intelligence
	LATER
	Advanced self-learning optimization
	LATER
	33. Security & Data Governance
* Never commit API keys, cookies, access tokens or database passwords.
* Use secret-manager/environment variables.
* Keep raw source data separate from Git.
* Log model calls without storing unnecessary sensitive content.
* Add source attribution and retrieval timestamps.
* Keep an audit trail for AI decisions and human overrides.
* Use least-privilege credentials.
* Define retention policies for crawled content.
* Respect site terms, API limits and applicable platform policies.
34. Testing Strategy
Area
	Tests
	Source ingestion
	URL parsing, RSS failure, duplicate detection, malformed pages
	Extraction
	schema validity, missing fields, language handling
	Scoring
	known inputs → expected scores
	Narratives
	similar stories cluster; unrelated stories separate
	Sentiment
	benchmark examples
	Brand fit
	known Antier-relevant vs irrelevant examples
	QA
	unsupported claim → reject/research
	Dashboard
	approval/rejection state transitions
	Git/CI
	lint, unit tests, integration tests
	35. Key Success Metrics
Metric
	Target direction
	Relevant opportunities per run
	Increase quality, not raw volume
	Human approval rate
	Increase
	False-positive rate
	Decrease
	Unsupported-claim rate
	Near zero
	Duplicate-topic rate
	Decrease
	Novelty/whitespace quality
	Increase
	Time saved per editorial cycle
	Increase
	Published-topic performance
	Increase
	Business-qualified content opportunities
	Increase
	36. Example Final Recommendation
EVENTS
Visa + Stripe + banks + stablecoin settlement announcements

       ↓

NARRATIVE
Stablecoins are moving toward mainstream payment infrastructure

       ↓

SENTIMENT
Institutional: high positive
Enterprise: positive
Developer: mixed
Regulatory: mixed

       ↓

ANTIER FIT
Stablecoin rails: very high
Payments: high
Enterprise infrastructure: very high

       ↓

WHITESPACE
Issuance coverage: crowded
Infrastructure/orchestration coverage: lower

       ↓

RECOMMENDED CONTENT

CEO:
"The stablecoin race is moving beyond issuance."

CTO:
"The difficult part of stablecoin payments is no longer
moving tokens. It is connecting the infrastructure around them."

CORPORATE:
"What enterprise stablecoin payment infrastructure
actually needs to solve."

       ↓

AI QA
Evidence verified → APPROVE

       ↓

HUMAN QA
Select one

       ↓

RESEARCH DOSSIER
Evidence + thesis + Antier proof + counterarguments

       ↓

ARTICLE / LINKEDIN
37. Initial Antier Topic Taxonomy
Domain
	Subtopics
	RWA
	tokenization, funds, real estate, commodities, securities, compliance, secondary markets
	Stablecoins
	rails, remittance, payments, settlement, issuance, treasury, regulation
	Institutional DeFi
	lending, liquidity, custody, compliance, settlement
	Blockchain infrastructure
	L1/L2, rollups, protocol engineering, interoperability, chain abstraction
	Wallets
	MPC, custody, account abstraction, enterprise wallets, programmable wallets
	AI + blockchain
	AI agents, autonomous commerce, agent identity, agent payments, AI operations
	Digital money
	digital banking, payments, cross-border settlement, tokenized money
	Security
	smart contracts, audits, monitoring, custody security, governance
	Regulation
	MiCA, SEC, licensing, stablecoin rules, RWA compliance
	Enterprise adoption
	banks, asset managers, governments, fintechs, enterprise transformation
	38. Repository Documentation Set
docs/
├── PRD.md              # product requirements
├── ARCHITECTURE.md     # system architecture
├── DATA_MODEL.md       # database schema
├── SCORING.md          # all scoring formulas
├── SOURCE_POLICY.md    # source tiers and ingestion policy
├── QA_POLICY.md        # AI + human QA rules
├── PROMPTS.md          # prompt versioning guide
├── RUNBOOK.md          # operations and troubleshooting
└── CHANGELOG.md        # system changes
39. Recommended Phase Plan
Phase
	Deliverable
	Outcome
	0
	Git repo + documentation
	Single source of truth
	1
	Antier brand brain
	System understands company/personas
	2
	Excel ingestion
	Curated source universe online
	3
	Ingestion + DB
	Reliable content pipeline
	4
	Intelligence
	Structured market signals
	5
	Narratives
	Market themes instead of article lists
	6
	Scoring
	Antier-specific opportunity ranking
	7
	QA
	High-confidence editorial queue
	8
	Dashboard
	Human review workflow
	9
	Research dossiers
	Long-form content pipeline
	10
	Feedback loop
	Performance-informed intelligence
	11
	Competitors/social
	Broader market intelligence
	12
	Optimization
	Continuous quality improvement
	40. What Claude Code Should Build First
The first coding milestone should produce a working vertical slice, not hundreds of files.
Excel
 ↓
10 test sources
 ↓
Fetch 50–100 recent items
 ↓
Deduplicate
 ↓
Claude extraction
 ↓
Cluster into narratives
 ↓
Score for Antier
 ↓
Generate 10 opportunities
 ↓
AI QA
 ↓
JSON + simple dashboard
Once that works end-to-end, expand source coverage. This validates the architecture before investing in a large crawler or polished UI.
41. Definition of Done for MVP
* A new source can be added through configuration without changing application code.
* New content is fetched only when needed.
* Duplicate stories are removed.
* Every content item has structured intelligence.
* Similar stories become narratives.
* Each narrative receives trend and sentiment signals.
* Every narrative receives an Antier relevance score.
* Top opportunities include evidence, thesis, persona and format.
* AI QA can reject weak or unsupported opportunities.
* Human reviewers can approve/reject opportunities.
* Approved opportunities generate research dossiers.
* All code/configuration/prompts are version-controlled in Git.
* Secrets and raw operational data are not committed.
* CI runs tests before changes merge.
42. Final Product Vision
The mature system should behave less like a content generator and more like an editorial intelligence analyst.
Every morning:

"What changed in the market?"

       ↓

"Which changes are becoming narratives?"

       ↓

"Which narratives matter to institutions,
enterprises, founders and developers?"

       ↓

"Which ones align with Antier's real capabilities?"

       ↓

"Where is the market conversation crowded?"

       ↓

"Where is there an authority gap?"

       ↓

"What can Antier say that is genuinely useful?"

       ↓

"Who should say it?"

       ↓

"Is the evidence strong enough?"

       ↓

"Should our human QA team approve it?"

       ↓

"What research do we need to write the final piece?"

       ↓

"What did we learn from the published result?
43. Current Antier Positioning Reference
This blueprint is anchored to Antier's current public positioning. Antier's homepage describes purpose-built AI and blockchain infrastructure for institutions and enterprises and lists RWA tokenization, stablecoin rails, protocol engineering, enterprise AI, institutional DeFi and enterprise wallets among its infrastructure disciplines. citeturn0search0
Antier's current tokenization infrastructure material emphasizes institutional, regulated deployments and lifecycle infrastructure, while its broader tokenization offering covers multiple asset classes, investor onboarding, compliance, custody, liquidity and interoperability. citeturn0search1turn0search2
The About page positions Antier around blockchain trust plus AI intelligence and identifies Vikram R Singh as CEO & Founder. citeturn0search3
44. Immediate Next Steps
24. Create the remote Git repository: antier-content-intelligence.
25. Put the master blueprint and source registry under version control.
26. Create CLAUDE.md with the system constitution and coding rules.
27. Create the Antier brand/persona YAML files.
28. Import the Excel source list into config/sources/source_registry.csv.
29. Build the MVP vertical slice before expanding integrations.
30. Validate the first 10–20 recommended opportunities with the human QA team.
31. Adjust scoring weights based on editorial feedback.
32. Only then scale the source universe and add social/competitor intelligence.
END OF MASTER BLUEPRINT
Antier Content Intelligence Agent •