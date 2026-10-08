#!/usr/bin/env python3
"""
The weekly carousels Claude writes: Tuesday's glossary term and Thursday's
Breakdown. What weekly.yml decides in code, around the one step a model does.

    python src/weekly.py due <kind>             # exit 0 if this week still owes one
    python src/weekly.py brief <kind>           # the writer's instructions
    python src/weekly.py finish <kind> <draft>  # refuse a bad draft, or file it

<kind> is a key of KINDS: glossary or breakdown.

Neither is drafted by draft.py's free-tier model. A definition and a
mechanism are exactly where a model invents a confident one, and docs §4
gives both to Claude. Until 2026-10-06 a person ran that Claude session; now
weekly.yml does, once a week each. Everything that can be decided without a
model is decided here, before and after it writes:

  - whether this week's slot is already filled (`due`)
  - what the post is built from: a term's example is a published post the
    writer picks from a list; a Breakdown's subject is a published Drop this
    file picks, tech first, that has no Breakdown yet
  - a repeated term, a missing field, a mechanism of the wrong length
  - the credit. source_url, doi, attribution, peer_reviewed and
    announcement are copied
    from the post it is built from, never typed by the model. A retyped
    credit is the one way a correct explanation still goes out wrong.

Standard library and formats.py only: `due` runs in the gate job, before
anything is installed, and watch.py reads KINDS.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import NamedTuple

from formats import FORMATS

REPO_ROOT = Path(__file__).resolve().parent.parent
POSTS_DIR = REPO_ROOT / "posts"

# The credit fields copied from the post a draft is built from. The model's
# draft never supplies them; finish() overwrites whatever it wrote.
# `announcement` travels with the rest: a Breakdown of a launch is about an
# announcement too, and without it the slides would call it a preprint.
CREDIT = ("source_url", "doi", "attribution", "peer_reviewed", "announcement")

# draft.PRIORITY_BEATS, restated rather than imported: draft.py pulls in the
# LLM clients and gspread, and this runs before pip install. Posts drafted
# before score.py named a beat have none, so the signal colorway — AI,
# computing, software, robotics — stands in for it.
TECH_BEATS = frozenset({"ai", "software", "automation", "robotics", "computing"})


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
}


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
            and post.get("post_type") not in ("signal", "term", "sheet")]


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


# ---------------------------------------------------------------- the brief

def brief(name: str, directory: Path = POSTS_DIR) -> str:
    """The writer's whole instruction, with the menu code already chose."""
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
  - colorway is signal, orbit, bloom or ember, by docs §1's topics.
  - caption ends in a question.
  - Do NOT write source_url, doi, attribution, peer_reviewed, announcement,
    es or published_at. Code copies the credit after you; the rest is not
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
    "announcement": true — the maker's own announcement, not a study.

{rules}
Finish by printing the hook and one line on what the mechanism is.
""".replace("{rules}", SHARED_RULES)


# ---------------------------------------------------------------- finishing

def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:40] or "post"


def required(kind: Kind) -> list[str]:
    spec = FORMATS[kind.post_type]
    fields = [*spec.record, *(s.field for s in spec.sections if not s.optional),
              "domain", "colorway", "caption"]
    return [f for f in fields if f not in CREDIT]


def problems(name: str, post: dict, directory: Path = POSTS_DIR) -> list[str]:
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
    if name == "breakdown":
        steps = post.get("mechanism")
        if not (isinstance(steps, list) and 2 <= len(steps) <= 3
                and all(isinstance(s, str) and s.strip() for s in steps)):
            found.append("mechanism must be a list of 2 or 3 non-empty steps "
                         "— docs §1's 8 to 10 slides")
    return found


def built_from(name: str, post: dict, directory: Path) -> str:
    """The stem of the published post whose credit this draft carries."""
    if name == "glossary":
        return str(post["example_post"]).strip()
    found = subject(directory)
    return found[0] if found else ""


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
    if bad := problems(name, post, directory):
        print(f"Refusing {draft.name}:", file=sys.stderr)
        for line in bad:
            print(f"  - {line}", file=sys.stderr)
        print(f"Nothing has been committed. Dispatch weekly.yml with "
              f"kind={name} and force to write another.", file=sys.stderr)
        return 1
    stem = built_from(name, post, directory)
    source = read(directory / f"{stem}.json") or {}
    for field in CREDIT:
        if field in source:
            post[field] = source[field]
        else:
            post.pop(field, None)
    words = post["term"] if name == "glossary" else post["hook"]
    prefix = "glossary-" if name == "glossary" else ""
    path = directory / f"{today.isoformat()}-{prefix}{slug(words)}.json"
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
