"""Import the source universe into config/sources/source_registry.csv.

Blueprint section 5: the Excel workbook becomes the source registry, imported into
Git as configuration -- not kept as an opaque local-only artifact. Section 44.28
names this as an immediate step.

Input is the live Google Sheet (shared read-only by link), so the registry can be
refreshed without anyone re-exporting a file by hand. Output is the section 5.1
column set, with authority scores from the section 5.2 tiers.

    python3 scripts/import_source_registry.py            # live sheet
    python3 scripts/import_source_registry.py --xlsx F    # a local workbook instead

Authority is assigned by explicit rule, never guessed. Anything unmatched gets the
documented default and is flagged needs_review in notes -- a silent assignment would
let a low-quality source inherit undeserved weight, which section 5.2 forbids.
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
import re
import sys
import tempfile
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.ingestion.office_reader import xlsx_to_text

SHEET_ID = os.environ.get(
    "DISCOVERY_SHEET_ID", "15gkGfWOWQvvYmHN2rCHskeyvgp6neB1p8pIRn9bD3Fg"
)
EXPORT = "https://docs.google.com/spreadsheets/d/%s/export?format=xlsx" % SHEET_ID

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONF = os.path.join(REPO, "config", "sources")
OUT = os.path.join(CONF, "source_registry.csv")
# Curated sources that are not in the sheet, and sources to deactivate. The registry
# is generated, so hand-editing it would be wiped on the next import -- these two
# files are the durable place for an editorial decision (section 41.1).
ADDITIONS = os.path.join(CONF, "additional_sources.csv")
PRUNE = os.path.join(CONF, "prune_list.csv")

COLUMNS = [
    "source_id", "source_name", "url", "source_type", "category",
    "authority_score", "crawl_frequency", "region", "topics", "personas",
    "active", "last_seen_at", "notes",
]

# --- Authority tiers (section 5.2) -----------------------------------------------
# Keyed on a substring of the entity name or its domain. Order matters: first match
# wins, so the most authoritative classes are listed first.
TIERS = [
    # 10 -- regulators, official bodies, primary company/protocol announcements
    (10, "regulator", [
        "imf.org", "worldbank", "bis.org", "fsb.org", "fatf", "treasury.gov",
        "newyorkfed", "richmondfed", "esma.europa",
    ]),
    (10, "primary_company", [
        "circle.com", "tether.to", "paxos.com", "stripe.com", "visa.com",
        "mastercard.com", "dtcc.com", "swift.com", "euroclear.com",
        "clearstream.com", "lseg.com", "digitalasset.com",
    ]),
    # 9 -- major financial institutions, established protocols, primary research
    (9, "institution", [
        "jpmorgan", "citi.com", "blackrock", "franklintempleton", "dbresearch",
        "statestreet",
    ]),
    # Convening and standards bodies: institutional weight, but not regulators.
    # Keeping them out of tier 10 is the section 5.2 rule against inflating authority.
    (9, "standards_body", ["weforum", "tacoalition"]),
    (9, "protocol", [
        "securitize.io", "ondo.finance", "superstate", "centrifuge.io",
        "chain.link", "fireblocks", "anchorage", "bitgo", "mento.org",
    ]),
    # 8 -- established research firms and high-quality specialist media
    (8, "research_firm", [
        "mckinsey", "bcg.com", "bain.com", "deloitte", "pwc.com", "kpmg",
        "ey.com", "kearney", "accenture", "simon-kucher", "celent.com",
        "edgardunn", "flagshipadvisory", "fxcintel", "brookings", "dci.mit.edu",
        "cfainstitute", "spglobal", "gartner", "forrester", "cbinsights",
        "emergenresearch", "nielseniq", "kantar", "redseer", "paulhastings",
        "cadwalader",
    ]),
    (8, "data_platform", [
        "artemis.ai", "allium.so", "dune.com", "defillama", "visaonchainanalytics",
        "21shares", "falconx", "messari", "blockworksresearch", "delphidigital",
        "getorbital",
    ]),
    # 7 -- industry publications and specialist blogs
    (7, "specialist", [
        "4pillars", "teroxx", "assettokenization", "tacoalition",
        "tokenizedeconomies", "blockchainresearchlab", "frontiersin", "aei.org",
        "ssrn.com", "f6s.com", "beincrypto",
    ]),
]
DEFAULT_TIER = 5          # section 5.2: community / secondary commentary
DEFAULT_TYPE = "unclassified"

# Sources measured unreachable (SOURCE_POLICY.md). Carried into notes so a run does
# not mistake a bot-block for an empty feed.
BLOCKED = {
    "dune.com": "HTTP 403 as of 2026-10-06",
    "defillama.com": "HTTP 403 as of 2026-10-06",
    "ssrn.com": "HTTP 403 as of 2026-10-06",
    "research.4pillars.io": "HTTP 429 as of 2026-10-06",
}
GATED = ["celent.com", "fxcintel", "gartner", "forrester", "spglobal",
         "cbinsights", "emergenresearch", "nielseniq", "kantar"]

# Crawl frequency by tier. Regulators and primary sources move slowly but matter
# most when they move; data platforms change continuously.
FREQUENCY = {10: "daily", 9: "daily", 8: "weekly", 7: "weekly", 5: "weekly"}

JUNK_URL = re.compile(r"^https?://(s\.no|no)/?$", re.I)


def classify(name, url):
    hay = ("%s %s" % (name, url)).lower()
    for score, stype, needles in TIERS:
        for needle in needles:
            if needle in hay:
                return score, stype
    return DEFAULT_TIER, DEFAULT_TYPE


def normalise_url(raw):
    raw = (raw or "").strip()
    if not raw:
        return ""
    if raw.startswith("http"):
        return raw
    # The Generic tab carries bare domains. Make them fetchable.
    return "https://" + raw.lstrip("/")


def parse_sheet(text):
    """Yield (sheet_name, row_cells) for every data row of every tab."""
    sheet = None
    header_seen = False
    for line in text.splitlines():
        if line.startswith("===== SHEET:"):
            sheet = line.replace("===== SHEET:", "").replace("=====", "").strip()
            header_seen = False
            continue
        if not line.strip() or sheet is None:
            continue
        cells = [c.strip() for c in line.split("|")]
        if not header_seen:
            header_seen = True          # first non-empty row of a tab is its header
            continue
        yield sheet, cells


def build_rows(text):
    rows, seen = [], set()
    for sheet, cells in parse_sheet(text):
        if sheet == "Generic":
            name = cells[0] if cells else ""
            url = normalise_url(cells[1] if len(cells) > 1 else "")
            focus = cells[2] if len(cells) > 2 else ""
            price = cells[3] if len(cells) > 3 else ""
            category, notes_extra = "generic", price
        elif sheet == "Specific Websites":
            name = cells[0] if cells else ""
            url = normalise_url(cells[1] if len(cells) > 1 else "")
            focus, category, notes_extra = "", "specific_website", ""
        else:
            continue                     # People / LinkedIn tabs are empty
        # Strip the hyperlink annotation office_reader adds: "Text <https://...>"
        name = re.sub(r"\s*<https?://[^>]+>$", "", name).strip()
        if not url or JUNK_URL.match(url):
            continue
        key = url.rstrip("/").lower()
        if key in seen:
            continue
        seen.add(key)

        score, stype = classify(name, url)
        notes = []
        if stype == DEFAULT_TYPE:
            notes.append("needs_review: authority defaulted to %d" % DEFAULT_TIER)
        for dom, why in BLOCKED.items():
            if dom in url.lower():
                notes.append("BLOCKED %s" % why)
        if any(g in url.lower() for g in GATED):
            notes.append("GATED")
        if notes_extra:
            notes.append(notes_extra)

        rows.append({
            "source_id": "",            # assigned after sorting, for stable ids
            "source_name": name or key,
            "url": url,
            "source_type": stype,
            "category": category,
            "authority_score": score,
            "crawl_frequency": FREQUENCY.get(score, "weekly"),
            "region": "global",
            "topics": focus,
            "personas": "",             # left blank: assigning personas per source
                                        # is an editorial call, not a mechanical one
            "active": "true",
            "last_seen_at": "",
            "notes": "; ".join(notes),
        })

    rows.sort(key=lambda r: (-int(r["authority_score"]), r["source_name"].lower()))
    for i, row in enumerate(rows, 1):
        row["source_id"] = "src-%03d" % i
    return rows


def load_additions():
    """Curated sources filling service gaps the sheet does not cover."""
    if not os.path.exists(ADDITIONS):
        return []
    with open(ADDITIONS) as fh:
        return list(csv.DictReader(fh))


def load_prune():
    """(url_fragment, reason) pairs for sources to mark inactive."""
    if not os.path.exists(PRUNE):
        return []
    with open(PRUNE) as fh:
        return [(r["url_contains"].strip().lower(), r["reason"])
                for r in csv.DictReader(fh) if r.get("url_contains", "").strip()]


def apply_additions(rows, additions):
    """Append curated sources, skipping any URL the sheet already provides."""
    have = {r["url"].rstrip("/").lower() for r in rows}
    for add in additions:
        url = normalise_url(add["url"])
        if url.rstrip("/").lower() in have:
            continue
        score = int(add.get("authority_score") or DEFAULT_TIER)
        rows.append({
            "source_id": "",
            "source_name": add["source_name"],
            "url": url,
            "source_type": add.get("source_type") or DEFAULT_TYPE,
            "category": add.get("category") or "curated",
            "authority_score": score,
            "crawl_frequency": add.get("crawl_frequency") or FREQUENCY.get(score, "weekly"),
            "region": add.get("region") or "global",
            "topics": add.get("topics") or "",
            "personas": add.get("personas") or "",
            "active": add.get("active") or "true",
            "last_seen_at": "",
            "notes": add.get("notes") or "curated addition",
        })
        have.add(url.rstrip("/").lower())
    return rows


def apply_prune(rows, prune):
    """Deactivate rather than delete: the reason stays auditable in the registry."""
    pruned = 0
    for row in rows:
        low = row["url"].lower()
        for fragment, reason in prune:
            if fragment in low:
                row["active"] = "false"
                row["notes"] = (row["notes"] + "; " if row["notes"] else "") + \
                    "PRUNED: " + reason
                pruned += 1
                break
    return pruned


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--xlsx", help="local workbook instead of the live sheet")
    args = ap.parse_args()

    if args.xlsx:
        path, cleanup = args.xlsx, False
    else:
        fd, path = tempfile.mkstemp(suffix=".xlsx")
        os.close(fd)
        cleanup = True
        try:
            req = urllib.request.Request(EXPORT, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=120) as resp:
                data = resp.read()
            with open(path, "wb") as fh:
                fh.write(data)
        except Exception as exc:
            print("Could not fetch the sheet: %s" % exc, file=sys.stderr)
            return 1

    rows = build_rows(xlsx_to_text(path))
    if cleanup:
        os.unlink(path)

    additions = load_additions()
    rows = apply_additions(rows, additions)
    pruned = apply_prune(rows, load_prune())

    # Re-sort and re-id after merging so ids stay stable by authority then name.
    rows.sort(key=lambda r: (-int(r["authority_score"]), r["source_name"].lower()))
    for i, row in enumerate(rows, 1):
        row["source_id"] = "src-%03d" % i

    if not rows:
        print("No sources parsed — refusing to write an empty registry.", file=sys.stderr)
        return 1

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)

    by_tier = {}
    for row in rows:
        by_tier.setdefault(int(row["authority_score"]), []).append(row)
    print("wrote %d sources -> config/sources/source_registry.csv" % len(rows))
    for tier in sorted(by_tier, reverse=True):
        print("  tier %2d: %3d" % (tier, len(by_tier[tier])))
    flagged = [r for r in rows if "needs_review" in r["notes"]]
    blocked = [r for r in rows if "BLOCKED" in r["notes"]]
    inactive = [r for r in rows if r["active"] != "true"]
    print("  needs_review: %d   blocked: %d" % (len(flagged), len(blocked)))
    print("  curated additions: %d   pruned (deactivated): %d"
          % (len(additions), pruned))
    print("  active: %d of %d" % (len(rows) - len(inactive), len(rows)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
