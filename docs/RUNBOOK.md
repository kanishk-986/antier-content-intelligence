# RUNBOOK

## Prerequisites

| Requirement | Status on the build machine (2026-10-12) |
|---|---|
| Python 3.10+ | ✅ 3.12.13 via uv |
| Node 18+ | ✅ v24.19.0 |
| `gh` CLI | ⚠️ installed (2.97.0) but **not logged in** |
| Docker | ❌ not installed |
| PostgreSQL / pgvector | ❌ not installed — SQLite used for the vertical slice |
| `claude` CLI auth | ✅ authenticated against a Claude.ai subscription |
| `ANTHROPIC_API_KEY` | ❌ not set — **and not required**, see below |

## Quality gate

```bash
./scripts/install-hooks.sh     # once per clone: installs the pre-push gate
./scripts/check.sh             # lint + tests + secret scan, same as CI
```

**GitHub Actions is not running yet.** Pushing `.github/workflows/ci.yml` requires a
token with `workflow` scope; the credential on this machine has `repo` only, so the
workflow file is held on the local branch `pending/ci-workflow` and sits untracked in
the working tree. `scripts/check.sh` runs the identical three checks, and the pre-push
hook enforces them, so the gate is real in the meantime.

To land CI, either add `workflow` scope to the token at
<https://github.com/settings/tokens>, or run `gh auth login` (which also needs
`read:org` — the current token lacks it, so `gh` cannot authenticate with it). Then:

```bash
git add .github/workflows/ci.yml
git commit -m "Add CI: lint, tests, secret scan"
git push
```

## Running the LLM stages without API credits

The direct `anthropic` SDK bills metered API credits. The `claude` CLI authenticates
against a Claude.ai subscription, so routing the model stages through it uses the
existing plan instead. This is the **default** backend:

```bash
python3 scripts/run_intelligence.py --limit 20            # subscription (default)
python3 scripts/run_intelligence.py --limit 20 --backend api   # bills credits
python3 scripts/run_intelligence.py --dry-run             # no model call at all
```

Both paths implement the same `LLM` Protocol in `src/intelligence/extractor.py`, so
nothing downstream knows or cares which ran.

**What you give up, and what it costs you instead:**

| | CLI / subscription | API / credits |
|---|---|---|
| Billing | existing plan | metered |
| Strict schema | prompt-requested, validated after | `output_config.format`, enforced |
| Limits | subscription rate limits | credit balance |
| Speed | process spawn per item | faster |

The schema trade-off is safe only because `schema.validate` **rejects** rather than
clamps — a malformed record fails loudly and is recorded as a failure rather than
stored. Run with `--limit` and resume; a long run can be throttled.

## Setup

```bash
uv venv --python 3.12 .venv
VIRTUAL_ENV=.venv uv pip install -e ".[dev]"

cp .env.example .env     # fill in ANTHROPIC_API_KEY, then:
chmod 600 .env
```

The key goes in `.env` and nowhere else — never in a shell command, never committed.
Load it with `export $(grep -v '^#' .env | xargs)`; that keeps it out of shell history
and out of `ps`.

## Daily operating cycle (§28)

Example timings from the blueprint. **Implementation uses configurable schedules, not
hard-coded times** (§28).

| Time | Activity |
|---|---|
| 06:00 | Poll curated sources and APIs |
| 06:15 | Normalize and deduplicate |
| 06:30 | LLM intelligence extraction |
| 06:50 | Narrative clustering |
| 07:10 | Trend / sentiment calculation |
| 07:25 | Antier relevance and whitespace scoring |
| 07:40 | Persona / angle generation |
| 07:55 | AI QA |
| 08:10 | Dashboard ready for human review |

## Refreshing the source registry

```bash
python3 scripts/import_source_registry.py     # live sheet -> config/sources/source_registry.csv
```

Review the diff before committing — the registry is configuration, so a change to it
is a reviewable change to system behaviour.

## The daily brief at 10:00 (§28)

One command runs the whole cycle and mails the brief:

    python3 scripts/run_daily.py                 # full cycle, send
    python3 scripts/run_daily.py --dry-run       # write to outputs/, send nothing
    python3 scripts/run_daily.py --brief-only    # rebuild the brief, skip the pipeline
    python3 scripts/run_daily.py --hours 48      # wider window after a missed day

Stages run ingestion → intelligence → narratives → scoring → QA → brief. A failure
stops the chain, because each stage reads what the previous one wrote and scoring a
stale clustering would produce a brief that looks current and is not. Intelligence
extraction is the exception: it is rate limited rather than free, so a partial pass
is reported and the cycle continues.

### Setting up delivery

Google Workspace needs an **app password**, not the account password, once 2FA is
on. Create one at <https://myaccount.google.com/apppasswords>, then:

    cp .env.example .env
    # edit .env: SMTP_USER and SMTP_PASSWORD
    chmod 600 .env

Never pass the password on a command line — it lands in shell history and in `ps`.
`scripts/install-schedule.sh` sources `.env` inside a wrapper so it never reaches
the launchd plist, which is world-readable.

### Scheduling it

    ./scripts/install-schedule.sh               # 10:00 local, every day
    DAILY_HOUR=7 ./scripts/install-schedule.sh  # a different time
    ./scripts/install-schedule.sh --remove

**launchd, not cron.** cron drops a run entirely if the Mac was asleep at the time;
launchd runs a missed job once the machine wakes. For a daily brief that is the
difference between a late mail and no mail. The Mac must be awake or asleep — a
shut-down machine runs nothing, and §28 assumes a machine that is on.

    launchctl kickstart -p gui/$(id -u)/com.antier.content-intelligence.daily
    tail -f outputs/launchd.err.log

### Who gets what

`config/brand/recipients.yaml` maps each §4 persona to a person. A persona is an
editorial *territory*, not a job title: it decides the angle an item should be
written from, and routing sends each territory to whoever owns it so nobody reads
four sections to find their one.

| persona | territory | assigned |
|---|---|---|
| ceo | strategy, market structure, regulation, capital markets | Vikram R Singh |
| coo | operations, delivery, scale, partnerships, compliance ops | Shashi Pal |
| cto | architecture, security, protocols, interoperability | unassigned |
| sme | deep specialist themes | unassigned |
| company | enterprise use cases, solutions, case studies | Antier corporate |

`coo` is an **owner extension beyond §4**, which names four personas. Its territory
in `config/brand/coo.yaml` is a first draft and should be reviewed — a wrong
territory routes the wrong items there, which is worse than routing none.

**Adding a persona is a config change.** `src/brand.py` discovers them from
`config/brand/*.yaml` by their `persona:` field, so a new file is enough. The list
used to be hardcoded in three places — the QA schema, this router and the QA prompt
— which meant adding the COO would have had the QA validator reject a
recommendation the brief could route perfectly well. A test now asserts the prompt
lists exactly the configured personas, because a static prompt drifts silently.

An item is routed by the QA reviewer's `recommended_persona` where one exists —
§20 makes that the stronger signal — and otherwise by matching the narrative
against each persona's configured territory, which is arithmetic and so belongs in
Python (CLAUDE.md rule 7). An item matching nothing goes to `company` and says so;
it is never dropped, because a silent drop makes the brief read as "nothing
happened in your territory".

Every section appears every day, including empty ones. An empty section reads as
"we looked and found nothing"; a section that vanishes reads as "nothing was looked
for". A QA-rejected item is shown **with its objection** rather than removed — the
objection is usually the most useful line in the brief.

## Checking source health

    python3 scripts/source_health.py               # yield by type + independence share
    python3 scripts/source_health.py --actionable   # independent sources we can fix
    python3 scripts/source_health.py --run 2026-10-13T06:00:00+00:00

Run it after every ingestion. Two numbers matter more than the item count:

- **independent items as a share of the corpus.** Below 50%, the corpus is mostly
  vendor self-reporting and cannot support a claim however large it is.
- **independent sources with a fixable status.** These are the ones worth work; a
  `blocked` research firm is not a bug.

## Troubleshooting

**A source returns nothing.** Check `SOURCE_POLICY.md` → known-unreachable sources
first. Dune, DefiLlama, SSRN and research.4pillars are bot-blocked; that is expected
and must be reported as blocked, not as empty.

**Scores look inflated.** Check whether the competitor-saturation axis is reporting
`not yet measured` rather than zero (`SCORING.md`). A missing input must never read as
"no saturation".

**Velocity is infinite or undefined.** A narrative with a zero baseline. See the
`SCORING.md` edge case — the implementation must record which rule it applied.

**Git push fails with a credential error.** The predecessor repo used a
session-scoped credential file. Run `gh auth login` for a durable credential.

## Weekly intelligence report (§29)

Top rising narratives · emerging but not yet saturated · gaining institutional
traction · regulatory tension · topics competitors overuse · topics competitors ignore
· topics Antier should own · CEO opportunities · CTO opportunities · long-form
opportunities · previous-week performance.
