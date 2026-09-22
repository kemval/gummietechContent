"""
watch.py — the run that speaks for runs that never happened.

Two properties matter more than any single case. It must not cry wolf: the
free tier delivers a daily cron hours late, so every question it asks is
about an obligation that has already come due. And it must not nag: a
finding nobody can act on, repeated every day, is how a person learns to
stop reading the bot — which is the same failure the notify-failure throttle
and the self-held fact-check were both post-mortems of.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

import telegram as tg
import watch
from proof import Report


@pytest.fixture
def posts(monkeypatch, posts_dir):
    """An empty posts/ that both watch.py and telegram.py read."""
    directory, write = posts_dir
    monkeypatch.setattr(watch, "POSTS_DIR", directory)
    monkeypatch.setattr(tg, "POSTS_DIR", directory)
    return directory, write


def tap(stem: str) -> dict:
    """A publish tap, as getUpdates returns it — with no timestamp of its own."""
    return {"callback_query": {"data": f"{tg.CALLBACK_PREFIX}{stem}",
                               "id": "1", "message": {"message_id": 9}}}


def findings(report: Report, where: str) -> list[str]:
    return [text for level, text in report.lines
            if level != "note" and text.startswith(f"{where} · ")]


# -------------------------------------------------------------- the cadence

@pytest.mark.parametrize("today,expected", [
    ("2026-09-21", "2026-09-18"),   # Monday  looks back to Friday
    ("2026-09-22", "2026-09-21"),   # Tuesday to Monday
    ("2026-09-23", "2026-09-21"),   # Wednesday morning: Monday, not today
    ("2026-09-24", "2026-09-23"),   # Thursday to Wednesday
    ("2026-09-20", "2026-09-18"),   # Sunday   to Friday
])
def test_the_last_drop_day_is_one_that_already_ended(today, expected):
    """Never today. A 12:17 cron has been delivered as late as 18:12, so
    asking whether today's Drop exists yet would report a pipeline that is
    merely running behind as one that is broken."""
    assert watch.last_drop_day(today).isoformat() == expected


def test_a_drop_day_that_produced_nothing_is_a_block(posts):
    directory, _ = posts
    report = Report("WATCH")
    watch.check_cadence("2026-09-22", report, directory)
    assert report.verdict == "BLOCK"
    assert "2026-09-21" in report.render()


def test_a_drop_day_that_was_drafted_is_not_a_finding(posts):
    directory, write = posts
    write("2026-09-21-something.json", colorway="signal")
    report = Report("WATCH")
    watch.check_cadence("2026-09-22", report, directory)
    assert report.verdict == "PASS"


def test_the_filenames_date_is_what_answers_it(posts):
    """The same question daily.yml's gate job asks, by the same means: a post
    published on Monday but drafted Sunday is Sunday's file."""
    directory, write = posts
    write("2026-09-20-drafted-the-day-before.json",
          colorway="signal", published_at="2026-09-21")
    report = Report("WATCH")
    watch.check_cadence("2026-09-22", report, directory)
    assert report.verdict == "BLOCK"


# ----------------------------------------------------------------- the gate

def test_an_unhonoured_tap_is_a_finding(posts):
    _, write = posts
    write("2026-09-21-tapped.json", colorway="signal")
    report = Report("WATCH")
    watch.check_gate([tap("2026-09-21-tapped")], report)
    assert findings(report, "gate")


def test_a_tap_that_was_honoured_is_not(posts):
    _, write = posts
    write("2026-09-21-tapped.json", colorway="signal",
          published_at="2026-09-21")
    report = Report("WATCH")
    watch.check_gate([tap("2026-09-21-tapped")], report)
    assert report.verdict == "PASS"


def test_a_replayed_tap_is_reported_once(posts):
    """getUpdates has no offset, so the same tap comes back on every poll for
    24 hours — and more than once in a single reply when it was tapped twice."""
    _, write = posts
    write("2026-09-21-tapped.json", colorway="signal")
    report = Report("WATCH")
    watch.check_gate([tap("2026-09-21-tapped")] * 3, report)
    assert len(findings(report, "gate")) == 1


def test_a_tap_naming_no_post_is_ignored(posts):
    """The stem arrives from the network. confirm() distrusts it; so does this."""
    report = Report("WATCH")
    watch.check_gate([tap("../../etc/passwd"), tap("nothing-here")], report)
    assert report.verdict == "PASS"


# -------------------------------------------------------------- the metrics

def answer(stem: str, text: str = "12 3 4") -> dict:
    return {"message": {"text": text,
                        "reply_to_message":
                            {"text": f"📊 {tg.METRICS_MARK} {stem}"}}}


def test_an_answer_that_was_never_written_down_is_a_finding(posts):
    _, write = posts
    write("2026-09-14-live.json", colorway="signal",
          published_at="2026-09-14", metrics={"asked_at": "2026-09-17"})
    report = Report("WATCH")
    watch.check_metrics([answer("2026-09-14-live")], "2026-09-18", report)
    assert findings(report, "metrics")


def test_an_answer_already_recorded_is_not(posts):
    directory, write = posts
    write("2026-09-14-live.json", colorway="signal",
          published_at="2026-09-14",
          metrics={"asked_at": "2026-09-17", "saves": 12, "shares": 3,
                   "profile_visits": 4, "recorded_at": "2026-09-17"})
    report = Report("WATCH")
    watch.check_metrics([answer("2026-09-14-live")], "2026-09-18", report,
                        directory)
    assert report.verdict == "PASS"


def test_a_chat_message_is_not_a_dropped_answer(posts):
    """record_metrics ignores a reply that is not three numbers, in silence.
    Reporting one as lost would be reporting on a conversation."""
    directory, write = posts
    write("2026-09-14-live.json", colorway="signal",
          published_at="2026-09-14", metrics={"asked_at": "2026-09-17"})
    report = Report("WATCH")
    watch.check_metrics([answer("2026-09-14-live", "nice one")], "2026-09-18",
                        report, directory)
    assert report.verdict == "PASS"


def numbers(text: str = "0 1 1") -> dict:
    """Three numbers typed into the chat rather than replied with."""
    return {"message": {"text": text, "chat": {"id": 1}, "message_id": 9}}


def test_three_numbers_replying_to_nothing_are_a_finding(posts):
    """The one failure record_metrics cannot report on itself: it has no idea
    which post they answer, and getUpdates has no offset, so a nudge from the
    poll would be re-sent every poll for a day. Nine were lost this way."""
    directory, write = posts
    write("2026-09-14-live.json", colorway="signal",
          published_at="2026-09-14", metrics={"asked_at": "2026-09-17"})
    report = Report("WATCH")
    watch.check_metrics([numbers()], "2026-09-18", report, directory)
    assert findings(report, "metrics")


def test_the_same_mistake_repeated_is_one_finding(posts):
    """Nine in a day is one habit, and nine lines is a message nobody reads."""
    directory, write = posts
    report = Report("WATCH")
    watch.check_metrics([numbers("0 1 1"), numbers("0 1 0"), numbers("0 1 3")],
                        "2026-09-18", report, directory)
    assert len(findings(report, "metrics")) == 1
    assert "3 message(s)" in report.render()


def test_talking_to_the_bot_is_not_a_dropped_answer(posts):
    """Only the shape of an answer counts. Anything else is a conversation."""
    directory, _ = posts
    report = Report("WATCH")
    watch.check_metrics([numbers("posted it"), {"callback_query": {"data": "x"}}],
                        "2026-09-18", report, directory)
    assert report.verdict == "PASS"


def test_an_ask_nobody_answered_is_a_finding_once_it_is_stale(posts):
    directory, write = posts
    write("2026-09-01-live.json", colorway="signal",
          published_at="2026-09-01", metrics={"asked_at": "2026-09-04"})
    fresh, stale = Report("WATCH"), Report("WATCH")
    watch.check_metrics([], "2026-09-08", fresh, directory)
    watch.check_metrics([], "2026-09-30", stale, directory)
    assert fresh.verdict == "PASS"
    assert findings(stale, "metrics")


# --------------------------------------------------------------- the colour

def test_two_neighbouring_posts_in_the_same_field_are_a_finding(posts):
    directory, write = posts
    write("2026-09-18-first.json", colorway="ember")
    write("2026-09-19-second.json", colorway="ember")
    report = Report("WATCH")
    watch.check_colour(report, directory)
    assert findings(report, "colour")


def test_the_finding_names_the_colorway_that_breaks_the_run(posts):
    """Whatever vary() would have chosen, so the advice and the code that
    would have prevented it cannot drift apart."""
    directory, write = posts
    write("2026-09-18-first.json", colorway="ember")
    write("2026-09-19-second.json", colorway="ember")
    report = Report("WATCH")
    watch.check_colour(report, directory)
    assert f"--colorway {watch.vary('ember', 'ember')}" in report.render()


def test_a_run_that_is_already_published_does_not_move_the_verdict(posts):
    """A post on the grid cannot be re-rendered. Reporting it as a finding
    would send the same unfixable message every day, which is exactly how a
    person learns to ignore the bot."""
    directory, write = posts
    write("2026-09-18-first.json", colorway="ember",
          published_at="2026-09-18")
    write("2026-09-19-second.json", colorway="ember",
          published_at="2026-09-19")
    report = Report("WATCH")
    watch.check_colour(report, directory)
    assert report.verdict == "PASS"
    assert "second ember post in a row" in report.render()


def test_a_field_that_is_free_is_not_a_finding(posts):
    directory, write = posts
    write("2026-09-18-first.json", colorway="ember")
    write("2026-09-19-second.json", colorway="orbit")
    report = Report("WATCH")
    watch.check_colour(report, directory)
    assert report.verdict == "PASS"


def test_a_colorway_outside_the_table_is_a_finding(posts):
    directory, write = posts
    write("2026-09-18-first.json", colorway="sunset")
    report = Report("WATCH")
    watch.check_colour(report, directory)
    assert findings(report, "colour")


def test_one_unrecognised_colorway_does_not_disable_the_rule(posts):
    """previous_colorway() steps over a post it cannot read rather than
    ending the walk. This walks the same way, or a single bad record hides
    every clash after it."""
    directory, write = posts
    write("2026-09-17-first.json", colorway="ember")
    write("2026-09-18-broken.json", colorway="sunset")
    write("2026-09-19-third.json", colorway="ember")
    report = Report("WATCH")
    watch.check_colour(report, directory)
    assert any("2026-09-19-third" in text for text in findings(report, "colour"))


def test_the_era_fixtures_are_not_posts(posts):
    """post_order()'s date-prefix filter, which resolve-post needs for the
    same reason: era*.json has no prefix and would sort after every draft."""
    directory, write = posts
    write("2026-09-18-first.json", colorway="ember")
    write("era.json", colorway="ember")
    report = Report("WATCH")
    watch.check_colour(report, directory)
    assert report.verdict == "PASS"


# --------------------------------------------------------------- the buffer

def test_a_deep_buffer_is_a_finding(posts):
    directory, write = posts
    for n in range(watch.MAX_BUFFER + 1):
        write(f"2026-09-2{n}-draft.json", colorway="signal")
    report = Report("WATCH")
    watch.check_buffer(report, directory)
    assert findings(report, "buffer")


def test_a_normal_buffer_is_only_a_note(posts):
    directory, write = posts
    write("2026-09-21-draft.json", colorway="signal")
    report = Report("WATCH")
    watch.check_buffer(report, directory)
    assert report.verdict == "PASS"


# ------------------------------------------------------- degrading, not dying

def test_a_sheet_that_cannot_be_opened_is_a_note_not_a_crash(monkeypatch):
    """open_sheet() exits with instructions when the credentials are missing.
    A watcher that dies on one unconfigured check reports nothing about the
    eight that are fine."""
    import ingest
    monkeypatch.setattr(ingest, "open_sheet",
                        lambda: (_ for _ in ()).throw(SystemExit("no creds")))
    report = Report("WATCH")
    watch.check_queue(report)
    assert report.verdict == "PASS"
    assert "not checked" in report.render()


def test_telegram_being_unreachable_is_a_note_not_a_crash(monkeypatch):
    monkeypatch.setattr(watch, "call",
                        lambda *a, **k: (_ for _ in ()).throw(
                            watch.TelegramError("getUpdates timed out")))
    report = Report("WATCH")
    assert watch.updates_from_telegram("token", report) == []
    assert report.verdict == "PASS"


def test_a_broken_check_run_is_a_block():
    report = Report("WATCH")
    watch.check_structure("failure", report)
    assert report.verdict == "BLOCK"


@pytest.mark.parametrize("result", ["success", "skipped", ""])
def test_a_check_run_that_did_not_break_says_nothing(result):
    report = Report("WATCH")
    watch.check_structure(result, report)
    assert report.verdict == "PASS"


def test_an_unconfigured_fact_check_is_a_finding(monkeypatch):
    """review.yml skips the fact-check with no token and writes a stand-in
    that deliberately does not hold the post. That is right, and invisible."""
    monkeypatch.setenv("HAS_CLAUDE", "false")
    report = Report("WATCH")
    watch.check_factcheck(report)
    assert findings(report, "fact-check")


@pytest.mark.parametrize("value", ["true", ""])
def test_a_configured_fact_check_says_nothing(monkeypatch, value):
    monkeypatch.setenv("HAS_CLAUDE", value)
    report = Report("WATCH")
    watch.check_factcheck(report)
    assert report.verdict == "PASS"


# ----------------------------------------------------------------- the feeds

def feed_sweep(monkeypatch, *results):
    """Stub the network half of check_feeds.

    `results` are (name, status, detail, age) as check_feed returns them.
    Patched on verify_feeds because check_feeds imports from it at call time,
    which is what keeps feedparser and yaml out of the other checks.
    """
    import verify_feeds as vf
    entries = [{"name": name, "url": f"https://{name}.example/feed"}
               for name, _, _, _ in results]
    replies = {name: (status, detail, age)
               for name, status, detail, age in results}
    monkeypatch.setattr(vf, "all_feeds",
                        lambda *a, **k: [(Path("feeds/x.yaml"), e)
                                         for e in entries])
    monkeypatch.setattr(vf, "check_feed",
                        lambda entry, **k: replies[entry["name"]])


def test_a_feed_that_stopped_publishing_is_a_finding(monkeypatch):
    """The SemiAnalysis case: 200, ten entries, and nothing since last year.

    Every check that existed passed it, because all of them asked whether
    entries came back. ingest.py would drop all ten on MAX_AGE_DAYS and take
    a row from it never.
    """
    feed_sweep(monkeypatch, ("SemiAnalysis", "ok", "10 entries", 371))
    report = Report("WATCH")
    watch.check_feeds(report)
    found = findings(report, "feeds")
    assert any("371 days" in line for line in found)
    assert report.verdict == "FIX"


def test_a_slow_feed_is_not_stale(monkeypatch):
    """Practical Engineering publishes every other week. A watcher that calls
    that broken is one nobody reads — the whole reason the bar is 60 days and
    not ingest.py's MAX_AGE_DAYS of 7."""
    feed_sweep(monkeypatch,
               ("Practical Engineering", "ok", "20 entries", 7),
               ("Construction Physics", "ok", "20 entries", 3))
    report = Report("WATCH")
    watch.check_feeds(report)
    assert not findings(report, "feeds")
    assert report.verdict == "PASS"


def test_an_undated_feed_is_not_reported(monkeypatch):
    """Some feeds carry no dates at all. ingest.py keeps their entries on
    purpose, so there is no age to test and nothing to say."""
    feed_sweep(monkeypatch, ("Undated", "ok", "30 entries", None))
    report = Report("WATCH")
    watch.check_feeds(report)
    assert not findings(report, "feeds")
    assert report.verdict == "PASS"


def test_stale_feeds_are_capped_like_dead_ones(monkeypatch):
    """63 lines of dead feed is scrolled past, so the cap applies to both."""
    feed_sweep(monkeypatch, *[(f"Gone{i}", "ok", "5 entries", 400)
                              for i in range(watch.MAX_NAMED + 3)])
    report = Report("WATCH")
    watch.check_feeds(report)
    assert any("more stale" in line for line in findings(report, "feeds"))


# --------------------------------------------------------------- the silence

def test_notes_alone_do_not_send(posts):
    """A daily "all clear" is what teaches a person to mute the bot."""
    directory, write = posts
    write("2026-09-21-fine.json", colorway="signal", published_at="2026-09-21")
    report = Report("WATCH")
    watch.check_colour(report, directory)
    watch.check_buffer(report, directory)
    assert report.lines            # it has things to print locally
    assert report.verdict == "PASS"   # and nothing to say in the chat
