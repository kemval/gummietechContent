#!/usr/bin/env python3
"""
The thing that speaks for runs that never happened.

`notify-failure` speaks for a run that started and broke. Nothing speaks for
a run that was never created — a shed cron, a gate that skipped, a tap that
no poll ever picked up — because a run that does not exist has no runner to
speak from. That is what this is: a different run, on its own schedule,
looking backwards at state the pipeline left behind and saying what is
missing from it.

It measures rather than looks, for proof.py's reason. Every question below is
answerable from a file, a sheet cell or a Telegram update, so none of it
needs a model and none of it spends a quota.

Usage:
    python src/watch.py                  # print the report
    python src/watch.py --send           # ...and send it if it is not a PASS
    python src/watch.py --skip-feeds     # skip the slow network sweep

What it reports:

    cadence    the last drafting day that has ended has its post: a Drop on
               Mon/Wed/Fri, the Signal on Saturday
    glossary   from Wednesday on, this week has its term (or Cheat Sheet)
    breakdown  from Friday on, this week has a Breakdown
    subject    yesterday's Drop, or Signal items, were tech, not science
    gate       every tap in Telegram's 24h window reached published_at
    metrics    every answered ask was written down, and old asks were answered
    colour     no two neighbouring posts share a field
    buffer     the gate is not silently accumulating drafts
    feeds      every feed still returns entries, and still publishes, and a
               newsroom's `announces` prefixes still fit its links
    queue      rows are still arriving, and fresh candidates are scored
    lift       which of the last day's queued rows only relevance let in
    structure  check.yml, whose result the workflow hands over
    fact-check is configured at all

Three things it cannot do, which matter as much as what it can:

  - **It cannot prove it ran.** It is on the same scheduler that sheds, so
    its silence means "nothing to report" or "I did not run", and it has no
    way to tell you which. Making its absence visible costs a message a week;
    that trade is open, not made.
  - **Telegram does not timestamp a tap.** `callback_query` carries no date,
    so a tap made shortly before this runs is indistinguishable from one the
    poll lost. That is why an unrecorded tap is a FIX and says the poll may
    still be pending — a genuinely lost tap reports every day until it is
    fixed, which is the signal worth acting on.
  - **It does not measure how late a cron was.** The Actions API would give
    that, and it would change nothing: GitHub cannot be asked for less delay.
    So this asks for no `actions:` permission at all.

Exit status is 0 even when it finds things, because the message is the
report. Only an unexpected failure exits non-zero — and that is a broken run,
which `notify-failure` already speaks for. One problem, one message.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from formats import by_hand
from proof import Report
from render import COLORWAYS, post_order, vary
from telegram import (METRICS_ASK_RE, METRICS_CORE, METRICS_KEY,
                      POSTS_DIR, UPDATES_LIMIT,
                      TelegramError, config, locate, metrics_reply, ours,
                      parse_callback, poll, publish_date, read_post, recorded,
                      send_report)
from weekly import KINDS as WEEKLY

# What each drafting day owes. docs §1 fixes the Drop at 3×/week and the
# Signal at one; daily.yml asks on `* * 1,3,5,6` and drafts the Signal on the
# Saturday.
DRAFT_DAYS = {0: "Drop", 2: "Drop", 4: "Drop",   # Monday, Wednesday, Friday
              5: "Signal"}                        # Saturday


def owed_glob(day: date) -> str:
    """The filename that proves a drafting day did its work.

    The same test daily.yml's gate job makes, by the same means. A Drop is
    anything dated that day. A Signal is named for its ISO week by draft.py,
    and is looked for by that name anywhere in the week: one drafted by hand
    on the Sunday is still that week's Signal, as 2026-09-27's was.
    """
    if DRAFT_DAYS[day.weekday()] == "Signal":
        return f"{day.year}-*-signal-week-{day.isocalendar().week:02d}.json"
    return f"{day.isoformat()}-*.json"


def owes(day: date, post: dict) -> bool:
    """Is this post, matched by owed_glob(), the one that day owed?

    The date alone does not say. A Breakdown is written by hand and dated
    whatever day it was written, and on 2026-09-28 one dated that Monday
    made daily.yml's gate report the Drop as already drafted, so no Drop
    was. The Signal's name already says what it is; a Drop day is answered
    by anything a person did not write (formats.by_hand). daily.yml's gate
    asks the same.
    """
    if DRAFT_DAYS[day.weekday()] == "Signal":
        return True
    return not by_hand(post)


# Above this, drafts are piling up at the gate faster than they are tapped.
# Three is a comfortable buffer at 3 posts a week; four is a backlog.
MAX_BUFFER = 3

# An ask that has gone unanswered longer than this is not "settling", it is
# forgotten. learn.py counts it as unanswered either way; this says so.
METRICS_PATIENCE_DAYS = 7

# Candidates below this are under two weeks of Drops, which is less notice
# than finding and wiring a new feed takes.
QUEUE_FLOOR = 6

# ingest.yml runs every 2h. Nothing new in a day means it is succeeding and
# adding nothing — dead feeds, or a dedupe that now eats everything.
INGEST_SILENCE_HOURS = 24

# A chat message is read; 63 lines of dead feed are scrolled past. Name the
# first few and count the rest.
MAX_NAMED = 8


def last_draft_day(today: str) -> date:
    """The most recent drafting day that has already ended.

    It walks back from *yesterday*, never from today, and that is the whole
    reason this check cannot false-alarm: the free tier delivers a daily cron
    3–6 hours late, so asking whether today's Drop exists yet would report a
    pipeline that is merely running behind as a pipeline that is broken. A
    day that has ended owes its post unconditionally.
    """
    day = date.fromisoformat(today) - timedelta(days=1)
    while day.weekday() not in DRAFT_DAYS:
        day -= timedelta(days=1)
    return day


def check_cadence(today: str, report: Report,
                  directory: Path | None = None) -> None:
    """Did the last drafting day that ended produce its post?"""
    day = last_draft_day(today)
    directory = directory or POSTS_DIR
    if any(owes(day, read_post(path) or {})
           for path in directory.glob(owed_glob(day))):
        report.note("cadence", f"{day:%A} {day.isoformat()} was drafted")
        return
    what, how = (("the Signal day", "with signal=true")
                 if DRAFT_DAYS[day.weekday()] == "Signal"
                 else ("a Drop day", "with force=true"))
    report.block("cadence", f"{day:%A} {day.isoformat()} was {what} and "
                            f"posts/ has nothing for it. Check whether "
                            f"daily.yml ran at all; dispatch it {how} to "
                            f"draft now.")


def check_weekly(today: str, report: Report,
                 directory: Path | None = None) -> None:
    """Does this week have each carousel weekly.yml writes, once its day passed?

    docs §1 wants a glossary term on Tuesday and a Breakdown on Thursday, and
    neither is a Drop day's Drop, so check_cadence() cannot see them — the
    week of 2026-09-21 simply went without a Breakdown and nothing said so.
    Only the current week is asked about, and only from the day after each
    one's weekday: a week that already ended without one is history, and
    repeating it every day until the next Monday is the nagging this file
    exists to avoid. weekly.KINDS is the one table of which day is whose.
    """
    day = date.fromisoformat(today)
    monday = day - timedelta(days=day.weekday())
    week = []
    for path in post_order(directory or POSTS_DIR):
        try:
            drafted = date.fromisoformat(path.name[:10])
        except ValueError:
            continue
        if monday <= drafted <= day:
            week.append((path, (read_post(path) or {}).get("post_type")))
    for name, kind in WEEKLY.items():
        if day.weekday() <= kind.weekday:
            continue
        found = [path for path, post_type in week if post_type in kind.slot]
        if found:
            report.note(name, f"this week's is {found[0].stem}")
            continue
        due = monday + timedelta(days=kind.weekday)
        report.fix(name, f"no {' or '.join(kind.slot)} post this week (due "
                         f"{due:%A} {due}). weekly.yml did not write one — "
                         f"read its last run, or dispatch it with "
                         f"kind={name}.")


def check_subject(today: str, report: Report,
                  directory: Path | None = None) -> None:
    """Did yesterday's Drop, or any of its Signal's items, fall back to science?

    draft.pick_row takes science only when no queued row is on a priority
    subject, and says so in the run log. That is the moment the tech pool ran
    dry, and it is worth hearing about without reading the sheet. Only
    yesterday is asked about, so one fallback is one message, not one a day.
    A Drop or item with no beat came from no row — evergreen, --url, or a
    Signal drafted before beats were recorded — and is not judged.
    """
    from draft import PRIORITY_BEATS, PRIORITY_TOPICS   # imports the LLM clients

    def off(record: dict) -> str:
        beat = str(record.get("beat", "")).strip().lower()
        return "" if not beat or beat in PRIORITY_BEATS | PRIORITY_TOPICS else beat

    advice = ("The tech pool is dry — check the arXiv AI feeds are arriving, "
              "or draft the next one with --evergreen from the tech queue.")
    day = date.fromisoformat(today) - timedelta(days=1)
    for path in sorted((directory or POSTS_DIR).glob(f"{day.isoformat()}-*.json")):
        post = read_post(path) or {}
        kind = post.get("post_type", "drop")
        # A run post is that day's Drop with a code slide: same row pick.
        if kind in ("drop", "run") and (beat := off(post)):
            report.fix("subject", f"{path.stem} is a {beat} Drop: no queued "
                                  f"row was on AI, software, automation or "
                                  f"robotics. {advice}")
        elif kind == "signal":
            items = [i for i in post.get("items") or [] if isinstance(i, dict)]
            fell = [off(i) for i in items if off(i)]
            if fell:
                report.fix("subject", f"{path.stem} has {len(fell)} of "
                                      f"{len(items)} items off the priority "
                                      f"subjects ({', '.join(sorted(set(fell)))})."
                                      f" {advice}")


def check_gate(updates: list, report: Report) -> None:
    """Every tap in the window whose post still has no published_at."""
    seen: set[str] = set()
    for update in updates:
        data = str((update.get("callback_query") or {}).get("data", ""))
        parsed = parse_callback(data)
        if parsed is None:
            continue
        stem, prefix = parsed
        # locate() refuses a stem that names no file or tries to be a path,
        # and finds it whether it is a carousel in posts/ or a status report
        # in series/reports/ — a lost tap is a lost tap either way. The stem
        # arrives from the network; confirm() distrusts it and so does this.
        path = locate(stem)
        if path is None or stem in seen:
            continue
        post = read_post(path)
        # recorded(), not published_at: a reel tap lands on a post that has
        # been dated since its carousel went out, and would read as done.
        if post is None or recorded(post, prefix):
            continue
        seen.add(stem)
        report.fix("gate", f"{stem} was tapped and still has no "
                           f"published_at. If you tapped it just now the "
                           f"poll may not have run yet; if this repeats "
                           f"tomorrow the tap was lost — dispatch "
                           f"publish.yml.")


def check_metrics(updates: list, today: str, report: Report,
                  directory: Path | None = None) -> None:
    """Answers that were never written down, and asks nobody answered."""
    orphans = 0
    for update in updates:
        message = update.get("message") or {}
        asked = (message.get("reply_to_message") or {}).get("text", "")
        match = METRICS_ASK_RE.search(asked or "")
        # Only a message that is actually an answer (three or five numbers)
        # counts. record_metrics
        # ignores anything else in silence, and reporting a chat message as a
        # dropped answer would be reporting on a conversation.
        if not metrics_reply(str(message.get("text", ""))):
            continue
        # Three numbers replying to nothing — or to the wrong message — are
        # the one failure record_metrics cannot report on itself. It drops
        # them because reply_to_message is the only thing that says which
        # post they answer, and it drops them silently because getUpdates
        # carries no offset: a nudge sent from the poll would be sent again
        # on every poll for twenty-four hours. Once a day, from a different
        # run, is the only place this can be said without becoming that.
        if not match:
            orphans += 1
            continue
        path = locate(match.group(1))
        post = read_post(path) if path else None
        if post is None:
            continue
        have = post.get(METRICS_KEY) or {}
        # The core three, not every field: reach and follows are optional,
        # and an answer without them is an answer.
        if all(field in have for field in METRICS_CORE):
            continue
        report.fix("metrics", f"{match.group(1)} was answered and the "
                              f"numbers are not in the JSON — dispatch "
                              f"publish.yml to re-read the reply.")

    # One finding for the lot: the same mistake nine times is one habit.
    if orphans:
        report.fix("metrics", f"{orphans} message(s) of numbers arrived "
                              f"without replying to a question, so nothing "
                              f"knows which post they answer and they were "
                              f"dropped. Long-press the 📊 message itself and "
                              f"use Reply.")

    directory = directory or POSTS_DIR
    for path in post_order(directory):
        post = read_post(path) or {}
        block = post.get(METRICS_KEY) or {}
        asked_at = str(block.get("asked_at", "")).strip()
        if not asked_at or all(f in block for f in METRICS_CORE):
            continue
        try:
            age = (date.fromisoformat(today) - date.fromisoformat(asked_at)).days
        except ValueError:
            continue
        if age >= METRICS_PATIENCE_DAYS:
            report.fix("metrics", f"{path.stem} was asked about {age} days "
                                  f"ago and never answered — reply to that "
                                  f"message with saves, shares, visits.")


def check_colour(report: Report, directory: Path | None = None) -> None:
    """No two posts a reader meets in a row share a field.

    render.vary() keeps a drafted post off its predecessor's hue and
    render.py warns at render time, but a Breakdown is written by hand and
    never passes through either, and neither of them can see a run that is
    already published. This walks the whole archive in reading order, which
    is the only place a shipped run is visible at all.
    """
    previous: str | None = None
    previous_path: Path | None = None
    for path in post_order(directory):
        post = read_post(path) or {}
        name = post.get("colorway")
        if name and name not in COLORWAYS:
            report.fix("colour", f"{path.name} has colorway {name!r}, which "
                                 f"is not a family — render falls back to "
                                 f"signal. Valid: {', '.join(COLORWAYS)}")
        if name and name == previous and previous_path is not None:
            # A run that is already on the grid is history: there is nothing
            # to re-render and no tap to withhold. Reporting it as a finding
            # would send the same unfixable message every single day, which
            # is precisely what teaches a person to stop reading the bot. It
            # stays a note so a hand run still shows the whole archive.
            say = report.fix if not post.get("published_at") else report.note
            fix = (f" Re-render it with --colorway {vary(name, previous)}."
                   if not post.get("published_at")
                   else " Already published — nothing to do.")
            say("colour", f"{path.name} is the second {name} post in a row, "
                          f"after {previous_path.name}.{fix}")
        # Step over a post whose colorway is unrecognised rather than ending
        # the walk, exactly as previous_colorway() does — one bad record must
        # not silently disable the rule for everything after it.
        if name in COLORWAYS:
            previous, previous_path = name, path


def check_buffer(report: Report, directory: Path | None = None) -> None:
    """How many drafts are waiting at the gate."""
    waiting = [path for path in post_order(directory or POSTS_DIR)
               if not (read_post(path) or {}).get("published_at")]
    if len(waiting) > MAX_BUFFER:
        report.fix("buffer", f"{len(waiting)} drafts are waiting for the "
                             f"gate: {', '.join(p.stem for p in waiting)}. "
                             f"More than {MAX_BUFFER} means posts are being "
                             f"drafted faster than they are published.")
    else:
        report.note("buffer", f"{len(waiting)} draft(s) waiting at the gate")


def check_feeds(report: Report) -> None:
    """Every feed still returns entries — and still publishes them.

    A dead feed does not fail anything: ingest.py logs it and goes on, the
    queue quietly stops growing from that source, and nobody finds out until
    draft.py runs short. This is the sweep CLAUDE.md requires by hand after a
    feeds/ change, run on a schedule so a feed that dies on its own is found
    the same way.

    Staleness is the second half, and it is the half that used to be
    invisible. A publication that stops does not take its feed down with it:
    the URL answers 200 for years, feedparser returns a full item list, and
    every check above it passes. What changes is downstream — ingest.py drops
    each of those items on MAX_AGE_DAYS, so the feed contributes no rows at
    all, and asking only "did entries come back" cannot see the difference.
    SemiAnalysis was wired into feeds/tier5_depth.yaml on 2026-09-22 on the
    strength of a clean OK and 10 entries, none of them newer than Sep 2025.

    Reported as a FIX, not a note: unlike a colour run that already shipped,
    this is actionable in both directions — the publication moved and the URL
    can be corrected, or it ended and the entry should come out.
    """
    from verify_feeds import (STALE_AFTER_DAYS, all_feeds,      # feedparser
                              check_feed)                       # + yaml

    dead: list[str] = []
    stale: list[str] = []
    drifted: list[str] = []
    empty = 0
    for _, entry in all_feeds():
        name = entry.get("name", "unnamed")
        status, detail, age, drift = check_feed(entry)
        if drift:
            drifted.append(f"{name} — {drift}")
        if status == "fail":
            dead.append(f"{name} — {detail}")
        elif status == "empty":
            empty += 1
        # age is None for an undated feed, which has no age to test. ingest.py
        # keeps undated entries on purpose, so silence here is the same
        # decision one layer up, not an oversight.
        elif age is not None and age >= STALE_AFTER_DAYS:
            stale.append(f"{name} — published nothing in {age} days, so "
                         f"ingest drops every item on age")

    for line in dead[:MAX_NAMED]:
        report.fix("feeds", line)
    if len(dead) > MAX_NAMED:
        report.fix("feeds", f"and {len(dead) - MAX_NAMED} more")
    if dead:
        report.fix("feeds", "run the feed-scout agent — it finds where each "
                            "one moved and proposes the corrected YAML")

    for line in stale[:MAX_NAMED]:
        report.fix("feeds", line)
    if len(stale) > MAX_NAMED:
        report.fix("feeds", f"and {len(stale) - MAX_NAMED} more stale")
    if stale:
        report.fix("feeds", "feed-scout finds the successor feed if there is "
                            "one; retire the entry if there is not")

    # A live feed whose `announces` prefixes stopped fitting it: launches
    # from it fall back to the model's label and lose their duplicate key,
    # and nothing else would say so. See verify_feeds.announces_drift().
    for line in drifted[:MAX_NAMED]:
        report.fix("feeds", line)

    if empty:
        report.note("feeds", f"{empty} feed(s) parsed but returned 0 entries")
    if not dead and not empty and not stale and not drifted:
        report.note("feeds", "every feed is live and publishing")


def check_queue(report: Report) -> None:
    """Rows are still arriving, and candidates are still scored.

    Reads the sheet directly rather than through draft.py, which would drag
    in the LLM clients for three counts. The status vocabulary is score.py's:
    new → queued | rejected → drafted | duplicate.
    """
    try:
        from ingest import (COLUMNS, MAX_STORY_AGE_DAYS,   # gspread
                            open_sheet, story_age_days)
        rows = open_sheet().get_all_values()
    except SystemExit as exc:
        # open_sheet exits with instructions when the credentials are not
        # there. A watcher that dies on one unconfigured check reports
        # nothing about the eight that are fine.
        report.note("queue", f"not checked — {exc}")
        return
    except Exception as exc:                # noqa: BLE001 - any client error
        report.note("queue", f"not checked — {type(exc).__name__}: {exc}")
        return

    status, fetched = COLUMNS.index("status"), COLUMNS.index("fetched_at")
    body = [row for row in rows[1:] if len(row) > status]
    # Counted as draft.pick_row() sees them: a queued row older than
    # MAX_STORY_AGE_DAYS is never chosen, so it is not a candidate here
    # either — counting it would report a healthy queue the day drafting
    # stops for want of fresh news.
    col = {name: i for i, name in enumerate(COLUMNS)}
    now = datetime.now(timezone.utc)
    queued_rows = [row for row in body if row[status] == "queued"]
    fresh = sum(1 for row in queued_rows
                if (age := story_age_days(row, col, now)) is not None
                and age <= MAX_STORY_AGE_DAYS)
    unscored = sum(row[status] == "new" for row in body)

    if fresh < QUEUE_FLOOR:
        report.fix("queue", f"only {fresh} candidate(s) from the last "
                            f"{MAX_STORY_AGE_DAYS} days above the score "
                            f"threshold ({len(queued_rows)} queued in all). "
                            f"Check ingest.yml is scoring, run the "
                            f"evergreen-scout agent, or draft with "
                            f"--evergreen.")
    else:
        report.note("queue", f"{fresh} fresh of {len(queued_rows)} queued, "
                             f"{unscored} unscored, {len(body)} rows")
    # Asked whether or not the queue is short: a thin queue full of lifted
    # rows is the case most worth hearing about.
    check_lift(body, col, now, report)

    newest = max((row[fetched] for row in body
                  if len(row) > fetched and row[fetched]), default="")
    if not newest:
        report.fix("queue", "no row carries a fetched_at — has ingest.py "
                            "ever written to this sheet?")
        return
    try:
        age = datetime.now(timezone.utc) - datetime.fromisoformat(newest)
    except ValueError:
        report.note("queue", f"newest fetched_at is unreadable: {newest!r}")
        return
    if age > timedelta(hours=INGEST_SILENCE_HOURS):
        report.fix("queue", f"nothing new in {age.days * 24 + age.seconds // 3600}h "
                            f"— ingest.yml is running and adding no rows. "
                            f"Check the feeds section above.")


# score.py writes each row's axes into `notes` as a letter and a number —
# "n6 v3 e7 s6 r8 · why" — novelty, visual, explain, surprise, relevance.
NOTE_AXIS_RE = re.compile(r"\b([nvesr])(\d+(?:\.\d+)?)\b")
LIFT_AXES = "nves"            # score.AXES, by initial; relevance is the lift
# Rows queued in the last day that only relevance put there. Above this
# share of the day's queued rows, relevance is choosing the queue rather
# than adding launches to it. A first guess, not a measurement: on the 60
# rows measured on 2026-10-07 the lift added 1 of 5. Revisit it at the
# first week's review (docs/decisions/voice-and-selection.md).
MAX_LIFTED_SHARE = 0.5


def lifted(note: str) -> bool:
    """Whether a queued row's score came from relevance, not its axes.

    True when the four axes average under 7 — so the row could only have
    cleared score.THRESHOLD through the relevance lift. A note from before
    relevance existed has no "r" and is never lifted.
    """
    axes = {k: float(v) for k, v in NOTE_AXIS_RE.findall(note.split("·")[0])}
    if "r" not in axes or not all(a in axes for a in LIFT_AXES):
        return False
    return sum(axes[a] for a in LIFT_AXES) / len(LIFT_AXES) < 7


def check_lift(body: list[list[str]], col: dict, now: datetime,
               report: Report) -> None:
    """Which of the last day's queued rows only relevance let in.

    The lift (score.LIFT_AT) is how launches reach the queue, and the
    model's relevance is noisy: the same launch scored 8 in one batch and 2
    in another. A customer story scored 8 would be queued on that alone.
    So every lifted row is named, for a person to glance at, and a day
    where they are most of the queue is a FIX.
    """
    from ingest import story_age_days                       # gspread
    if "notes" not in col:
        return
    day = [row for row in body
           if row[col["status"]] in ("queued", "drafted")
           and (age := story_age_days(row, {"fetched_at": col["fetched_at"]},
                                      now)) is not None and age <= 1]
    lift = [row for row in day if len(row) > col["notes"]
            and lifted(row[col["notes"]])]
    if not lift:
        return
    names = [row[col["title"]][:70] for row in lift[:MAX_NAMED]]
    line = (f"{len(lift)} of the last day's {len(day)} queued rows got in on "
            f"relevance alone: " + "; ".join(names)
            + (f"; and {len(lift) - MAX_NAMED} more" if len(lift) > MAX_NAMED
               else ""))
    if len(lift) > MAX_LIFTED_SHARE * len(day):
        report.fix("lift", line + ". That is most of the queue: check none "
                                  "is a customer story or marketing, and "
                                  "consider raising score.LIFT_AT.")
    else:
        report.note("lift", line)


def check_structure(result: str, report: Report) -> None:
    """check.yml's verdict, handed over by the workflow.

    It runs as a called workflow rather than inside this process because it
    is already defined once and two callers is the point. Its result arrives
    as a string so that a red check is a line in this report rather than an
    ✗ on a scheduled run nobody is watching.
    """
    if not result or result in ("success", "skipped"):
        return
    where = ""
    server, repo, run = (os.getenv("GITHUB_SERVER_URL", ""),
                         os.getenv("GITHUB_REPOSITORY", ""),
                         os.getenv("GITHUB_RUN_ID", ""))
    if server and repo and run:
        where = f" {server}/{repo}/actions/runs/{run}"
    report.block("structure", f"check.yml came back {result} — a module, a "
                              f"template, the archive or the Spanish is "
                              f"broken on master.{where}")


def check_factcheck(report: Report) -> None:
    """Whether the gate is verifying anything at all.

    review.yml skips the fact-check with no token and writes a stand-in that
    deliberately does not hold the post, so the button behaves exactly as it
    did before fact-checking existed. That is the right behaviour and it is
    invisible: the only symptom is posts sailing through unverified.
    """
    if os.getenv("HAS_CLAUDE", "").strip().lower() == "false":
        report.fix("fact-check", "CLAUDE_CODE_OAUTH_TOKEN is not set, so "
                                 "review.yml is skipping the fact-check and "
                                 "every post is reaching the gate unverified. "
                                 "Re-run `claude setup-token`.")


def updates_from_telegram(token: str, chat_id: str, report: Report) -> list:
    """The same offset-less read confirm() does, so it consumes nothing.

    getUpdates without an offset leaves the cursor alone, which is what lets
    a tap replay for 24 hours and what makes confirm() idempotent. Reading
    the same window from a second process is therefore free: this cannot
    take a tap away from the poll that is meant to act on it. Filtered by
    chat the way confirm() filters, so a tap it ignores is not reported here
    as lost.
    """
    try:
        polled = poll(token)
    except TelegramError as exc:
        report.note("gate", f"taps not checked — {exc}")
        return []
    if len(polled) >= UPDATES_LIMIT:
        report.fix("gate", f"Telegram returned its cap of {UPDATES_LIMIT} "
                           f"updates. Any tap newer than those is invisible "
                           f"to publish.yml until the oldest age out of the "
                           f"24 hours. Check tomorrow that today's posts got "
                           f"published_at; dispatch publish.yml if not.")
    return ours(polled, chat_id)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--send", action="store_true",
                    help="send the report to Telegram when it is not a PASS")
    ap.add_argument("--skip-feeds", action="store_true",
                    help="skip the feed sweep, which is the slow part")
    ap.add_argument("--structure", default="",
                    help="the result of the check.yml job, from the workflow")
    args = ap.parse_args()

    report = Report("WATCH")
    today = publish_date()

    # config() exits with instructions when the token is missing. With --send
    # that is the right end: a watcher that cannot speak has no job. Without
    # it, this is someone at a terminal reading the output, so the Telegram
    # half degrades to a note and the other seven checks still run.
    if args.send:
        token, chat_id = config(need_chat=True)
    else:
        try:
            token, chat_id = config(need_chat=False)
        except SystemExit:
            token, chat_id = "", ""
            report.note("gate", "no TELEGRAM_BOT_TOKEN — taps not checked")

    check_structure(args.structure, report)
    check_cadence(today, report)
    check_weekly(today, report)
    check_subject(today, report)
    if token and not chat_id:
        report.note("gate", "no TELEGRAM_CHAT_ID — taps not checked")
    elif token:
        updates = updates_from_telegram(token, chat_id, report)
        check_gate(updates, report)
        check_metrics(updates, today, report)
    check_colour(report)
    check_buffer(report)
    check_factcheck(report)
    check_queue(report)
    if args.skip_feeds:
        report.note("feeds", "skipped")
    else:
        check_feeds(report)

    body = report.render()
    print(body)

    # Notes do not move the verdict, so a PASS carrying nothing but notes is
    # silence. A daily "all clear" is what teaches a person to mute the bot,
    # which is the failure notify-failure's throttle was removed over.
    if args.send and report.verdict != "PASS":
        send_report(token, chat_id, "watch", body)
        print("\nSent to Telegram.")

    # 0 even on findings: the message is the report, and a non-zero exit
    # would make notify-failure send a second message about the same thing.
    return 0


if __name__ == "__main__":
    sys.exit(main())
