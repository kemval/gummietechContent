#!/usr/bin/env python3
"""
What each carousel format is made of, and nothing else.

Its own module for the reason llm_errors.py is: every layer needs this
answer and one of them cannot pay for it. telegram.py runs on publish.yml's
poll, the most frequent workflow here,
under `requests` and `python-dotenv` alone and must never import render.py,
which pulls in Jinja and Playwright at module load — so the table cannot
live there, and a second copy in telegram.py would be a second place for the
formats to drift.

Standard library only, on purpose. Importing this costs nothing.
"""

from __future__ import annotations

from typing import NamedTuple


# Required of most formats. attribution is a legal and reputational
# requirement, not a nicety; alt_text is the only thing a screen-reader user
# gets. A Signal moves the first three onto each of its five entries, because
# a roundup has five sources and not one — see FORMATS.
RECORD = ("hook", "attribution", "alt_text", "source_url", "peer_reviewed")


class Section(NamedTuple):
    """One body field of a carousel, and what to call it.

    `en`/`es` are the labels the web archive prints. The slide templates carry
    their own copy of these words because there they are typeset display,
    sized and positioned per format — "The catch" on a Drop is "The limits" on
    a Breakdown for the same field. The archive is prose and asks here.

    `pair` marks a list whose every piece is "Term: line" (PAIR), split at
    the first separator where it is laid out.

    `many` marks a field holding one entry per slide. `key` marks one whose
    entries are objects rather than strings, and names the one that is prose:
    a Signal's items each carry a claim, a source and a peer-review flag, and
    only the claim is translated or measured.
    """
    field: str
    en: str
    es: str
    many: bool = False
    optional: bool = False
    key: str = ""
    pair: bool = False


# The separator in a `pair` piece. A colon and a space, because a term can
# hold a colon of its own only with no space after it ("p:value" is not one).
PAIR = ": "


def unpaired(post: dict) -> list[str]:
    """Which `pair` pieces have no "Term: line" split, as 'items[3]'.

    Refused rather than guessed at: a piece with no separator would lay out
    as a term with no definition, and a wrong split would set half a
    sentence as the term.
    """
    out = []
    for section in sections(post):
        if section.pair:
            for n, piece in enumerate(pieces(post, section), start=1):
                term, sep, line = piece.partition(PAIR)
                if not (sep and term.strip() and line.strip()):
                    out.append(f"{section.field}[{n}]")
    return out


class Format(NamedTuple):
    """A carousel format, whole.

    `record` is what the post itself must carry; `entries` is what each object
    inside a `key` section must carry. `catch` says whether the format has a
    slide that drops to --ink — the dark slide *is* the catch, so a format
    with no single caveat has none. `by_hand` says draft.py does not write
    it — a person does, or for a term or a Breakdown weekly.yml — so it is
    never a Drop day's Drop, and "Another story" cannot draft another in its
    place.
    """
    template: str
    sections: tuple[Section, ...]
    record: tuple[str, ...] = RECORD
    entries: tuple[str, ...] = ()
    catch: bool = True
    by_hand: bool = False


# What each carousel format is made of, in the order a reader meets it.
#
# One table, because six places need the answer and none of them should be
# asking `if post_type ==`: render.py refuses a record missing a field,
# proof.py measures the word budget and the preprint flags, translate.py
# knows what to translate, site.py what to print, telegram.py what to show at
# the gate, and the slide template what to lay out.
#
# A Breakdown shares `why_it_matters` and `the_catch` with a Drop rather than
# inventing synonyms: the job of those two slides is identical and docs §1
# calls them the account's entire competitive advantage in both formats. What
# it adds is the question, the intuition and the mechanism; what it drops is
# `what_happened`, because a Breakdown explains rather than reports.
#
# A Signal is the one that does not fit that shape at all. It is five items
# with five sources, so `attribution`, `source_url` and `peer_reviewed` are
# properties of an entry rather than of the post — §7.3 makes credit
# mandatory and §7.2 makes the preprint label mandatory, and both are per
# item or they are wrong. It also has no catch: the dark slide is where a
# post's caveat goes, and a roundup has five of them or none.
FORMATS: dict[str, Format] = {
    "drop": Format("drop.html", (
        Section("what_happened",  "What happened",  "Qué pasó"),
        Section("why_it_matters", "Why it matters", "Por qué importa"),
        Section("the_catch",      "The catch",      "El detalle"),
    )),
    "breakdown": Format("breakdown.html", (
        Section("the_question",   "The question",   "La pregunta"),
        Section("the_intuition",  "The intuition",  "La intuición"),
        Section("mechanism",      "The mechanism",  "El mecanismo", many=True),
        Section("why_it_matters", "Why it matters", "Por qué importa"),
        Section("the_catch",      "The limits",     "Los límites"),
        # Off by default: the hook is already the one-line summary, and a
        # recap is one more synthesised sentence for fact-check to verify.
        # Kept because it is a JSON field, not an architecture decision —
        # learn.py can settle whether it earns its slide.
        Section("recap",          "In one line",    "En una línea",
                optional=True),
    ), by_hand=True),
    "signal": Format(
        "signal.html",
        (Section("items", "This week", "Esta semana", many=True, key="claim"),),
        record=("hook", "alt_text", "items"),
        entries=("claim", "attribution", "source_url", "peer_reviewed"),
        catch=False,
    ),
    # The glossary: one term, defined, then shown in a post this account
    # already published. `example_post` names that post's stem, and
    # render.load_post() refuses one that is not in posts/ with a
    # published_at — the example is ours or it is not an example. Its credit
    # is read from that post, never retyped here. The catch is the common
    # misuse of the word.
    "term": Format(
        "term.html",
        (Section("term",       "Term",               "Término"),
         Section("definition", "What it means",      "Qué significa"),
         Section("example",    "Where we saw it",    "Dónde lo vimos"),
         Section("the_catch",  "The common mistake", "El error común")),
        record=(*RECORD, "example_post"),
        by_hand=True,
    ),
    # The cheat sheet: several terms, one line each, from one source. Each
    # entry is one string, "Term: line" — `pair` — rather than an object, so
    # the term travels with its line through translation, the archive and
    # the gate, which read prose as strings; a Signal's `key` would carry
    # only one of the two. The credit is the post's: the entries are lines
    # from one source, not sources. A reference has no single caveat, so no
    # catch either.
    "sheet": Format(
        "sheet.html",
        (Section("items", "The sheet", "La chuleta", many=True, pair=True),),
        catch=False,
        by_hand=True,
    ),
    # A Drop whose paper ships its code, with one slide on running it. The
    # repo is required, and it is code_link()'s, never the model's: a run
    # post pointing at an invented repo is the worst wrong credit there is.
    "run": Format("run.html", (
        Section("what_happened",  "What happened",    "Qué pasó"),
        Section("try_it",         "Run it yourself",  "Córrelo tú"),
        Section("why_it_matters", "Why it matters",   "Por qué importa"),
        Section("the_catch",      "The catch",        "El detalle"),
    ), record=(*RECORD, "code_url")),
}
DEFAULT_FORMAT = "drop"


def format_name(post_type: str | None) -> str:
    """Which entry of FORMATS a post belongs to.

    An unknown type falls back with a warning rather than exiting, for the
    same reason an unknown colorway does: the draft cost an LLM call, and a
    Drop of it is still a post a person can judge at the gate.

    post_type comes from the model, and this is the only thing that turns it
    into a template path — a lookup in a table this file owns, never a
    filename built from the string.
    """
    name = str(post_type or "").strip().lower()
    if name in FORMATS:
        return name
    if name:
        print(f"  warning: unknown post_type {name!r} — rendering as a "
              f"{DEFAULT_FORMAT}. Valid: {', '.join(FORMATS)}")
    return DEFAULT_FORMAT


def by_hand(post: dict) -> bool:
    """Whether this post is outside draft.py, so it is no day's Drop.

    A hand-written post is dated the day it was written and can share a Drop
    day's date without being its Drop: on 2026-09-28 a Breakdown did, and
    daily.yml's gate reported the Drop as drafted, so none was. The gate,
    watch.owes() and draft.reject() all ask this.
    """
    return spec(post).by_hand


def spec(post: dict) -> Format:
    """The whole format record for this post."""
    return FORMATS[format_name(post.get("post_type"))]


def template_for(post_type: str | None) -> str:
    """The template file a post renders with."""
    return FORMATS[format_name(post_type)].template


def sections(post: dict) -> tuple[Section, ...]:
    """The body fields of this post, in reading order, skipping the optional
    ones it does not carry."""
    return tuple(s for s in spec(post).sections
                 if not s.optional or post.get(s.field))


def required(post: dict) -> list[str]:
    """Every field this post must have to be renderable."""
    return [*spec(post).record,
            *(s.field for s in sections(post) if not s.optional)]


def entries(post: dict) -> list[dict]:
    """The objects inside this post's `key` section, if it has one."""
    for section in sections(post):
        if section.key:
            return [e for e in post.get(section.field) or []
                    if isinstance(e, dict)]
    return []


def missing_from_entries(post: dict) -> list[str]:
    """Which entry is short of which field, as 'items[2]: source_url'.

    Per entry rather than per record, because a Signal's credit and preprint
    label belong to the item they describe. §7.2 and §7.3 are not satisfied
    by one of five items carrying them.
    """
    wanted = spec(post).entries
    if not wanted:
        return []
    out = []
    for n, entry in enumerate(entries(post), start=1):
        for field in wanted:
            value = entry.get(field)
            absent = (value is None if field == "peer_reviewed"
                      else not str(value or "").strip())
            if absent:
                out.append(f"items[{n}]: {field}")
    return out


def body_text(record: dict, field: str, key: str = "") -> list[str]:
    """A field's prose as a list of pieces: one per slide for a list field
    like a Breakdown's `mechanism`, one in total for the rest.

    `key` pulls the prose out of a list of objects — a Signal's items carry a
    source and a flag alongside the claim, and only the claim is prose.

    Takes a field name rather than a Section so it also reads an `es` block,
    which carries the same fields as plain strings and knows nothing about
    the table.
    """
    raw = record.get(field)
    if isinstance(raw, list):
        out = []
        for value in raw:
            text = value.get(key, "") if key and isinstance(value, dict) else value
            if str(text or "").strip():
                out.append(str(text).strip())
        return out
    return [str(raw).strip()] if str(raw or "").strip() else []


def pieces(record: dict, section: Section) -> list[str]:
    """A section's prose from a post record, honouring its `key`."""
    return body_text(record, section.field, section.key)


def post_preprint_flag(post: dict) -> bool:
    """Whether the post itself carries one "not yet peer-reviewed" label.

    False for a Signal whatever its items say, because a Signal has no
    post-level `peer_reviewed` at all — `record` moved it onto the entries,
    and `post.get("peer_reviewed", False)` on a record that never had the
    field reads as an unreviewed post. render.py handed that straight to the
    templates, so every Signal set the global flag and announced "preprint
    flag ON (peer_reviewed is false)" at the gate about five peer-reviewed
    papers. Only signal.html ignoring the variable kept it off the slides.
    """
    return not spec(post).entries and not post.get("peer_reviewed", False)


def preprint_claims(post: dict) -> int:
    """How many slides must carry a "not yet peer-reviewed" label.

    One per unreviewed source, which is one per post for every format but the
    Signal and one per item for that. §7.2 is not a per-post rule; it is a
    per-claim one, and a roundup makes the difference visible.
    """
    if spec(post).entries:
        return sum(1 for e in entries(post) if e.get("peer_reviewed") is False)
    return int(post_preprint_flag(post))


def es_fields(post: dict) -> tuple[str, ...]:
    """The fields the web archive shows in Spanish, for this post's format."""
    return ("domain", "hook", *(s.field for s in sections(post)))
