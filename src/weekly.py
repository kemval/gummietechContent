#!/usr/bin/env python3
"""
The weekly carousels Claude writes: Tuesday's glossary term, Thursday's
Breakdown, and on Sunday, alternating by ISO week, "Can I run it?" or the
Incident Report. What weekly.yml decides in code, around the one step a
model does.

    python src/weekly.py due <kind>             # exit 0 if this week still owes one
    python src/weekly.py brief <kind>           # the writer's instructions
    python src/weekly.py finish <kind> <draft>  # refuse a bad draft, or file it

<kind> is a key of KINDS: glossary, breakdown, reference or incident.

Neither is drafted by draft.py's free-tier model. A definition and a
mechanism are exactly where a model invents a confident one, and docs §4
gives both to Claude. Until 2026-10-06 a person ran that Claude session; now
weekly.yml does, once a week each. Everything that can be decided without a
model is decided here, before and after it writes:

  - whether this week's slot is already filled (`due`)
  - what the post is built from: a term's example is a published post the
    writer picks from a list; a Breakdown's subject is a published Drop this
    file picks, tech first, that has no Breakdown yet; a reference's model
    is a fresh published AI post, or Signal item, the writer picks from a
    list; an incident is the next evergreen row marked as one
  - a repeated term, a missing field, a mechanism of the wrong length
  - the credit. source_url, doi, attribution, peer_reviewed,
    announcement and news_report are copied
    from the post it is built from, never typed by the model. A retyped
    credit is the one way a correct explanation still goes out wrong.

Standard library, formats.py and evergreen.py only: `due` runs in the gate job, before
anything is installed, and watch.py reads KINDS.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import NamedTuple

import evergreen
from formats import FORMATS, LADDER, PAIR, hashtags, unpaired

REPO_ROOT = Path(__file__).resolve().parent.parent
POSTS_DIR = REPO_ROOT / "posts"

# The credit fields copied from the post a draft is built from. The model's
# draft never supplies them; finish() overwrites whatever it wrote.
# `announcement` travels with the rest: a Breakdown of a launch is about an
# announcement too, and without it the slides would call it a preprint.
CREDIT = ("source_url", "doi", "attribution", "peer_reviewed", "announcement",
          "news_report", "incident_report")

# draft.PRIORITY_BEATS, restated rather than imported: draft.py pulls in the
# LLM clients and gspread, and this runs before pip install. Posts drafted
# before score.py named a beat have none, so the signal colorway — AI,
# computing, software, robotics — stands in for it.
TECH_BEATS = frozenset({"ai", "software", "automation", "robotics", "computing",
                        "engineering"})

# ingest.MAX_STORY_AGE_DAYS, restated for TECH_BEATS' reason. The reason
# draft.pick_row() has it applies on Sunday too: "can I run the model that
# came out last month" is a question nobody is asking any more.
FRESH_DAYS = 10

# A rung's line, after its colon, in words. sheet.html sets all five rungs on
# one slide at the sheet's type size, which holds five one-line entries and
# not five two-line ones: the 2026-10-18 sample fitted with lines of four to
# eight words. Refused in finish() rather than left to proof.py, which would
# only say so at the gate.
MAX_RUNG_WORDS = 8

# The benchmark lines after the ladder: docs' Benchmark Decoder, sharing the
# post rather than taking a Sunday of its own.
BENCHMARK_LINES = (2, 3)


class Kind(NamedTuple):
    """One weekly carousel Claude writes.

    `slot` is what fills the week: docs §1 has the Cheat Sheet, written by a
    person, take the glossary's place every sixth Tuesday, so a sheet counts.
    """
    post_type: str
    slot: tuple[str, ...]
    weekday: int            # date.weekday(): Monday is 0


KINDS: dict[str, Kind] = {
    "glossary":  Kind("term", ("term", "sheet"), 1),      # Tuesday
    "breakdown": Kind("breakdown", ("breakdown",), 3),    # Thursday
    "reference": Kind("reference", ("reference",), 6),    # Sunday, even weeks
    "incident":  Kind("incident", ("incident",), 6),      # Sunday, odd weeks
}


def scheduled(day: date) -> str:
    """The kind written on this day, or "" for a day with none.

    Two kinds share Sunday, and they take turns by ISO week, in KINDS order:
    week 42 of 2026, the first Sunday with any, is a reference. The gate in
    weekly.yml and watch.check_weekly() both ask here, so they agree about
    whose Sunday it is.
    """
    names = [n for n, k in KINDS.items() if k.weekday == day.weekday()]
    return names[day.isocalendar().week % len(names)] if names else ""


def read(path: Path) -> dict | None:
    try:
        post = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        print(f"  skipped {path.name}: {exc}", file=sys.stderr)
        return None
    return post if isinstance(post, dict) else None


def posts(directory: Path) -> list[tuple[Path, dict]]:
    return [(path, post) for path in sorted(directory.glob("*.json"))
            if (post := read(path)) is not None]


def every_post(directory: Path) -> list[dict]:
    """posts/ and posts/rejected/: a subject turned down at the gate once
    should not come back next week unchanged — draft.covered_papers()'s
    reason for reading rejected/ too."""
    return [post for folder in (directory, directory / "rejected")
            for _, post in posts(folder)]


def due(kind: Kind, today: date, directory: Path = POSTS_DIR) -> list[Path]:
    """This week's post in the kind's slot, if any. Empty means still owed.

    Asked by filename date from Monday, the window watch.check_weekly() uses,
    so the gate and the watcher agree about which week a post fills.
    """
    monday = today - timedelta(days=today.weekday())
    found = []
    for path, post in posts(directory):
        try:
            drafted = date.fromisoformat(path.name[:10])
        except ValueError:
            continue
        if monday <= drafted <= today and post.get("post_type") in kind.slot:
            found.append(path)
    return found


def published(directory: Path) -> list[tuple[str, dict]]:
    """Published posts with one source of their own, newest first."""
    return [(path.stem, post) for path, post in reversed(posts(directory))
            if post.get("published_at")
            and post.get("post_type") not in ("signal", "term", "sheet",
                                              "reference")]


def is_tech(post: dict) -> bool:
    beat = str(post.get("beat", "")).strip().lower()
    return beat in TECH_BEATS if beat else post.get("colorway") == "signal"


# ------------------------------------------------------------ the glossary

def defined_terms(directory: Path = POSTS_DIR) -> list[str]:
    return [str(p["term"]).strip() for p in every_post(directory)
            if p.get("post_type") == "term" and p.get("term")]


def examples(directory: Path = POSTS_DIR) -> list[tuple[str, dict]]:
    """Published posts a new term may point to, newest first.

    One already used as some term's example is left out, so the glossary
    walks across the archive instead of defining five words from one paper.
    """
    used = {str(p.get("example_post", "")).strip() for p in every_post(directory)
            if p.get("post_type") == "term"}
    return [(stem, post) for stem, post in published(directory)
            if stem not in used]


# ----------------------------------------------------------- the breakdown

def subject(directory: Path = POSTS_DIR) -> tuple[str, dict] | None:
    """The published Drop this week's Breakdown explains, or None.

    A Drop says what happened; a Breakdown explains how, and the account
    deepening a story it already told is how the one on hallucination came
    about. Its paper has already passed a fact-check and the gate. Skipped:
    any paper a Breakdown already covers, by DOI or by source URL. Tech
    first, as draft.pick_row() is; then newest.
    """
    covered = set()
    for post in every_post(directory):
        if post.get("post_type") == "breakdown":
            covered |= {str(post.get(f, "")).strip().lower()
                        for f in ("doi", "source_url")} - {""}
    drops = [(stem, post) for stem, post in published(directory)
             if post.get("post_type") in ("drop", "run")
             and str(post.get("source_url", "")).strip()
             and not {str(post.get(f, "")).strip().lower()
                      for f in ("doi", "source_url")} & covered]
    tech = [d for d in drops if is_tech(d[1])]
    return (tech or drops or [None])[0]


# ----------------------------------------------------- the reference sheet

def item_ref(stem: str, n: int) -> str:
    """How a reference names one Signal item: its post's stem and its 1-based
    place, so the credit can be read back from exactly that item."""
    return f"{stem}#{n}"


def sources(today: date, directory: Path = POSTS_DIR) -> list[tuple[str, dict]]:
    """What this Sunday's "Can I run it?" may be built on, newest first.

    Each entry is a published, fact-checked source, so its credit can be
    copied the way a term's is. Fresh AI posts come first: Drops and run
    posts dated within FRESH_DAYS, and the items of Signals dated within it,
    since a week's model launches mostly reach this account as Signal items.
    Code cannot tell from a record whether a model's weights can be
    downloaded, so the writer chooses from this list and reads the source.
    Only when nothing fresh is left does an older run post stand in. Its
    repo is already verified, and running it is what the post is about. Any
    source a reference already covers is skipped, by DOI or by source URL.
    """
    covered = set()
    for post in every_post(directory):
        if post.get("post_type") == "reference":
            covered |= {str(post.get(f, "")).strip().lower()
                        for f in ("doi", "source_url")} - {""}

    def fresh_ai(record: dict, stem: str) -> bool:
        try:
            drafted = date.fromisoformat(stem[:10])
        except ValueError:
            return False
        beat = str(record.get("beat", "")).strip().lower()
        ai = beat == "ai" if beat else record.get("colorway") == "signal"
        return ai and 0 <= (today - drafted).days <= FRESH_DAYS

    def uncovered(record: dict) -> bool:
        keys = {str(record.get(f, "")).strip().lower()
                for f in ("doi", "source_url")} - {""}
        return bool(str(record.get("source_url", "")).strip()) and not keys & covered

    fresh, runs = [], []
    for path, post in reversed(posts(directory)):
        if not post.get("published_at"):
            continue
        if post.get("post_type") == "signal":
            for n, item in enumerate(post.get("items") or [], start=1):
                if (isinstance(item, dict) and fresh_ai(item, path.stem)
                        and uncovered(item)):
                    fresh.append((item_ref(path.stem, n), item))
        elif post.get("post_type") in ("drop", "run") and uncovered(post):
            if fresh_ai(post, path.stem):
                fresh.append((path.stem, post))
            elif post.get("post_type") == "run":
                runs.append((path.stem, post))
    return fresh or runs


def resolve(ref: str, directory: Path = POSTS_DIR) -> dict:
    """The record a reference is built on: a post, or one Signal item."""
    stem, _, n = ref.partition("#")
    post = read(directory / f"{stem}.json") or {}
    if not n:
        return post
    items = post.get("items") or []
    at = int(n) - 1 if n.isdigit() else -1
    return items[at] if 0 <= at < len(items) and isinstance(items[at], dict) else {}


# --------------------------------------------------------- the incident

def incident(directory: Path = POSTS_DIR,
             queue: Path = evergreen.QUEUE) -> evergreen.Row | None:
    """The evergreen row this Sunday's Incident Report tells, or None.

    The first row marked `**Kind** — incident`, in the file's score order,
    whose source no post in posts/ or posts/rejected/ already carries,
    whether it was drafted as an Incident Report, a Drop or a Signal item.
    """
    covered = set()
    for post in every_post(directory):
        for record in (post, *(i for i in post.get("items") or []
                               if isinstance(i, dict))):
            if url := str(record.get("source_url", "")).strip().lower():
                covered.add(url)
    try:
        text = queue.read_text()
    except OSError as exc:
        raise SystemExit(f"Cannot read {queue}: {exc}. The Incident Report "
                         f"is picked from it; restore the file.")
    for row in evergreen.rows(text):
        if (row.fields.get("kind", "").strip().lower() == "incident"
                and evergreen.source_url(row.fields).lower() not in covered):
            return row
    return None


def incident_credit(row: evergreen.Row) -> dict:
    """The credit an Incident Report carries, from its row: the row's
    primary, the person or body it says to attribute, and the label that
    says what such a source is."""
    return {"source_url": evergreen.source_url(row.fields),
            "attribution": evergreen.credit(row.fields),
            "peer_reviewed": False,
            "incident_report": True}


# ---------------------------------------------------------------- the brief

def brief(name: str, directory: Path = POSTS_DIR,
          today: date | None = None) -> str:
    """The writer's whole instruction, with the menu code already chose."""
    if name == "reference":
        found = sources(today or date.today(), directory)
        if not found:
            raise SystemExit("No published AI post from the last "
                             f"{FRESH_DAYS} days, and no run post, is left "
                             "without a reference. Write this Sunday's by "
                             "hand, or skip it.")
        menu = [f"  - {ref}  —  {rec.get('hook') or rec.get('claim', '')}  "
                f"({rec.get('source_url', '')})" for ref, rec in found]
        ladder = "\n".join(f"  {n}. {rung}" for n, rung in
                           enumerate(LADDER, start=1))
        return REFERENCE_BRIEF.format(menu="\n".join(menu), ladder=ladder,
                                      rungs=len(LADDER), words=MAX_RUNG_WORDS,
                                      lo=BENCHMARK_LINES[0],
                                      hi=BENCHMARK_LINES[1])
    if name == "incident":
        row = incident(directory)
        if row is None:
            raise SystemExit("Every evergreen row marked `**Kind** — "
                             "incident` is already covered. Run the "
                             "evergreen-scout agent for more, or write this "
                             "Sunday's by hand.")
        return INCIDENT_BRIEF.format(rank=row.rank, title=row.title,
                                     row=row.body.strip(),
                                     source_url=evergreen.source_url(row.fields))
    if name == "glossary":
        terms = [f"  - {t}" for t in defined_terms(directory)] or ["  (none)"]
        menu = [f"  - {stem}  —  {post.get('hook', '')}"
                for stem, post in examples(directory)] or ["  (none)"]
        return GLOSSARY_BRIEF.format(terms="\n".join(terms),
                                     menu="\n".join(menu))
    found = subject(directory)
    if found is None:
        raise SystemExit("No published Drop is left without a Breakdown. "
                         "Write this week's by hand, or publish more Drops.")
    stem, post = found
    return BREAKDOWN_BRIEF.format(stem=stem, hook=post.get("hook", ""),
                                  source_url=post.get("source_url", ""))


SHARED_RULES = """\
Rules:
  - Every claim comes from the source or from the post you build on. Do not
    add a number, a name or a claim that is in neither.
  - Write in the voice docs/voice.md describes: read it first. Where it and
    these rules disagree, these rules win.
  - hook within 12 words; every other slide field within 25 words.
  - colorway is signal, orbit, bloom or ember, by CLAUDE.md's colorway
    table: AI; software and quantum; data and infrastructure; hardware.
  - caption ends in a question that takes one word or one memory to
    answer: a choice between two things, or the reader's own experience.
    Never "how will this change...".
  - Do NOT write source_url, doi, attribution, peer_reviewed, announcement,
    news_report, es or published_at. Code copies the credit after you; the rest is not
    yours.
  - Write /tmp/weekly/draft.json and no other file.
"""

GLOSSARY_BRIEF = """\
Write this week's glossary term for @gummietech, an Instagram account on
science and technology, tech first.

Read first:
  - docs/gummietech_content_system.md, the Glossary under §1
  - src/formats.py, the "term" entry
  - posts/2026-10-06-glossary-hallucination.json, a term that passed the
    gate: match its shape and its register

Terms already defined (do not define these again):
{terms}

Published posts you may use as example_post (stem, then hook):
{menu}

Then:
  1. Pick one example post above and read its JSON in posts/. Prefer an AI,
     computing or software post. Pick a term a curious non-specialist meets
     in the news and would want to keep the meaning of, which that post
     shows in action.
  2. Read the post's source_url. The definition must agree with how that
     source uses the word. If it cannot be read, pick another post rather
     than defining from memory.
  3. Write /tmp/weekly/draft.json with exactly these fields: post_type
     ("term"), domain, colorway, hook, term, definition, example, the_catch,
     example_post (the stem, no .json), caption, keywords, hashtags,
     alt_text.

  - example says what that post showed, in that post's own facts.
  - the_catch is the common mistake people make with the word: a misreading,
    not a weakness of the paper.

{rules}
Finish by printing the term, the example post, and one line on why.
""".replace("{rules}", SHARED_RULES)

BREAKDOWN_BRIEF = """\
Write this week's Breakdown for @gummietech, an Instagram account on science
and technology, tech first. A Breakdown explains how something works, in
8 slides; it does not report news.

It explains the story of posts/{stem}.json, a Drop this account already
published ("{hook}"). Its source is {source_url}.

Read first:
  - docs/gummietech_content_system.md, "The Breakdown — 8–10 slides"
  - src/formats.py, the "breakdown" entry
  - posts/2026-09-27-why-language-models-hallucinate.json, a Breakdown that
    passed the gate: match its shape and its register
  - posts/{stem}.json, the Drop
  - the source itself, in full: for a paper, the paper and not only its
    abstract — prefer the arXiv HTML or the publisher's full text; for a
    write-up, the whole write-up and what it links as its own evidence. If
    you cannot read past an abstract or a summary, say so in your final
    message and write nothing: a mechanism explained from an abstract is
    the failure this format exists to avoid.

Write /tmp/weekly/draft.json with exactly these fields: post_type
("breakdown"), domain, colorway, hook, the_question, the_intuition,
mechanism (a list of 2 or 3 steps, one slide each), why_it_matters,
the_catch, caption, keywords, hashtags, alt_text. No recap.

  - the_question opens on a concrete case from the source.
  - the_intuition is the common first guess, which the mechanism corrects.
  - mechanism is how it works, in order, each step a slide on its own.
  - the_catch is the limits the source itself states. Not a weakness you
    infer: a caveat the source does not state is the error the fact-check
    blocks most.
  - If the Drop's peer_reviewed is false, the_catch says what that means:
    a preprint not yet peer-reviewed, or — when the Drop carries
    "announcement": true — the maker's own announcement, not a study, or —
    with "news_report": true — a news outlet's report, not a study.

{rules}
Finish by printing the hook and one line on what the mechanism is.
""".replace("{rules}", SHARED_RULES)


REFERENCE_BRIEF = """\
Write this Sunday's "Can I run it?" for @gummietech, an Instagram account on
technology. It is a cheat sheet about one AI model that came out recently:
whether it runs on machines readers own, and what its benchmark numbers mean
in plain words. The point is a sheet people save.

Read first:
  - src/formats.py, the "reference" entry
  - docs/voice.md

Published posts and Signal items you may build on (ref, then cover line or
claim, then source). Fresh ones come first:
{{menu}}

Then:
  1. Pick the first one above that is a model whose weights anyone can
     download (an open-weights release on Hugging Face, or a repo with the
     weights). Read its source in full. If none of them has downloadable
     weights, say so in your final message and write nothing.
  2. Find what memory it needs. In order of preference: the model card's own
     requirements table, the quantization table of the repo that ships the
     quantized files (for example a GGUF repo on Hugging Face), or a named
     VRAM calculator. Write down the URL of each figure you use.
  3. Write /tmp/weekly/draft.json with exactly these fields: post_type
     ("reference"), domain, colorway, hook, items, the_catch, source_post
     (the ref above, exactly as written), figure_sources, caption, keywords,
     hashtags, alt_text.

  - items is a list of strings, each "Term: line". The first {{rungs}} are this
    hardware ladder, in this order, with these exact terms:
{{ladder}}
    Each rung's line says the largest size and quantization of this model
    that fits on that machine, and its memory, or "No" and the smaller model
    to use instead. For example "MacBook Air, 16 GB: Yes, 8B at Q4, about 6
    GB". At most {{words}} words after the colon: all five share one slide.
    Tokens per second only when a source measured them on that machine.
  - Then {{lo}} or {{hi}} benchmark lines, each a benchmark the model card
    reports, turned into the task it measures, with the number. For example
    "MMLU 78: Answers 78 of 100 university-exam questions right". Every
    line after the colon starts with a capital letter. When the
    card compares models, say how big a gap is noise and how big is a real
    difference.
  - hook is the verdict, not the model's name: "Yes, it runs on a MacBook
    Air", "You need 24 GB, not 8". It must be true of the ladder below it.
  - One line of the sheet should surprise: a small size winning something,
    or the context window costing more memory than the model. If the source
    gives you no surprise, say so in your final message.
  - the_catch is the limit of these benchmarks that the headline leaves out:
    the maker's own numbers, English only, a test the model may have seen in
    training. It must be stated or plainly shown by the source. A caveat you
    infer yourself is the error the fact-check blocks most.
  - figure_sources is a list of strings, one per hardware figure: "<rung>:
    <url>". A figure you computed rather than read says "about … ,
    estimated" in its line, and its figure_sources entry names the
    calculator or the arithmetic. No figure without an entry.
  - caption ends in a one-word question, such as "What do you run models on?"

{{rules}}
Finish by printing the ref you built on and the hook.
""".replace("{{rules}}", SHARED_RULES).replace("{{", "{").replace("}}", "}")


INCIDENT_BRIEF = """\
Write this Sunday's Incident Report for @gummietech, an Instagram account on
technology. It tells one real failure in production: what broke, when, why,
how it was fixed, and what people usually get wrong about it. It explains a
famous failure; it does not report news.

It tells evergreen row #{rank} of docs/evergreen_queue.md, "{title}":

{row}

Read first:
  - docs/evergreen_queue.md, "Before drafting any of these": the numbers
    not to add apply to you
  - src/formats.py, the "incident" entry
  - docs/voice.md
  - the source itself, {source_url}, in full. The row is a summary, and a
    timeline written from a summary is the failure this format exists to
    avoid. If you cannot read the source, say so in your final message and
    write nothing.

Write /tmp/weekly/draft.json with exactly these fields: post_type
("incident"), domain, colorway, hook, what_broke, timeline (a list of 2 or
3 entries, one slide each), root_cause, the_fix, the_catch, caption,
keywords, hashtags, alt_text.

  - hook may start from the row's Hook, but check every word of it against
    the source.
  - what_broke is what people saw: the outage, the loss, the explosion, in
    the report's own figures.
  - timeline entries are in order, and each opens with its time as the
    source gives it ("37 seconds after lift-off", "09:30 ET"). No time the
    source does not state.
  - root_cause is the mechanism the report names, at the level a reader can
    follow. the_fix is what was changed afterwards, per the source.
  - the_catch is what people usually get wrong about this incident, and the
    source must support it. The row's own "The catch" is a good start.

{rules}
Finish by printing the hook and one line on the root cause.
""".replace("{rules}", SHARED_RULES)


# ---------------------------------------------------------------- finishing

# The longest a post's stem may be. telegram.py carries it in a button's
# callback_data, which Telegram caps at 64 bytes (telegram.CALLBACK_LIMIT),
# after its longest prefix, "held:" or "reel:". Restated, not imported:
# telegram.py needs `requests`, and this runs before pip install;
# tests/test_weekly.py holds the two equal. 2026-10-18: the first reference,
# "2026-10-18-reference-" plus a 40-character slug, came to 65 bytes and
# review.yml could not send it.
STEM_LIMIT = 64 - len("held:")


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:40] or "post"


def required(kind: Kind) -> list[str]:
    spec = FORMATS[kind.post_type]
    fields = [*spec.record, *(s.field for s in spec.sections if not s.optional),
              "domain", "colorway", "caption"]
    return [f for f in fields if f not in CREDIT]


def problems(name: str, post: dict, directory: Path = POSTS_DIR,
             today: date | None = None) -> list[str]:
    """Why this draft is not one weekly.yml may commit. Empty means fine."""
    kind = KINDS[name]
    found = []
    if post.get("post_type") != kind.post_type:
        found.append(f"post_type is {post.get('post_type')!r}, "
                     f"not {kind.post_type!r}")
    if post.get("published_at"):
        found.append("it carries published_at — only the human gate adds that")
    if "es" in post:
        found.append("it carries an es block — translate.py writes that")
    if missing := [f for f in required(kind) if not post.get(f)]:
        found.append(f"missing {', '.join(missing)}")
    if name == "glossary":
        term = str(post.get("term", "")).strip().lower()
        if term and term in {t.lower() for t in defined_terms(directory)}:
            found.append(f"{post['term']!r} is already defined")
        stem = str(post.get("example_post", "")).strip()
        if stem and stem not in {s for s, _ in examples(directory)}:
            found.append(f"example_post {stem!r} is not one of the published "
                         f"posts the brief offered")
    if name == "reference":
        found.extend(reference_problems(post, directory, today))
    if name == "incident":
        steps = post.get("timeline")
        if not (isinstance(steps, list) and 2 <= len(steps) <= 3
                and all(isinstance(s, str) and s.strip() for s in steps)):
            found.append("timeline must be a list of 2 or 3 non-empty "
                         "entries — one slide each")
    if name == "breakdown":
        steps = post.get("mechanism")
        if not (isinstance(steps, list) and 2 <= len(steps) <= 3
                and all(isinstance(s, str) and s.strip() for s in steps)):
            found.append("mechanism must be a list of 2 or 3 non-empty steps "
                         "— docs §1's 8 to 10 slides")
    return found


def reference_problems(post: dict, directory: Path,
                       today: date | None = None) -> list[str]:
    """Why a "Can I run it?" draft is not this Sunday's sheet."""
    found = []
    ref = str(post.get("source_post", "")).strip()
    if ref and ref not in {r for r, _ in sources(today or date.today(),
                                                 directory)}:
        found.append(f"source_post {ref!r} is not one of the posts the brief "
                     f"offered")
    items = post.get("items")
    if not (isinstance(items, list)
            and all(isinstance(i, str) for i in items)):
        return [*found, "items must be a list of \"Term: line\" strings"]
    terms = [i.partition(PAIR)[0].strip() for i in items]
    if tuple(terms[:len(LADDER)]) != LADDER:
        found.append(f"items must open on the hardware ladder, in order: "
                     f"{'; '.join(LADDER)}")
    if long := [f"{t} ({len(line.split())} words)"
                for t, line in (i.split(PAIR, 1) for i in items[:len(LADDER)]
                                if PAIR in i)
                if len(line.split()) > MAX_RUNG_WORDS]:
        found.append(f"a machine's line is at most {MAX_RUNG_WORDS} words, so "
                     f"the five fit one slide: {', '.join(long)}")
    lo, hi = BENCHMARK_LINES
    if not lo <= len(items) - len(LADDER) <= hi:
        found.append(f"after the ladder come {lo} or {hi} benchmark lines, "
                     f"not {len(items) - len(LADDER)}")
    if bad := unpaired(post):
        found.append(f"no \"Term: line\" split in {', '.join(bad)}")
    if low := [t for t, line in (i.split(PAIR, 1) for i in items if PAIR in i)
               if line.strip()[:1].islower()]:
        found.append(f"each line starts with a capital, as the sheet sets "
                     f"them: {', '.join(low)}")
    figures = post.get("figure_sources")
    if not (isinstance(figures, list) and figures
            and all(isinstance(f, str) and f.strip() for f in figures)):
        found.append("figure_sources must list where each hardware figure "
                     "comes from")
    return found


def built_from(name: str, post: dict, directory: Path) -> tuple[str, dict]:
    """The published post (or Signal item) whose credit this draft carries:
    its name, for the log, and its record."""
    if name == "glossary":
        stem = str(post["example_post"]).strip()
    elif name == "reference":
        ref = str(post["source_post"]).strip()
        return ref, resolve(ref, directory)
    elif name == "incident":
        row = incident(directory)
        return ((f"evergreen #{row.rank}", incident_credit(row)) if row
                else ("", {}))
    else:
        found = subject(directory)
        stem = found[0] if found else ""
    return stem, read(directory / f"{stem}.json") or {}


def finish(name: str, draft: Path, today: date,
           directory: Path = POSTS_DIR) -> int:
    """Refuse a bad draft, or stamp its credit and file it in posts/.

    The writer drafts outside the repo and this names the file, so the model
    never chooses a path in posts/ and the commit has one file to add. A
    Breakdown's subject is recomputed rather than taken from the draft: the
    same checkout gives the same answer, and the writer cannot move it.
    """
    post = read(draft)
    if post is None:
        print(f"{draft} is not a JSON object. Nothing has been committed; read "
              f"the writer's output in this log.", file=sys.stderr)
        return 1
    if bad := problems(name, post, directory, today):
        print(f"Refusing {draft.name}:", file=sys.stderr)
        for line in bad:
            print(f"  - {line}", file=sys.stderr)
        print(f"Nothing has been committed. Dispatch weekly.yml with "
              f"kind={name} and force to write another.", file=sys.stderr)
        return 1
    stem, source = built_from(name, post, directory)
    for field in CREDIT:
        if field in source:
            post[field] = source[field]
        else:
            post.pop(field, None)
    # Not credit, but the same rule: a Breakdown or a term is about the
    # subject of the post it is built from, and learn.py groups by it.
    if source.get("beat"):
        post["beat"] = source["beat"]
    post["hashtags"] = hashtags(post.get("hashtags"))
    words = post["term"] if name == "glossary" else post["hook"]
    prefix = {"glossary": "glossary-", "reference": "reference-",
              "incident": "incident-"}.get(name, "")
    filed = f"{today.isoformat()}-{prefix}{slug(words)}"[:STEM_LIMIT].rstrip("-")
    path = directory / f"{filed}.json"
    path.write_text(json.dumps(post, indent=2, ensure_ascii=False) + "\n")
    print(f"Built from {stem}; credit {post.get('attribution')!r} copied "
          f"from it.")
    print(f"Wrote {path.relative_to(REPO_ROOT)}")
    return 0


def main(argv: list[str]) -> int:
    command, name = (argv[1:3] + ["", ""])[:2]
    if name not in KINDS:
        print(__doc__, file=sys.stderr)
        return 2
    if command == "due":
        found = due(KINDS[name], date.today())
        if found:
            print(f"This week already has one: {', '.join(p.name for p in found)}")
            return 1
        print(f"This week has no {name} yet.")
        return 0
    if command == "brief":
        print(brief(name))
        return 0
    if command == "finish" and len(argv) == 4:
        return finish(name, Path(argv[3]), date.today())
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
