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
import contextlib
import fcntl
import os
import signal
import socket
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


# A stage that never returns is worse than one that fails: the cycle produces no
# brief at all and nothing says why. Measured: an intelligence pass managed 7 items
# in three hours once the subscription started rate limiting, with no upper bound.
STAGE_TIMEOUT_SECONDS = {
    "ingestion": 45 * 60,
    "intelligence": 25 * 60,
    "narratives": 15 * 60,
    "scoring": 10 * 60,
    "qa": 20 * 60,
}
DEFAULT_STAGE_TIMEOUT = 30 * 60


LOCK_PATH = os.path.join(OUTPUTS, ".daily.lock")
NETWORK_PROBE = ("bis.org", "www.circle.com")


def network_is_up(hosts=NETWORK_PROBE) -> bool:
    """Can we resolve anything at all?

    A run that starts while the Mac is asleep has no DNS, and every source fails
    with "nodename nor servname". Measured on a real overnight run: 54 of 105
    sources recorded as `error`, which is not a fact about those publishers and
    pollutes the health report that decides where work is worth doing.
    """
    for host in hosts:
        try:
            socket.getaddrinfo(host, 443)
            return True
        except OSError:
            continue
    return False


@contextlib.contextmanager
def single_instance(path: str = LOCK_PATH):
    """Only one cycle at a time.

    launchd starts the job on a calendar schedule regardless of what is already
    running. Two cycles sharing one SQLite file would interleave a re-clustering
    with a scoring pass. The lock is advisory and released even on a crash, because
    flock is held by the file descriptor rather than written into the file.
    """
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise RuntimeError(
                "another daily cycle is already running; this one will not start"
            ) from exc
        handle.write(f"{os.getpid()}\n")
        handle.flush()
        yield


def stage(name: str, args: list[str], required: bool, log) -> bool:
    log(f"\n=== {name} ===")
    limit = STAGE_TIMEOUT_SECONDS.get(name, DEFAULT_STAGE_TIMEOUT)
    # Its own session, so a timeout can signal the whole tree. A stage shells out
    # to the `claude` CLI, which spawns Node processes that inherit the pipes;
    # killing only the direct child leaves them holding the pipe open and the
    # timeout never surfaces. That is how a 20-minute stage ran for 65 minutes.
    proc = subprocess.Popen(
        [PYTHON if os.path.exists(PYTHON) else sys.executable,
         os.path.join(REPO, "scripts", args[0]), *args[1:]],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, cwd=REPO,
        start_new_session=True,
    )
    try:
        out, err = proc.communicate(timeout=limit)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            proc.kill()
        try:
            out, err = proc.communicate(timeout=10)
        except Exception:
            out, err = "", ""
        for line in (out or "").strip().splitlines()[-4:]:
            log("  " + line)
        log(f"  {name} hit its {limit // 60}-minute limit and was stopped"
            + ("" if required else " — continuing; this stage is resumable"))
        return not required

    for line in (out or "").strip().splitlines()[-6:]:
        log("  " + line)
    if proc.returncode != 0:
        for line in (err or "").strip().splitlines()[-4:]:
            log("  ! " + line)
        log(f"  {name} exited {proc.returncode}"
            + ("" if required else " — continuing, this stage is resumable"))
        return not required
    return True


def run(args, log) -> int:
    """One cycle. `log` writes to both the console and the day's log file."""
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    if not args.brief_only and not network_is_up():
        log("\n  no network: DNS does not resolve. Skipping the pipeline rather "
            "than recording every source as failed — a sleeping machine is not a "
            "fact about a publisher. The brief below uses what is already stored.")
        args.brief_only = True

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
        try:
            with single_instance():
                return run(args, log)
        except RuntimeError as exc:
            log(f"  {exc}")
            return 0


if __name__ == "__main__":
    raise SystemExit(main())
