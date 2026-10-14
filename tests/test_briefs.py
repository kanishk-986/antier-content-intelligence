"""The daily brief: routing, windowing and the mail path."""

import os
import sys
from dataclasses import dataclass, field

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.brand import load_personas, persona_names
from src.briefs import daily, mailer
from src.briefs.persona import assign, load_recipients

NOW_ISO = "2026-10-13T12:00:00+00:00"
from datetime import datetime, timedelta, timezone

NOW = datetime(2026, 10, 13, 12, 0, tzinfo=timezone.utc)
PERSONA_CONFIGS = load_personas()


@dataclass
class FakeOpportunity:
    id: str = "o1"
    narrative_id: str = "n1"
    narrative_name: str = "stablecoin regulation and market structure"
    score_0_10: float = 7.5
    band: str = "good"
    unmeasured: list = field(default_factory=list)


class FakeStore:
    def __init__(self, items, reviews=None):
        self._items = items
        self._reviews = reviews or []

    def narrative_items(self, narrative_id):
        return self._items

    def qa_reviews(self):
        return self._reviews


def item(hours_ago, title="Visa expands settlement", source="Visa"):
    when = NOW - timedelta(hours=hours_ago)
    return {"id": f"i{hours_ago}", "source_id": "s1", "source_name": source,
            "title": title, "clean_text": "body text " * 30,
            "url": "https://x/a", "published_at": when.isoformat()}


# --- routing ------------------------------------------------------------------

def test_the_qa_recommendation_wins():
    """Section 20 makes the reviewer's judgement the stronger signal; a keyword
    match must not override a human-reviewable one."""
    got = assign(FakeOpportunity(), [item(1)], PERSONA_CONFIGS, qa_persona="cto")
    assert got.persona == "cto" and got.from_qa


def test_an_unknown_qa_persona_falls_through_to_matching():
    got = assign(FakeOpportunity(), [item(1)], PERSONA_CONFIGS, qa_persona="cfo")
    assert not got.from_qa


def test_territory_matching_picks_the_ceo_for_market_structure():
    o = FakeOpportunity(narrative_name="market structure and regulation shift")
    assert assign(o, [], PERSONA_CONFIGS).persona == "ceo"


def test_territory_matching_picks_the_cto_for_architecture():
    o = FakeOpportunity(narrative_name="wallet architecture and interoperability")
    assert assign(o, [], PERSONA_CONFIGS).persona == "cto"


def test_no_match_goes_to_the_general_channel_with_a_reason():
    o = FakeOpportunity(narrative_name="zzzz qqqq")
    got = assign(o, [], PERSONA_CONFIGS)
    assert got.persona == "company"
    assert "no territory matched" in got.reason


def test_an_unmatched_opportunity_is_never_dropped():
    """A silent drop makes the brief read as "nothing happened in your territory"."""
    o = FakeOpportunity(narrative_name="zzzz qqqq")
    store = FakeStore([item(2)])
    brief = daily.build(store, [o], now=NOW)
    assert brief.total == 1


# --- the window ---------------------------------------------------------------

def test_only_narratives_with_something_in_the_window_appear():
    store = FakeStore([item(100)])
    assert daily.build(store, [FakeOpportunity()], window_hours=24,
                       now=NOW).total == 0


def test_one_fresh_item_brings_its_narrative_in():
    store = FakeStore([item(100), item(2)])
    assert daily.build(store, [FakeOpportunity()], window_hours=24,
                       now=NOW).total == 1


def test_a_forthcoming_item_does_not_bring_a_narrative_in():
    """Same rule as momentum and the sitemap: a date that has not arrived is not
    yesterday's news."""
    store = FakeStore([item(-24 * 300)])
    assert daily.build(store, [FakeOpportunity()], now=NOW).total == 0


def test_an_undated_item_cannot_prove_freshness():
    bare = {**item(2), "published_at": None}
    assert daily.build(FakeStore([bare]), [FakeOpportunity()], now=NOW).total == 0


def test_sections_are_capped():
    store = FakeStore([item(1)])
    many = [FakeOpportunity(id=f"o{i}", score_0_10=float(i)) for i in range(12)]
    brief = daily.build(store, many, now=NOW, max_per_persona=3)
    assert all(len(v) <= 3 for v in brief.sections.values())


def test_the_highest_scoring_survive_the_cap():
    store = FakeStore([item(1)])
    many = [FakeOpportunity(id=f"o{i}", score_0_10=float(i)) for i in range(6)]
    brief = daily.build(store, many, now=NOW, max_per_persona=2)
    shown = [e.opportunity.score_0_10 for v in brief.sections.values() for e in v]
    assert 5.0 in shown and 0.0 not in shown


# --- rendering ----------------------------------------------------------------

def _render(opportunities, items, reviews=None):
    brief = daily.build(FakeStore(items, reviews), opportunities, now=NOW)
    return daily.render_markdown(brief, load_recipients())


def test_every_persona_section_appears_even_when_empty():
    """An empty section reads as "we looked"; a missing one reads as "we didn't"."""
    out = _render([], [item(1)])
    for persona in persona_names():
        label = PERSONA_CONFIGS[persona].get("label") or persona
        assert f"## {label}" in out
    assert "Searched, not skipped" in out


def test_the_configured_names_appear():
    out = _render([], [item(1)])
    assert "Vikram R Singh" in out and "Shashi Pal" in out


def test_the_coo_section_exists():
    """An owner extension beyond section 4's four personas. It has to reach the
    brief, and the QA validator has to accept it as a recommendation."""
    from src.agents.qa import PERSONAS as QA_PERSONAS
    assert "coo" in persona_names()
    assert "coo" in QA_PERSONAS, (
        "the QA schema rejected a persona the brief can route; the list used to be "
        "hardcoded in three places")
    assert "COO" in _render([], [item(1)])


def test_an_operations_narrative_routes_to_the_coo():
    o = FakeOpportunity(narrative_name="operational scale and delivery cost")
    assert assign(o, [], PERSONA_CONFIGS).persona == "coo"


def test_the_prompt_lists_exactly_the_configured_personas():
    """The prompt is a static file, so it drifts from config silently. A model told
    the wrong enum returns a value the validator then rejects."""
    from src.agents import qa as qa_module
    system, _ = qa_module.load_prompt()
    for persona in persona_names():
        assert f"`{persona}`" in system, f"{persona} missing from the QA prompt"


def test_a_rejected_item_is_shown_with_its_objection():
    """The objection is usually the most useful line in the brief."""
    review = {"opportunity_id": "o1", "ai_decision": "REJECT",
              "problems": '["Q1: all three sources are the vendor\'s own newsroom"]',
              "recommended_persona": "ceo"}
    out = _render([FakeOpportunity()], [item(1)], [review])
    assert "REJECT" in out
    assert "vendor's own newsroom" in out
    assert "hold." in out, "a rejected item must not read as a recommendation"


def test_an_unreviewed_item_says_so():
    out = _render([FakeOpportunity()], [item(1)])
    assert "not yet QA reviewed" in out


def test_malformed_problems_json_does_not_break_the_brief():
    review = {"opportunity_id": "o1", "ai_decision": "REJECT",
              "problems": "not json at all"}
    out = _render([FakeOpportunity()], [item(1)], [review])
    assert "not json at all" in out


def test_unmeasured_dimensions_are_disclosed():
    o = FakeOpportunity(unmeasured=["commercial_relevance"])
    assert "Unmeasured: commercial_relevance" in _render([o], [item(1)])


def test_the_evidence_names_publishers_with_counts():
    items = [item(1, source="Paxos"), item(2, source="Paxos"), item(3, source="ESMA")]
    out = _render([FakeOpportunity()], items)
    assert "2x Paxos" in out and "1x ESMA" in out


# --- mail ---------------------------------------------------------------------

ENV = {"SMTP_HOST": "smtp.gmail.com", "SMTP_PORT": "587",
       "SMTP_USER": "a@b.test", "SMTP_PASSWORD": "secret-pw"}


def test_missing_smtp_settings_name_themselves():
    with pytest.raises(RuntimeError) as exc:
        mailer.config_from_env({"SMTP_HOST": "x"})
    for key in ("SMTP_PORT", "SMTP_USER", "SMTP_PASSWORD"):
        assert key in str(exc.value)


def test_the_error_does_not_suggest_putting_a_password_on_the_command_line():
    with pytest.raises(RuntimeError) as exc:
        mailer.config_from_env({})
    assert "Never pass a password on the command line" in str(exc.value)


def test_a_send_failure_never_echoes_the_password():
    """smtplib puts the server response in the exception, and a failed AUTH can
    echo part of what was sent."""
    def boom(message, settings):
        raise RuntimeError(f"535 auth failed for {settings['SMTP_PASSWORD']}")
    result = mailer.send("s", "# b", ["x@y.test"], env=ENV, transport=boom)
    assert not result.sent
    assert "secret-pw" not in result.detail
    assert "***" in result.detail


def test_nothing_is_sent_without_a_recipient():
    result = mailer.send("s", "# b", ["", None], env=ENV,
                         transport=lambda m, s: None)
    assert not result.sent and "no valid recipient" in result.detail


def test_a_successful_send_reports_its_recipients():
    captured = {}
    result = mailer.send("subj", "# body", ["x@y.test"], env=ENV,
                         transport=lambda m, s: captured.update(msg=m))
    assert result.sent
    assert captured["msg"]["Subject"] == "subj"
    assert captured["msg"]["To"] == "x@y.test"


def test_the_mail_carries_both_plain_text_and_html():
    captured = {}
    mailer.send("s", "# Brief\n- one", ["x@y.test"], env=ENV,
                transport=lambda m, s: captured.update(msg=m))
    types = {p.get_content_type() for p in captured["msg"].walk()}
    assert {"text/plain", "text/html"} <= types


def test_a_fetched_title_cannot_inject_markup():
    """Titles come from pages we did not write."""
    out = mailer.markdown_to_html("- [<script>alert(1)</script>](https://x/a)")
    assert "<script>" not in out and "&lt;script&gt;" in out


def test_links_and_headings_survive_rendering():
    out = mailer.markdown_to_html("## CEO\n- [Title](https://x/a)\n**bold**")
    assert "<h2>CEO</h2>" in out
    assert '<a href="https://x/a">Title</a>' in out
    assert "<strong>bold</strong>" in out
    assert out.count("<ul>") == out.count("</ul>") == 1


def test_a_recipient_name_matching_the_label_is_not_repeated():
    """The corporate channel's recipient name is the label, which read as
    "Antier Corporate — Antier Corporate"."""
    out = _render([], [item(1)])
    assert "Antier Corporate — Antier Corporate" not in out
    assert "## Antier Corporate" in out


def test_the_html_brief_stands_alone():
    """A Workspace account with app passwords disabled by policy cannot use SMTP at
    all. The brief must be readable without mail ever working."""
    out = mailer.markdown_to_html("# Brief\n## COO — Shashi Pal\n- [T](https://x/a)")
    assert out.startswith("<!doctype html>")
    assert "<meta charset='utf-8'>" in out
    assert "Shashi Pal" in out


# --- the From header on a relay ------------------------------------------------

def test_the_relay_login_is_not_used_as_the_from_address():
    """Brevo issues a login like 9a1b2c@smtp-brevo.com and SMTP2GO a username.
    Sending the brief from that address means nobody recognises the sender and
    replies go nowhere."""
    env = {"SMTP_USER": "9a1b2c@smtp-brevo.com",
           "MAIL_FROM": "kanishk.raj@antiersolutions.com"}
    assert mailer.sender_address(env) == "kanishk.raj@antiersolutions.com"


def test_smtp_user_is_the_fallback_when_it_is_an_address():
    env = {"SMTP_USER": "kanishk.raj@antiersolutions.com"}
    assert mailer.sender_address(env) == "kanishk.raj@antiersolutions.com"


def test_a_login_that_is_not_an_address_is_not_silently_used():
    """A username like "antier-prod" would make an invalid From header; the caller
    must be told to set MAIL_FROM rather than have a broken message sent."""
    assert mailer.sender_address({"SMTP_USER": "antier-prod"}) == "antier-prod"


def test_the_from_header_reaches_the_message():
    captured = {}
    mailer.send("s", "# b", ["x@y.test"],
                env={**ENV, "SMTP_USER": "9a1b@smtp-brevo.com",
                     "MAIL_FROM": "kanishk.raj@antiersolutions.com"},
                transport=lambda m, s: captured.update(msg=m))
    assert captured["msg"]["From"] == "kanishk.raj@antiersolutions.com"


# --- running under the wrong interpreter --------------------------------------

def test_every_script_re_execs_into_the_venv():
    """macOS ships Python 3.9, which cannot parse `str | None` at runtime and has
    none of this project's dependencies. `python3 scripts/x.py` is the obvious thing
    to type and it crashed with a TypeError that says nothing about the cause."""
    import glob
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    scripts = glob.glob(os.path.join(root, "scripts", "*.py"))
    assert scripts, "no scripts found; the glob is wrong"
    missing = []
    for path in scripts:
        with open(path) as fh:
            if "_VENV" not in fh.read():
                missing.append(os.path.basename(path))
    assert not missing, f"these would crash under system python: {missing}"


def test_the_bootstrap_runs_before_any_annotation_is_evaluated():
    """It has to come before the first `def`, or the TypeError fires first."""
    import glob
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for path in glob.glob(os.path.join(root, "scripts", "*.py")):
        with open(path) as fh:
            body = fh.read()
        venv_at = body.index("_VENV")
        first_def = body.find("\ndef ")
        if first_def != -1:
            assert venv_at < first_def, (
                f"{os.path.basename(path)}: the venv bootstrap must precede the "
                "first def")


# --- a territory can have more than one owner ---------------------------------

@pytest.mark.parametrize("value,expected", [
    ("Nishant", "Nishant"),
    (["Rohit", "Mohit"], "Rohit and Mohit"),
    (["A", "B", "C"], "A, B and C"),
    (["Solo"], "Solo"),
    ([], ""),
    (None, ""),
    (["", "  "], ""),
])
def test_a_persona_can_be_owned_by_several_people(value, expected):
    """Expertise is not always one person: the SME territory has two."""
    assert daily._names(value) == expected


def test_both_sme_owners_appear_in_the_brief():
    out = _render([], [item(1)])
    assert "Rohit and Mohit" in out
    assert "Nishant" in out


# --- the cycle's own preconditions --------------------------------------------

import importlib.util as _ilu

_rd_spec = _ilu.spec_from_file_location(
    "run_daily", os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "scripts", "run_daily.py"))
run_daily = _ilu.module_from_spec(_rd_spec)
_rd_spec.loader.exec_module(run_daily)


def test_an_unreachable_network_is_detected():
    """A run that starts while the Mac is asleep has no DNS, and every source fails
    with "nodename nor servname". A real overnight run recorded 54 of 105 sources
    as `error` — which is not a fact about those publishers, and pollutes the health
    report that decides where work is worth doing."""
    assert run_daily.network_is_up(("no-such-host-xyz.invalid",)) is False


def test_a_resolvable_host_counts_as_up():
    assert run_daily.network_is_up(("localhost",)) is True


def test_one_bad_probe_host_does_not_report_the_network_down():
    assert run_daily.network_is_up(("no-such-host-xyz.invalid", "localhost")) is True


def test_only_one_cycle_runs_at_a_time(tmp_path):
    """launchd starts the job on schedule regardless of what is already running.
    Two cycles sharing one SQLite file would interleave a re-clustering with a
    scoring pass."""
    lock = str(tmp_path / "daily.lock")
    with run_daily.single_instance(lock), pytest.raises(RuntimeError, match="already running"):
        with run_daily.single_instance(lock):
            pass


def test_the_lock_is_released_when_the_cycle_ends(tmp_path):
    lock = str(tmp_path / "daily.lock")
    with run_daily.single_instance(lock):
        pass
    with run_daily.single_instance(lock):
        pass          # must not raise


def test_the_lock_is_released_even_after_a_crash(tmp_path):
    """flock is held by the file descriptor, so a crashed cycle cannot wedge the
    schedule permanently."""
    lock = str(tmp_path / "daily.lock")
    with pytest.raises(ValueError), run_daily.single_instance(lock):
        raise ValueError("stage blew up")
    with run_daily.single_instance(lock):
        pass
