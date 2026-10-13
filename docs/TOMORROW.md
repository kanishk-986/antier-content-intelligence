# Checking the first unattended run

The 10:00 cycle has never run on its own. Everything below has been verified by
hand; what has *not* been tested is launchd firing it with no one watching.

## What should happen at 10:00

Ingestion → intelligence → clustering → scoring → QA → brief → mail. Roughly
25–40 minutes, so the mail lands around 10:30–10:45.

## Check it in this order

```bash
cd ~/antier-content-intelligence

# 1. Did it fire at all?
grep "daily cycle" outputs/daily-$(date +%F).log

# 2. Did every stage finish?
grep -E "^=== |hit its .*-minute limit|stopped:" outputs/daily-$(date +%F).log

# 3. Was the mail sent?
tail -3 outputs/daily-$(date +%F).log

# 4. Nothing at all in the log?
cat outputs/launchd.err.log
```

## What "good" looks like

- `sent: sent to kanishk.raj@antiersolutions.com` at the end of the log
- The brief in the inbox with five sections, every one present even if empty
- Some items carrying a real QA verdict rather than `UNREVIEWED`

## Known rough edges, so they are not mistaken for faults

- **`intelligence` may stop at its 25-minute limit.** The subscription rate limits
  rather than charges, and a pass that normally runs at ~20s an item has been
  measured at 25 minutes an item under limiting. The stage is resumable and the
  cycle continues; the brief still goes out.
- **Some items will say `UNREVIEWED`.** QA reviews the top 8 per run.
- **`cto` and `sme` sections may be empty.** Their territories are narrow and the
  window is 24 hours. Empty is reported, never hidden — that is the design.
- **Articles dated 2027** exist in the corpus. Publishers list forthcoming work.
  They are excluded from every recency calculation but still visible in the data.

## If no mail arrives

1. Was the Mac shut down at 10:00? launchd runs a missed job on wake, but a
   powered-off machine runs nothing.
2. `python3 scripts/test_mail.py` — proves delivery independently of the pipeline.
3. `launchctl kickstart -p gui/$(id -u)/com.antier.content-intelligence.daily`
   runs the whole cycle immediately.

## Worth deciding after reading the first brief

- Is the per-persona routing putting the right items in front of the right person?
  `cto` and `sme` territories are still my drafts; `coo` was corrected from Shashi
  Pal's own profile and is the one to trust most.
- Is 5 items per section the right volume, or too many?
- Should QA cover more than the top 8? It costs run time, not money.
