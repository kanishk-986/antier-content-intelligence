"""The daily brief: yesterday's intelligence, routed per persona (sections 4, 28).

Structure, and why:

  * **Per persona, not one ranked list.** Section 4 gives each persona a distinct
    territory and section 18 a distinct angle. A single list makes every reader
    scan all of it to find their own two items.
  * **Every section appears, including empty ones.** An empty section reads as "we
    looked and found nothing in your territory", which is information. A section
    that vanishes when empty reads as "nothing was looked for".
  * **The QA verdict travels with the item.** Section 20 makes human review final,
    so the brief carries the reviewer's objection rather than hiding it behind a
    score. An item QA rejected is shown as rejected, not omitted -- the reason is
    often the most useful line in the brief.
  * **Nothing is published from here.** This is a reading document.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from src.brand import load_personas, persona_names
from src.briefs.persona import assign, load_recipients

# More than this in one section and it stops being a brief.
MAX_PER_PERSONA = 5
LEDE_CHARS = 320


@dataclass
class BriefItem:
    opportunity: Any
    items: list[dict[str, Any]]
    review: dict[str, Any] | None
    reason: str
    from_qa: bool

    @property
    def decision(self) -> str:
        return (self.review or {}).get("ai_decision") or "UNREVIEWED"


@dataclass
class Brief:
    generated_at: str
    window_hours: int
    sections: dict[str, list[BriefItem]] = field(default_factory=dict)
    corpus: dict[str, Any] = field(default_factory=dict)

    @property
    def total(self) -> int:
        return sum(len(v) for v in self.sections.values())


def _parse(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        when = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None
    return when if when.tzinfo else when.replace(tzinfo=timezone.utc)


def _in_window(items: list[dict[str, Any]], since: datetime,
               until: datetime) -> bool:
    """Did anything in this narrative publish inside the window?

    `until` excludes a forthcoming item, on the same rule momentum uses: a date that
    has not arrived is not yesterday's news.
    """
    for item in items:
        when = _parse(item.get("published_at"))
        if when and since <= when <= until:
            return True
    return False


def _reviews_by_opportunity(store) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for row in store.qa_reviews():
        out.setdefault(row["opportunity_id"], row)
    return out


def build(store, opportunities, window_hours: int = 24,
          now: datetime | None = None,
          max_per_persona: int = MAX_PER_PERSONA) -> Brief:
    now = now or datetime.now(timezone.utc)
    since = now - timedelta(hours=window_hours)
    horizon = now + timedelta(hours=24)

    personas = load_personas()
    reviews = _reviews_by_opportunity(store)
    brief = Brief(generated_at=now.isoformat(timespec="seconds"),
                  window_hours=window_hours,
                  sections={p: [] for p in persona_names()})

    considered = fresh = 0
    for opportunity in opportunities:
        considered += 1
        items = store.narrative_items(opportunity.narrative_id)
        if not _in_window(items, since, horizon):
            continue
        fresh += 1
        review = reviews.get(opportunity.id)
        placed = assign(opportunity, items, personas,
                        (review or {}).get("recommended_persona"))
        brief.sections.setdefault(placed.persona, []).append(
            BriefItem(opportunity, items, review, placed.reason, placed.from_qa))

    for persona, entries in brief.sections.items():
        entries.sort(key=lambda e: e.opportunity.score_0_10, reverse=True)
        brief.sections[persona] = entries[:max_per_persona]

    brief.corpus = {"opportunities": considered, "in_window": fresh,
                    "shown": brief.total, "window_hours": window_hours}
    return brief


# --- rendering ----------------------------------------------------------------

def _lede(item: dict[str, Any]) -> str:
    text = " ".join((item.get("clean_text") or "").split())
    return text[:LEDE_CHARS] + ("..." if len(text) > LEDE_CHARS else "")


def _problems(review: dict[str, Any] | None) -> list[str]:
    if not review:
        return []
    raw = review.get("problems")
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        return [str(raw)]
    return [str(p) for p in parsed] if isinstance(parsed, list) else [str(parsed)]


def render_markdown(brief: Brief, recipients: dict[str, Any] | None = None) -> str:
    recipients = recipients if recipients is not None else load_recipients()
    people = recipients.get("personas") or {}
    personas = load_personas()
    day = brief.generated_at[:10]

    out = [f"# Antier daily intelligence brief — {day}", ""]
    out.append(f"Window: the last {brief.window_hours} hours. "
               f"{brief.corpus['in_window']} of {brief.corpus['opportunities']} "
               f"scored opportunities published in it; {brief.total} shown.")
    out.append("")
    out.append("Human review is final (section 20). Nothing here has been published,"
               " and a rejected item is shown with its objection rather than removed"
               " — the objection is usually the most useful line.")
    out.append("")

    for persona in persona_names():
        config = personas.get(persona, {})
        who = people.get(persona) or {}
        label = config.get("label") or persona
        name = who.get("name") or ""
        # The corporate channel's recipient name is the label, so it would read
        # "Antier Corporate — Antier Corporate".
        show_name = name and name.strip().lower() != str(label).strip().lower()
        heading = f"## {label}" + (f" — {name}" if show_name else "")
        out.append(heading)
        territory = ", ".join(config.get("territory") or [])
        if territory:
            out.append(f"*Territory: {territory}*")
        angle = config.get("angle")
        if angle:
            out.append(f"*Angle: {angle}*")
        out.append("")

        entries = brief.sections.get(persona) or []
        if not entries:
            out.append("Nothing in this territory published in the window. "
                       "Searched, not skipped.")
            out.append("")
            continue

        for entry in entries:
            o = entry.opportunity
            out.append(f"### {o.narrative_name}")
            out.append(f"**{o.score_0_10}/10** ({o.band}) · QA: **{entry.decision}**"
                       f" · routed by {'QA' if entry.from_qa else entry.reason}")
            if o.unmeasured:
                out.append(f"*Unmeasured: {', '.join(o.unmeasured)} — capped below "
                           "`good` until measured.*")
            out.append("")

            publishers: dict[str, int] = {}
            for item in entry.items:
                key = item.get("source_name") or item.get("source_id") or "unknown"
                publishers[key] = publishers.get(key, 0) + 1
            out.append("**Evidence**: " + ", ".join(
                f"{n}x {name}" for name, n in
                sorted(publishers.items(), key=lambda kv: -kv[1])))
            out.append("")

            for item in entry.items[:3]:
                when = (item.get("published_at") or "undated")[:10]
                out.append(f"- [{item.get('title') or '(untitled)'}]"
                           f"({item.get('url')}) — {when}")
                lede = _lede(item)
                if lede:
                    out.append(f"  {lede}")
            out.append("")

            problems = _problems(entry.review)
            if problems:
                out.append("**What the QA reviewer objected to**")
                for problem in problems[:4]:
                    out.append(f"- {problem}")
                out.append("")

            suggestion = _suggest(entry, config)
            out.append(f"**Suggested angle** — {suggestion}")
            out.append("")

    out.append("---")
    out.append(f"Generated {brief.generated_at} · "
               "antier-content-intelligence · scoring weights v1")
    return "\n".join(out)


def _suggest(entry: BriefItem, persona_config: dict[str, Any]) -> str:
    """The section 18 framing for this persona, and the honest caveat.

    The framing matrix is the owner's, so it is quoted rather than invented. When a
    narrative has no matrix entry, the persona's general angle is used and labelled
    as such instead of a specific claim being made up.
    """
    decision = entry.decision
    framing = persona_config.get("framing") or {}
    name = (entry.opportunity.narrative_name or "").lower()
    for key, value in framing.items():
        if any(part in name for part in key.replace("_", " ").split()):
            base = value
            break
    else:
        base = persona_config.get("angle") or "general commentary"

    if decision == "REJECT":
        return (f"hold. {base}, but the reviewer rejected the evidence — see the "
                "objection above before using this.")
    if decision == "RESEARCH_MORE":
        return f"{base} — needs a second source before it can carry a claim."
    if decision == "UNREVIEWED":
        return f"{base} — not yet QA reviewed."
    return f"{base}."
