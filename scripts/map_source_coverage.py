"""Map every registry source onto the core services and ICPs, and find the gaps.

Answers the question the registry alone cannot: for each of the eight charter
services, do we have sources that actually cover it, at what authority, and which
ICPs are left unserved?

Signal matching runs over a source's name, URL and strategic-focus text from the
sheet. A source matching no service is reported `unmapped` rather than quietly
dropped -- an unmapped source is either miscategorised or not a source for this
business, and both need a human.

    python3 scripts/map_source_coverage.py                 # coverage matrix
    python3 scripts/map_source_coverage.py --md FILE       # write a markdown report
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
import csv
import os
import sys

import yaml

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REGISTRY = os.path.join(REPO, "config", "sources", "source_registry.csv")
SERVICES = os.path.join(REPO, "config", "brand", "services.yaml")


def load():
    with open(SERVICES) as fh:
        services = yaml.safe_load(fh)["services"]
    with open(REGISTRY) as fh:
        sources = list(csv.DictReader(fh))
    return services, sources


def map_source(row, services):
    """Service ranks a source plausibly covers, by signal match."""
    hay = " ".join([row["source_name"], row["url"], row.get("topics") or ""]).lower()
    hits = []
    for rank, svc in services.items():
        matched = [s for s in svc["signals"] if s in hay]
        if matched:
            hits.append((rank, matched))
    return hits


def reachability(row):
    if (row.get("active") or "true").lower() != "true":
        return "pruned"
    notes = (row.get("notes") or "").upper()
    if "BLOCKED" in notes:
        return "blocked"
    if "GATED" in notes:
        return "gated"
    return "open"


def build(services, sources):
    coverage = {rank: [] for rank in services}
    unmapped = []
    for row in sources:
        hits = map_source(row, services)
        if not hits:
            unmapped.append(row)
            continue
        for rank, matched in hits:
            coverage[rank].append((row, matched))
    return coverage, unmapped


def report(services, coverage, unmapped, total):
    lines = []
    add = lines.append
    add("| # | Service | Sources | Open | Tier 9-10 | Verdict |")
    add("|---|---|---:|---:|---:|---|")
    for rank in sorted(services):
        rows = coverage[rank]
        openish = [r for r, _ in rows if reachability(r) == "open"]
        high = [r for r in openish if int(r["authority_score"]) >= 9]
        if not openish:
            verdict = "**NO REACHABLE SOURCE**"
        elif not high and len(openish) < 3:
            verdict = "**thin** — no primary source"
        elif not high:
            verdict = "secondary only"
        elif len(high) >= 3:
            verdict = "well covered"
        else:
            verdict = "adequate"
        add("| %d | %s | %d | %d | %d | %s |" % (
            rank, services[rank]["name"], len(rows), len(openish), len(high), verdict))
    add("")
    add("Unmapped sources: **%d of %d** (%.0f%%) — matched no service signal."
        % (len(unmapped), total, 100 * len(unmapped) / total))
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--md", help="write a markdown report to this path")
    ap.add_argument("--show-unmapped", action="store_true")
    args = ap.parse_args()

    services, sources = load()
    coverage, unmapped = build(services, sources)
    text = report(services, coverage, unmapped, len(sources))
    print(text)

    if args.show_unmapped:
        print("\nUnmapped:")
        for row in sorted(unmapped, key=lambda r: -int(r["authority_score"])):
            print("  t%-2s %-34s %s" % (row["authority_score"],
                                        row["source_name"][:34], row["url"][:46]))

    if args.md:
        with open(args.md, "w") as fh:
            fh.write(text + "\n")
        print("\nwrote %s" % args.md)
    return 0


if __name__ == "__main__":
    sys.exit(main())
