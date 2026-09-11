#!/usr/bin/env python3
"""
Translate a post's page prose into Spanish for the web archive.

The archive carries a language toggle (templates/site_base.html); this is
where the Spanish it shows comes from. Reads a post JSON, asks the LLM for
the fields the page renders, and writes them back onto the same file as an
`es` block:

    "es": {
      "domain": "...", "hook": "...", "what_happened": "...",
      "why_it_matters": "...", "the_catch": "..."
    }

Usage:
    python src/translate.py                      # every post missing "es"
    python src/translate.py posts/2026-09-11-*.json
    python src/translate.py --force              # re-translate existing ones
    python src/translate.py --dry-run            # print, write nothing

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
import json
import sys
import time
from pathlib import Path

import llm                       # forwards to gemini or groq per LLM_PROVIDER
from render import ES_FIELDS, REPO_ROOT, shown

POSTS_DIR = REPO_ROOT / "posts"

# `domain` is optional in the JSON; the rest are what post.html always shows.
REQUIRED = tuple(f for f in ES_FIELDS if f != "domain")

SLEEP_BETWEEN_CALLS = 5          # seconds; the free tier allows ~12/minute

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
- Keep each field to roughly the English length. These render in a fixed \
layout, and a field that doubles overflows it.
- "domain" is a 2-3 word field label. Translate it as well — it is shown to \
the reader — lowercase unless it contains a proper noun.

Post:
{post}"""


def needs_translation(post: dict) -> bool:
    """True when the post has no usable `es` block. Mirrors site.py's
    check, from the writing side: a block missing a field is as unusable
    as no block at all."""
    es = post.get("es")
    if not isinstance(es, dict):
        return True
    return any(not str(es.get(f, "")).strip() for f in REQUIRED)


def translate(post: dict, api_key: str, model: str) -> dict:
    """Ask for the Spanish block and refuse anything the page cannot show."""
    fields = [f for f in ES_FIELDS if str(post.get(f, "")).strip()]
    source = {f: post[f] for f in fields}

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

    missing = [f for f in fields if not str(es.get(f, "")).strip()]
    if missing:
        sys.exit(f"Refusing to write. The model left these empty: "
                 f"{', '.join(missing)}. Re-run to try again.")

    # Keys the page does not render are dropped rather than stored: an
    # unrendered translation is one nobody proofreads at the gate.
    return {f: str(es[f]).strip() for f in fields}


def process(path: Path, api_key: str, model: str, force: bool,
            dry_run: bool) -> bool:
    """Translate one post. Returns True when a call was actually made."""
    try:
        post = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        print(f"  skipped {path.name}: not valid JSON ({exc})")
        return False

    missing = [f for f in REQUIRED if not str(post.get(f, "")).strip()]
    if missing:
        print(f"  skipped {path.name}: missing {', '.join(missing)}")
        return False

    if not force and not needs_translation(post):
        print(f"  skipped {path.name}: already translated (--force to redo)")
        return False

    print(f"\n{path.name}")
    es = translate(post, api_key, model)
    for field, text in es.items():
        print(f"  {field}: {text}")

    if dry_run:
        return True

    # `es` goes last so the English contract keeps the order draft.py wrote
    # and a diff shows the Spanish as an addition rather than a reshuffle.
    post.pop("es", None)
    post["es"] = es
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
    args = ap.parse_args()

    paths = args.posts or sorted(POSTS_DIR.glob("*.json"))
    if not paths:
        sys.exit(f"No post JSON in {POSTS_DIR}. Run `python src/draft.py` first.")

    missing = [p for p in paths if not p.is_file()]
    if missing:
        sys.exit("No such file: " + ", ".join(str(p) for p in missing))

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
