"""Find the listing path for a source the pipeline reports as no_feed.

Blueprint 41.1: a new source must be addable through configuration, not code. That
only holds if finding the right configuration is a repeatable operation rather than
hand-probing a site. This probes candidate paths concurrently and prints an
`overrides:` block ready for `config/sources/listing_rules.yaml`.

It judges a path by the same `candidate_links()` the extractor uses, so a path that
scores here is a path the pipeline can actually read -- not merely one that exists.

    python3 scripts/probe_listing.py --status no_feed error   # everything fixable
    python3 scripts/probe_listing.py --name "World Bank" "KPMG"
    python3 scripts/probe_listing.py --status no_feed --independent-only
"""

import argparse
import concurrent.futures as cf
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import httpx

from src.database.sqlite_store import SqliteStore
from src.ingestion.listing import candidate_links, load_rules
from src.ingestion.pipeline import load_registry
from src.narratives.momentum import load_independence

# Beyond the extractor's own default_paths: the shapes large institutions and the
# consultancies actually use. Cheap to try, and a wrong guess just 404s.
EXTRA_PATHS = [
    "/about/press-releases", "/news-and-events", "/newsroom/press-releases",
    "/newsroom/news", "/news/press-releases", "/about-us/newsroom",
    "/en/insights", "/en/news", "/en/newsroom", "/en-us/insights",
    "/us/en/insights", "/insights/blog", "/our-insights", "/featured-insights",
    "/perspectives", "/publications", "/thought-leadership", "/reports",
    "/newsroom/all-news", "/institutional/insights", "/investment-ideas",
]

# A listing page with fewer than this many readable links is not worth a rule; the
# extractor's own floor applies afterwards anyway.
MIN_LINKS = 3
TIMEOUT = 8.0
WORKERS = 12
UA = "Mozilla/5.0 (compatible; AntierContentIntelligence/1.0; +research)"


def probe_one(client: httpx.Client, base: str, path: str,
              reject: list[str]) -> tuple[int, str, str]:
    url = base.rstrip("/") + path
    try:
        resp = client.get(url)
    except httpx.HTTPError as exc:
        return (0, path, f"error: {type(exc).__name__}")
    if resp.status_code >= 400:
        return (0, path, f"HTTP {resp.status_code}")
    links = candidate_links(resp.text, str(resp.url), reject)
    return (len(links), path, f"HTTP {resp.status_code}, {len(links)} link(s)")


def probe_source(source: dict, paths: list[str], reject: list[str]) -> list[tuple]:
    with httpx.Client(timeout=TIMEOUT, follow_redirects=True,
                      headers={"User-Agent": UA}) as client, \
            cf.ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futures = [pool.submit(probe_one, client, source["url"], p, reject)
                   for p in paths]
        results = [f.result() for f in futures]
    return sorted((r for r in results if r[0] >= MIN_LINKS), reverse=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="data/aci.db")
    ap.add_argument("--status", nargs="*", default=["no_feed", "error"],
                    help="fetch-log statuses to target")
    ap.add_argument("--name", nargs="*", help="probe these sources by name instead")
    ap.add_argument("--independent-only", action="store_true",
                    help="skip primary parties; only they change corpus independence")
    ap.add_argument("--top", type=int, default=3, help="paths to report per source")
    args = ap.parse_args()

    rules = load_rules()
    reject = rules.get("reject_patterns", [])
    paths = list(dict.fromkeys(rules.get("default_paths", []) + EXTRA_PATHS))
    registry = {s["name"]: s for s in load_registry()}

    if args.name:
        targets = [registry[n] for n in args.name if n in registry]
        missing = [n for n in args.name if n not in registry]
        for n in missing:
            print(f"  ?? not in registry: {n}", file=sys.stderr)
    else:
        party = load_independence()["primary_party_types"]
        health = SqliteStore(args.db).source_health()
        if not health:
            print("No fetch log. Run scripts/run_ingestion.py first.", file=sys.stderr)
            return 1
        targets = []
        for row in health:
            if row["status"] not in args.status:
                continue
            if args.independent_only and row["source_type"] in party:
                continue
            src = registry.get(row["source_name"])
            if src:
                targets.append(src)

    if not targets:
        print("Nothing to probe.")
        return 0

    print(f"probing {len(targets)} source(s) x {len(paths)} path(s), "
          f"{WORKERS} at a time\n")
    found: dict[str, list[tuple]] = {}
    for src in targets:
        hits = probe_source(src, paths, reject)
        found[src["name"]] = hits[: args.top]
        label = src["name"][:38]
        if hits:
            print(f"  {label:40} " + "  ".join(f"{p}({n})" for n, p, _ in hits[:args.top]))
        else:
            print(f"  {label:40} nothing readable at any candidate path")

    usable = {k: v for k, v in found.items() if v}
    print(f"\n  {len(usable)} of {len(targets)} source(s) have a readable listing path")

    if usable:
        print("\n# paste into config/sources/listing_rules.yaml under `overrides:`")
        for name, hits in usable.items():
            host = registry[name]["url"].split("//")[-1].split("/")[0]
            host = host[4:] if host.startswith("www.") else host
            chosen = ", ".join(p for _, p, _ in hits)
            print(f"  {host}:\n    listing_paths: [{chosen}]    # {name}")

    dead = [k for k, v in found.items() if not v]
    if dead:
        print("\n  # no readable listing; needs a headless browser or a prune:")
        for name in dead:
            print(f"  #   {name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
