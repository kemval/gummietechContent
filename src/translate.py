#!/usr/bin/env python3
"""
Translate a post's page prose into Spanish for the web archive.

The archive carries a language toggle (templates/site_base.html); this is
where the Spanish it shows comes from. Reads a post JSON, asks the LLM for
the fields the page renders, and writes them back onto the same file as an
`es` block:

    "es": {
      "domain": "...", "hook": "...", "what_happened": "...",
      "why_it_matters": "...", "the_catch": "...",
      "_en": "<fingerprint of the English it was made from>"
    }

Usage:
    python src/translate.py                      # every post that needs it
    python src/translate.py posts/2026-09-11-*.json
    python src/translate.py --force              # re-translate existing ones
    python src/translate.py --dry-run            # print, write nothing
    python src/translate.py --check             # what is stale; no LLM call

Environment: same as draft.py (LLM_PROVIDER, GEMINI_API_KEY / GROQ_API_KEY).

Only the fields a reader sees, and nothing else. `caption` and `hashtags`
belong to Instagram, which posts in English; `alt_text` and the page's meta
description stay English because one language has to win for crawlers and
link previews. A translated field nobody renders is a field nobody proofs.

One request per post, rather than score.py's batching: a post is five short
fields, and a day's drafting is one post, so this costs one call against a
daily cap in the hundreds. Batching would buy nothing and add a slug-to-post
mapping the model can silently get wrong.

The Spanish is machine-written and lands on a public permalink, so it goes
through the same human gate as everything else: run this BEFORE adding
`published_at`, and read what it prints. site.py renders `es` only on posts
that already have that date, so an untranslated or unreviewed block cannot
reach the site on its own.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

import llm                       # forwards to gemini or groq per LLM_PROVIDER
from formats import es_fields, pieces, sections
from render import REPO_ROOT, shown

POSTS_DIR = REPO_ROOT / "posts"

SLEEP_BETWEEN_CALLS = 5          # seconds; the free tier allows ~12/minute

# The `es` block records a fingerprint of the English it was made from, under
# a key that is not a renderable field — site.py's `spanish()` copies only the
# fields the page shows, so this never reaches a template.
#
# Without it nothing relates a translation to its source. The gate exists to
# change the English: a fact-check finds a wrong number, a person fixes the
# slide, and the Spanish underneath still says the old thing. Re-running this
# file would skip that post as "already translated", so the only thing between
# stale Spanish and a permalink was somebody remembering to pass --force.
SOURCE_KEY = "_en"

PROMPT = """Translate this @gummietech post into neutral Latin American \
Spanish for the account's web archive.

Return ONLY a JSON object, no prose and no code fences, with exactly these \
keys: {keys}.

Rules:
- Neutral Latin American Spanish: no regionalisms, no "vosotros", usted-free \
impersonal phrasing.
- Translate the meaning, not the words. The English is plain and declarative; \
the Spanish has to read as if it had been written that way, not as a \
translation of something.
- Keep every claim exactly as strong as the English. Do not add, drop, soften \
or sharpen anything. "the_catch" is the credibility line — a hedge that moves \
is a factual error.
- Leave proper nouns, institutions, journal names, units and numbers exactly \
as they are.
- Scientific terms take their established Spanish form. If you are not \
certain of the accepted term, keep the English word rather than coin a \
Spanish-looking one: a reader can look up an English term, but a word that \
does not exist tells them nothing and discredits the rest. "semi-crystalline" \
is "semicristalino" — it came back once as "semicuadráticos", which means \
"semi-quadratic" and is not a word.
- Keep each field to roughly the English length. These render in a fixed \
layout, and a field that doubles overflows it.
- "domain" is a 2-3 word field label. Translate it as well — it is shown to \
the reader — lowercase unless it contains a proper noun.
- A field whose English value is a LIST comes back as a list of the same \
length, in the same order, one translated string per entry. Each entry is its \
own slide; do not merge, split or reorder them.

Post:
{post}"""


def value(post: dict, field: str) -> str | list[str] | None:
    """A field's translatable content: a string, a list of them, or None.

    A Breakdown's `mechanism` is a list with one slide per step, so both
    shapes have to survive being fingerprinted, sent and checked.
    """
    raw = post.get(field)
    if isinstance(raw, list):
        return [str(v).strip() for v in raw if str(v).strip()] or None
    return str(raw or "").strip() or None


def required(post: dict) -> tuple[str, ...]:
    """The fields this post's Spanish must carry to be usable.

    `domain` is optional in the JSON, so a post without one is not missing a
    translation; everything else on the page is required, because a block
    short of a field is dropped whole.
    """
    return tuple(f for f in es_fields(post) if f != "domain")


def source_fields(post: dict) -> dict:
    """The English a translation is made from: the fields this post's format
    puts on the page, minus the ones it leaves empty.

    A section whose entries are objects — a Signal's items — contributes only
    its prose. The source, the URL and the peer-review flag beside it are not
    translated: a journal name and a DOI are the same in both languages, and
    a translated one would be wrong.
    """
    out: dict = {}
    for field in ("domain", "hook"):
        if (v := value(post, field)) is not None:
            out[field] = v
    for section in sections(post):
        prose = pieces(post, section)
        if prose:
            out[section.field] = prose if section.many else prose[0]
    return out


def fingerprint(post: dict) -> str:
    """A stable hash of that English. Truncated because it is read by eye in
    a diff, and a collision here costs a re-translation, not a wrong page."""
    blob = json.dumps(source_fields(post), sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def stale_reason(post: dict) -> str:
    """Why this post needs translating, or "" when it does not.

    The first two checks mirror site.py's, from the writing side: a block
    missing a field is as unusable as no block at all. The third is the one
    site.py cannot make — a complete block whose English has moved on.
    """
    es = post.get("es")
    if not isinstance(es, dict):
        return "no Spanish yet"
    if any(value(es, f) is None for f in required(post)):
        return "the es block is incomplete"
    stamp = str(es.get(SOURCE_KEY, "")).strip()
    if stamp and stamp != fingerprint(post):
        return "the English changed after it was translated"
    # No stamp means it was translated before this file recorded one. That is
    # unknown, not stale: treating it as stale would re-translate every older
    # post on the next run, spend a day's calls, and overwrite Spanish a
    # person has already read at the gate.
    return ""


def unstamped(post: dict) -> bool:
    """Whether a complete `es` block carries no record of the English it came
    from.

    These were translated before this file stamped its work, so nothing can
    tell whether their Spanish still matches. stale_reason() deliberately
    leaves them alone, for the reason given there — but silence is not
    agreement, and a summary that counted them as up to date claimed a check
    that never ran. They are named instead, and clearing one is a --force
    re-translation, which writes the stamp.
    """
    es = post.get("es")
    return (isinstance(es, dict)
            and all(value(es, f) is not None for f in required(post))
            and not str(es.get(SOURCE_KEY, "")).strip())


def check(paths: list[Path]) -> int:
    """Report what needs translating, without calling the model.

    The half that does not depend on somebody reading a report: CI runs this
    on every push, so a post whose English was corrected at the gate turns
    the build red instead of quietly keeping Spanish that says the old thing.
    Needs no API key, which is why it returns before main() asks for one.

    Only a post whose stamp still matches is reported as up to date. An
    unstamped one is neither stale nor verified, so it is counted apart: it
    does not fail the build, because nothing about it has changed and failing
    would make every push red until a day's calls were spent, but it is not
    folded into the number that says everything is fine either.
    """
    stale: list[Path] = []
    unverifiable: list[Path] = []
    verified = 0

    for path in paths:
        try:
            post = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError) as exc:
            print(f"  {path.name}: unreadable ({exc})")
            stale.append(path)
            continue
        english = [f for f in required(post) if value(post, f) is None]
        if english:
            # Not translatable at all, and not this file's problem to report:
            # render.py refuses the same record. Say so and move on.
            print(f"  {path.name}: missing {', '.join(english)} in English")
            continue
        reason = stale_reason(post)
        if reason:
            print(f"  {path.name}: {reason}")
            stale.append(path)
        elif unstamped(post):
            unverifiable.append(path)
        else:
            verified += 1

    if stale:
        print(f"\n{len(stale)} post{'s' * (len(stale) != 1)} to translate:\n"
              "  python src/translate.py " + " ".join(shown(p) for p in stale))
    else:
        print(f"All {verified} up to date.")

    if unverifiable:
        n = len(unverifiable)
        print(f"\n{n} post{'s' * (n != 1)} carr{'y' if n != 1 else 'ies'} "
              f"Spanish written before the {SOURCE_KEY} stamp existed, so "
              f"nothing can tell whether it still matches the English.\n"
              f"Re-translate and read what it prints to clear them:\n"
              "  python src/translate.py --force "
              + " ".join(shown(p) for p in unverifiable))

    return 1 if stale else 0


def translate(post: dict, api_key: str, model: str) -> dict:
    """Ask for the Spanish block and refuse anything the page cannot show."""
    source = source_fields(post)
    fields = list(source)

    reply = llm.generate(
        PROMPT.format(keys=", ".join(f'"{f}"' for f in fields),
                      post=json.dumps(source, indent=2, ensure_ascii=False)),
        api_key, model, temperature=0.2)

    try:
        es = json.loads(reply.strip())
    except json.JSONDecodeError:
        sys.exit(f"The model did not return JSON:\n{reply[:400]}\n"
                 "Re-run to try again.")
    if not isinstance(es, dict):
        sys.exit(f"The model returned {type(es).__name__}, not a JSON object. "
                 "Re-run to try again.")

    missing = [f for f in fields if value(es, f) is None]
    if missing:
        sys.exit(f"Refusing to write. The model left these empty: "
                 f"{', '.join(missing)}. Re-run to try again.")

    # A list field has to come back the same length: each entry is a slide,
    # and a translation one short would silently drop one.
    for f in fields:
        if isinstance(source[f], list):
            got = value(es, f)
            if not isinstance(got, list) or len(got) != len(source[f]):
                sys.exit(f"Refusing to write. {f!r} has {len(source[f])} "
                         f"entries in English and came back with "
                         f"{len(got) if isinstance(got, list) else 'not a list'}"
                         f". Each one is a slide. Re-run to try again.")

    # Keys the page does not render are dropped rather than stored: an
    # unrendered translation is one nobody proofreads at the gate.
    return {f: value(es, f) for f in fields}


def process(path: Path, api_key: str, model: str, force: bool,
            dry_run: bool) -> bool:
    """Translate one post. Returns True when a call was actually made."""
    try:
        post = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        print(f"  skipped {path.name}: not valid JSON ({exc})")
        return False

    # The same question check() asks, through the same helpers: a list field
    # is a list of slides, not a string, so `str(post.get(f))` would call a
    # Breakdown's populated `mechanism` present and an empty one present too.
    # This read the module-level REQUIRED that moved into formats.py as
    # required(), and raised NameError on the first post of every run for as
    # long as it did — --check has its own copy of the loop and stayed green.
    missing = [f for f in required(post) if value(post, f) is None]
    if missing:
        print(f"  skipped {path.name}: missing {', '.join(missing)} in English")
        return False

    reason = stale_reason(post)
    if not force and not reason:
        print(f"  skipped {path.name}: already translated (--force to redo)")
        return False

    again = isinstance(post.get("es"), dict) and reason
    print(f"\n{path.name}" + (f" — re-translating: {reason}" if again else ""))
    es = translate(post, api_key, model)
    for field, text in es.items():
        print(f"  {field}: {text}")

    if dry_run:
        return True

    # `es` goes last so the English contract keeps the order draft.py wrote
    # and a diff shows the Spanish as an addition rather than a reshuffle.
    # The fingerprint goes in last, and is of the English as it stands right
    # now — the text that was actually sent to the model above.
    post.pop("es", None)
    post["es"] = {**es, SOURCE_KEY: fingerprint(post)}
    path.write_text(json.dumps(post, indent=2, ensure_ascii=False) + "\n")
    print(f"  wrote {shown(path)}")
    return True


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Translate post prose into Spanish for the web archive.")
    ap.add_argument("posts", nargs="*", type=Path,
                    help="post JSON files (default: all of posts/)")
    ap.add_argument("--force", action="store_true",
                    help="re-translate posts that already have an es block")
    ap.add_argument("--dry-run", action="store_true",
                    help="print the Spanish without writing it back")
    ap.add_argument("--check", action="store_true",
                    help="report posts that need translating and exit 1, "
                         "making no LLM call (what CI runs)")
    args = ap.parse_args()

    paths = args.posts or sorted(POSTS_DIR.glob("*.json"))
    if not paths:
        sys.exit(f"No post JSON in {POSTS_DIR}. Run `python src/draft.py` first.")

    missing = [p for p in paths if not p.is_file()]
    if missing:
        sys.exit("No such file: " + ", ".join(str(p) for p in missing))

    if args.check:
        print(f"Checking {len(paths)} post{'s' * (len(paths) != 1)}")
        return check(paths)

    api_key, model = llm.config()
    print(f"Translating {len(paths)} post{'s' * (len(paths) != 1)} → Spanish")

    called = 0
    for path in paths:
        if called and SLEEP_BETWEEN_CALLS:
            time.sleep(SLEEP_BETWEEN_CALLS)
        called += process(path, api_key, model, args.force, args.dry_run)

    print(f"\nDone. {called} translated, {len(paths) - called} skipped.")
    if called and args.dry_run:
        print("Dry run — nothing written.")
    elif called:
        print("Read the Spanish above before it goes live: it is machine "
              "written, and the archive is a permalink.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
