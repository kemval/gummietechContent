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

Two requests per post — a translation, then a proofread of it against the
English — rather than score.py's batching: a post is five short fields, and
a day's drafting is one post, so this costs two calls against a daily cap in
the hundreds. Batching would buy nothing and add a slug-to-post
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

# Posts a person rewrote by hand in the Spanish this archive wants. Rules
# describe the register; these show it, and a model imitates an example far
# more reliably than it follows an adjective. Optional: without the file the
# prompts carry no examples and everything else works as before.
EXAMPLES_PATH = REPO_ROOT / "docs" / "es_examples.json"

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

# Rules both passes share. Each named example is a real failure from posts/
# (2026-09-07 to 09-28), written with openai/gpt-oss-20b on Groq.
RULES = """\
- Neutral Latin American Spanish, no regionalisms, no "vosotros". Where the \
text addresses the reader, it is "tú" — the voice of a science account \
talking to its followers, not a press release and not a textbook.
- Write it the way a Spanish-speaking science writer would, starting from the \
facts, not from the English sentences. Reorder, join or split sentences \
wherever natural Spanish wants it. Read each sentence back: if a Spanish \
reader would have to guess what it means, or would never write it that way, \
rewrite it.
- No chains of impersonal "se" ("Se pidió una ejecución… Se obtuvo una…"): \
give the sentence a subject, or address the reader.
- The English is slide copy and often telegraphic — no articles, no verb \
("4B Qwen model, tuned with agentic RL, wrote…", "Three participants \
implanted"). The Spanish is full sentences: put the articles and verbs back.
- "solo" never takes an accent. A model size stays as written: "4B", not \
"4 B".
- Keep every claim exactly as strong as the English. Do not add, drop, soften \
or sharpen anything, and keep who does what to whom: "asked … and told to \
answer only if it knew" is "cuando se le pidió … y que respondiera solo si lo \
sabía", not "decir que solo responderá si lo sabía". "the_catch" is the \
credibility line — a hedge that moves is a factual error.
- Grammar has to be correct: gender and number agreement ("el Consejo de la \
Cuenca", "arte rupestre descolorido", "la detección cuántica"), and ranges \
as "del 8 % al 60 %".
- Translate every ordinary word. An English word left inside a Spanish \
sentence reads as a mistake: "bullfrog" is "rana toro", "manta ray" is \
"mantarraya", "lattice" is "red" or "celosía", "sloshing" is "chapoteo" or \
"oscilación". Keep in English only what has no Spanish form in use: \
proper nouns, institutions, journal names, named benchmarks, datasets, \
software and models (the "Join Order Benchmark" stays as it is), and \
established loanwords such as "benchmark", "prompt", "software".
- A multiplier is a comparison, not a count: "100-fold tests" is "pruebas \
100 veces más precisas" (or whatever the English compares), never \
"pruebas de 100 veces". "1.81x faster" is "1,81 veces más rápido".
- Keep every number and unit, with a decimal comma: "1.81" is "1,81", \
"0.05 M☉" is "0,05 M☉". Thousands take a space, not a comma or a point: \
"60,000" is "60 000".
- Scientific terms take their established Spanish form. If you are not \
certain of the accepted term, keep the English word rather than coin a \
Spanish-looking one: a reader can look up an English term, but a word that \
does not exist tells them nothing and discredits the rest. "semi-crystalline" \
is "semicristalino" — it came back once as "semicuadráticos", which means \
"semi-quadratic" and is not a word. An acronym keeps its English letters \
but gets its Spanish name the first time if a reader would not know it.
- This is a web page, not a slide: take the words natural Spanish needs, \
usually a little longer than the English. Never compress a sentence into \
telegraphic or broken Spanish to save space ("Nueve de diez revisados \
populares" came from that).
- "domain" is a 2-3 word field label. Translate it as well — it is shown to \
the reader — lowercase unless it contains a proper noun.
- A field whose English value is a LIST comes back as a list of the same \
length, in the same order, one translated string per entry. Each entry is its \
own paragraph; do not merge, split or reorder them."""

PROMPT = """Write this @gummietech post in neutral Latin American Spanish \
for the account's web archive — the same facts, as a Spanish-speaking \
science writer would put them.

Return ONLY a JSON object, no prose and no code fences, with exactly these \
keys: {keys}.

Rules:
{rules}
{examples}
Post:
{post}"""

# A second call that reads the draft against the English. The first pass
# gets most of it right and leaves a few sentences per post that do not say
# what the English says or are not Spanish; a translator asked to proofread
# its own output as a separate task catches most of those, for one more call
# per post against a daily cap in the hundreds.
REVIEW_PROMPT = """You are proofreading a machine translation of a \
@gummietech post, English into neutral Latin American Spanish, before it \
goes on a public web page.

For every field, compare the Spanish with the English and fix:
- anything whose meaning differs from the English — added, dropped, \
softened, sharpened, or with the roles swapped;
- grammar: agreement, prepositions, verb tense, word order;
- English words left untranslated that have a Spanish form in common use;
- words that do not exist in Spanish;
- any sentence a native Spanish-speaking science writer would not have \
written that way — literal, stiff, telegraphic or passive. Rewrite it as \
they would, without changing what it says. Correct grammar is not enough: \
it has to read as if it had been written in Spanish.
If a field already reads that way, return it unchanged.

Return ONLY a JSON object, no prose and no code fences, with exactly these \
keys: {keys}.

The translation had to follow these rules; the corrected version must too:
{rules}
{examples}
English:
{post}

Spanish to correct:
{draft}"""


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


def unusable(es: object, source: dict) -> str:
    """Why a parsed reply cannot go on the page, or "" when it can."""
    if not isinstance(es, dict):
        return f"it returned a JSON {type(es).__name__}, not an object"
    missing = [f for f in source if value(es, f) is None]
    if missing:
        return f"it left these empty: {', '.join(missing)}"
    # A list field has to come back the same length: each entry is a
    # paragraph, and a translation one short would silently drop one.
    for f in source:
        if isinstance(source[f], list):
            got = value(es, f)
            if not isinstance(got, list) or len(got) != len(source[f]):
                n = len(got) if isinstance(got, list) else "not a list"
                return (f"{f!r} has {len(source[f])} entries in English and "
                        f"came back with {n}; each one is a paragraph")
    return ""


def ask(prompt: str, source: dict, api_key: str, model: str) -> dict:
    """One call, retried once; refuse any reply the page cannot show.

    A malformed reply is the model's dice, not the input's fault: gpt-oss on
    Groq returned a JSON list despite response_format=json_object on
    2026-09-30, twice on the same post, and each time it ended the whole run
    with the posts after it untranslated. The same prompt came back fine on
    the next call, so one retry is the fix; a second failure still stops.
    """
    problem = ""
    for attempt in range(2):
        if attempt:
            print(f"  unusable reply ({problem}); asking once more")
            time.sleep(SLEEP_BETWEEN_CALLS)
        reply = llm.generate(prompt, api_key, model, temperature=0.2)
        try:
            es = json.loads(reply.strip())
        except json.JSONDecodeError:
            problem = f"it did not return JSON: {reply[:200]!r}"
            continue
        problem = unusable(es, source)
        if not problem:
            # Keys the page does not render are dropped rather than stored:
            # an unrendered translation is one nobody proofreads at the gate.
            return {f: value(es, f) for f in source}
    sys.exit(f"Refusing to write: {problem}. Re-run to try again.")


def examples(exclude: str) -> str:
    """The hand-written examples as a prompt section, or "" without them.

    `exclude` is the stem of the post being translated: re-translating one of
    the examples must not be handed its own answer, or it would copy it and
    the run would say nothing about how the prompt does.
    """
    try:
        pairs = json.loads(EXAMPLES_PATH.read_text())["examples"]
        shown_pairs = [(e["en"], e["es"]) for e in pairs
                       if e.get("post") != exclude]
    except FileNotFoundError:
        return ""
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
        print(f"  warning: ignoring {shown(EXAMPLES_PATH)} ({exc}); fix its "
              "JSON to get the examples back into the prompt.")
        return ""
    if not shown_pairs:
        return ""
    body = "\n\n".join(
        "English:\n" + json.dumps(en, indent=2, ensure_ascii=False)
        + "\nSpanish:\n" + json.dumps(es, indent=2, ensure_ascii=False)
        for en, es in shown_pairs)
    return ("\nPosts a native speaker wrote by hand for this archive. Match "
            "their voice and register, not their wording:\n\n" + body + "\n")


def translate(post: dict, stem: str, api_key: str, model: str) -> dict:
    """Translate, then have the draft proofread against the English."""
    source = source_fields(post)
    keys = ", ".join(f'"{f}"' for f in source)
    english = json.dumps(source, indent=2, ensure_ascii=False)
    shown_examples = examples(exclude=stem)

    draft = ask(PROMPT.format(keys=keys, rules=RULES, post=english,
                              examples=shown_examples),
                source, api_key, model)
    time.sleep(SLEEP_BETWEEN_CALLS)
    return ask(REVIEW_PROMPT.format(
                   keys=keys, rules=RULES, post=english,
                   examples=shown_examples,
                   draft=json.dumps(draft, indent=2, ensure_ascii=False)),
               source, api_key, model)


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
    es = translate(post, path.stem, api_key, model)
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
