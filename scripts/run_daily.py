"""The daily cycle (section 28), end to end, then the brief by email.

    python3 scripts/run_daily.py                 # full cycle, send the brief
    python3 scripts/run_daily.py --dry-run       # write the brief, send nothing
    python3 scripts/run_daily.py --brief-only    # skip the pipeline, rebuild the brief
    python3 scripts/run_daily.py --hours 48      # a wider window after a missed day

Stages run in order and a failure stops the chain, because every later stage reads
what the earlier one wrote: scoring a stale clustering would produce a brief that
looks current and is not. The exception is intelligence extraction, which is rate
limited rather than free -- a partial pass is useful and does not invalidate what
came before, so a non-zero exit there is reported and the cycle continues.

Section 20 holds: this sends a reading document. Nothing is published.
"""

# macOS ships Python 3.9, which cannot parse `str | None` at runtime and has none
# of this project's dependencies. Re-exec into the project venv so `python3
# scripts/x.py` works regardless of which interpreter the shell found first.
import os as _os
import sys as _sys

_VENV = _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))),
                      ".venv", "bin", "python")
if _os.path.exists(_VENV) and _os.path.realpath(_sys.executable) != _os.path.realpath(_VENV):
    _os.execv(_VENV, [_VENV, _os.path.abspath(__file__), *_sys.argv[1:]])

import argparse
import os
import subprocess
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.briefs import daily, mailer
from src.briefs.envfile import environment
from src.briefs.persona import load_recipients
from src.database.sqlite_store import SqliteStore
from src.scoring import weights as wcfg
from src.scoring.opportunity import persist, score_all

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PYTHON = os.path.join(REPO, ".venv", "bin", "python")
OUTPUTS = os.path.join(REPO, "outputs")


def stage(name: str, args: list[str], required: bool, log) -> bool:
    log(f"\n=== {name} ===")
    proc = subprocess.run([PYTHON if os.path.exists(PYTHON) else sys.executable,
                           os.path.join(REPO, "scripts", args[0]), *args[1:]],
                          capture_output=True, text=True, cwd=REPO)
    tail = (proc.stdout or "").strip().splitlines()[-6:]
    for line in tail:
        log("  " + line)
    if proc.returncode != 0:
        err = (proc.stderr or "").strip().splitlines()[-4:]
        for line in err:
            log("  ! " + line)
        log(f"  {name} exited {proc.returncode}"
            + ("" if required else " — continuing, this stage is resumable"))
        return not required
    return True


def run(args, log) -> int:
    """One cycle. `log` writes to both the console and the day's log file."""
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    if not args.brief_only:
        chain = [
            ("ingestion", ["run_ingestion.py"], True),
            ("intelligence", ["run_intelligence.py", "--limit",
                              str(args.intelligence_limit)], False),
            ("narratives", ["run_narratives.py"], True),
            ("scoring", ["run_scoring.py"], True),
            ("qa", ["run_qa.py", "--top", str(args.top)], False),
        ]
        for name, cmd, required in chain:
            if not stage(name, cmd, required, log):
                log(f"\nstopped: {name} failed and later stages read its output.")
                return 1

    log("\n=== brief ===")
    recipients = load_recipients()
    window = args.hours or int(recipients.get("window_hours") or 24)

    store = SqliteStore(args.db)
    config = wcfg.load()
    scored = score_all(store, config)
    persist(store, [o for o, _ in scored])
    brief = daily.build(store, [o for o, _ in scored], window_hours=window)
    markdown = daily.render_markdown(brief, recipients)

    md_path = os.path.join(OUTPUTS, f"brief-{day}.md")
    with open(md_path, "w") as fh:
        fh.write(markdown)

    # Also as HTML, because the brief has to be readable whether or not mail is
    # working. A Workspace account with app passwords disabled by policy cannot use
    # SMTP at all, and the brief should not be held hostage to that.
    html_path = os.path.join(OUTPUTS, f"brief-{day}.html")
    with open(html_path, "w") as fh:
        fh.write(mailer.markdown_to_html(markdown))
    log(f"  {brief.total} item(s) across {len(brief.sections)} persona section(s)")
    for persona, entries in brief.sections.items():
        log(f"    {persona:8} {len(entries)}")
    log(f"  wrote {md_path}")
    log(f"  wrote {html_path}")
    if args.open:
        subprocess.run(["open", html_path], check=False)

    to = [(recipients.get('digest') or {}).get('email') or ""]
    subject = (f"Antier daily brief — {day} — {brief.total} item(s) in the last "
               f"{window}h")

    if args.no_send:
        log("  --no-send: the brief is on disk and was not mailed.")
        return 0

    if args.dry_run:
        log("  --dry-run: not sent. "
            f"Would have gone to {', '.join(a for a in to if a) or '(nobody)'}")
        return 0

    result = mailer.send(subject, markdown, to, env=environment())
    log(f"  {'sent' if result.sent else 'NOT SENT'}: {result.detail}")
    store.audit("system", "daily_brief",
                detail=f"{brief.total} item(s), sent={result.sent}")
    return 0 if result.sent else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="data/aci.db")
    ap.add_argument("--hours", type=int, help="brief window; default from config")
    ap.add_argument("--dry-run", action="store_true", help="write, do not send")
    ap.add_argument("--open", action="store_true",
                    help="open the brief in the browser when it is written")
    ap.add_argument("--no-send", action="store_true",
                    help="write the brief and skip mail entirely (no credentials "
                         "needed); the scheduled run still produces the file")
    ap.add_argument("--brief-only", action="store_true", help="skip the pipeline")
    ap.add_argument("--intelligence-limit", type=int, default=40)
    ap.add_argument("--top", type=int, default=8, help="opportunities to QA")
    args = ap.parse_args()

    os.makedirs(OUTPUTS, exist_ok=True)
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    # Appended, not truncated: a scheduled run that fails at 10:00 and is retried
    # by hand at 10:20 must not erase the evidence from the first attempt.
    with open(os.path.join(OUTPUTS, f"daily-{day}.log"), "a") as log_file:
        def log(message: str = "") -> None:
            print(message, flush=True)
            log_file.write(message + "\n")
            log_file.flush()

        log(f"daily cycle {datetime.now(timezone.utc).isoformat(timespec='seconds')}")
        return run(args, log)


if __name__ == "__main__":
    raise SystemExit(main())
