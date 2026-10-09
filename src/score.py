#!/usr/bin/env python3
"""
Layer 2: score the sheet's new items with the LLM and rank them for the queue.

Reads every row with status "new", scores it 1-10 on the four axes from
docs/gummietech_content_system.md §Layer 2, and writes back a score, a
status and a one-line reason.

    novelty      genuinely new, or a rehash?
    visual       is there an image, diagram or video to build slides from?
    explain      can a smart non-expert get it in 5 slides?
    surprise     does it violate an intuition? (the share driver)

and separately on relevance — would someone who uses technology want to
know it today? — which lifts an item at LIFT_AT or above (see overall()).

It also names the item's `beat` — ai, software, automation, robotics,
computing or science — in the same call, so it costs no quota. draft.py
reads it to put the account's priority subjects first (see PRIORITY_BEATS
there); the score itself stays topic-blind.

The overall score is the mean of the four axes, or the relevance that
lifted it. Items at or above THRESHOLD become "queued"; the rest become
"rejected" and stay in the sheet as a record of what was considered.

Usage:
    python src/score.py
    python src/score.py --limit 40          # score at most 40 items
    python src/score.py --dry-run           # score and print, write nothing
    python src/score.py --beats             # name the beat of queued rows
                                            # scored before beats existed
    python src/score.py --beats --again     # re-name every queued row's beat
                                            # after BEAT_RULE changes

Environment (.env locally, repo secrets in CI):
    LLM_PROVIDER                 'gemini' (default) or 'groq' — see llm.py
    GEMINI_API_KEY               free-tier key from aistudio.google.com/apikey
    GEMINI_MODEL                 optional; see gemini.DEFAULT_MODEL
    GROQ_API_KEY                 free-tier key from console.groq.com/keys
    GROQ_MODEL                   optional; see groq_llm.DEFAULT_MODEL
    GOOGLE_SHEET_ID              spreadsheet key
    GOOGLE_SHEETS_CREDENTIALS    path to the service account JSON

Items go up in batches of BATCH_SIZE with a sleep between calls, to stay
inside the free tier's per-minute limit. The provider module (gemini.py or
groq_llm.py) owns what happens when a request is throttled or the model is
overloaded; llm.py picks which one from LLM_PROVIDER.
"""

from __future__ import annotations

import argparse
import json
import sys
import time

import llm                       # forwards per LLM_PROVIDER, failing over (llm.py)
from ingest import COLUMNS, check_unmoved, open_sheet

# 15-20 items per request. One request per item would exhaust the daily cap
# in an afternoon; this keeps a full day's ingest inside 20-30 calls.
BATCH_SIZE = 18
SLEEP_BETWEEN_CALLS = 5          # seconds; ~12 requests/minute

AXES = ["novelty", "visual", "explain", "surprise"]

# Relevance is scored in the same call but is not an axis: it can lift an
# item, never sink one. A launch people will use is news whatever its
# novelty or visual axes say, so at LIFT_AT or above its relevance is its
# score; below, the mean of AXES stands. Measured 2026-10-07 on Groq before
# settling on this: relevance as a fifth averaged axis, and in place of
# `visual`, both cut the queue from 14-19 to 1-2 of 60 rows (the model gives
# nearly everything 4-7) while moving almost no launch across THRESHOLD. See
# docs/decisions/voice-and-selection.md.
RELEVANCE = "relevance"
LIFT_AT = 8

# What an item is about. Anything else the model says is stored as blank
# rather than trusted into a column draft.py selects on.
BEATS = ("ai", "software", "automation", "robotics", "computing", "science")

# docs/gummietech_content_system.md: "Only items scoring >= 7 total surface
# in the morning queue."
THRESHOLD = 7.0

# The one definition of a beat, shared by both prompts. The subject rule is
# a post-mortem: on 2026-09-28 "Show HN: What if the speed of light was
# 5 km/h?" — a relativity simulation — was named `ai` from its headline, and
# pick_row() drafted physics as the day's tech post. A demo, an app or a
# "Show HN" about a science topic is that topic; the medium is not the beat.
BEAT_RULE = """Exactly one of: ai (machine learning, models, agents), software \
(programming, languages, tools, infrastructure), automation, robotics, \
computing (building computers: chips, processors, quantum computers and \
qubits, security), science (everything else). The beat is what the item is \
about, not what it is made with or where it was posted: a simulation, app, \
demo or "Show HN" about physics, biology or space is science. Physics that is \
not about building a computer is science even when it says "quantum" \
(particles, entanglement, materials, stars). A trade's tools and materials \
(metalworking, construction, manufacturing) are not software. Name ai only \
when machine learning is the subject."""

PROMPT = """You are the editorial filter for @gummietech, an Instagram account \
that explains science, technology and engineering to a smart non-expert audience.

Score each item below from 1 to 10 on four axes:

- novelty: genuinely new work, or a rehash of something already everywhere?
- visual: is there a real image, diagram, dataset or physical object to build \
five slides from? A diagram of how a system works, a benchmark chart, or a \
before/after of what a model or program produces counts: software is not \
text-only by default. Text-only policy news scores low.
- explain: can a smart non-expert understand the point in five slides?
- surprise: does it violate an intuition? This is what makes people share.

Then score relevance from 1 to 10, separately: would a curious person who \
uses technology want to know this today?
- 9-10: a launch or change that many people will use or hear about this \
week — a major AI model, a feature in a product millions use, a change to a \
browser, phone or operating system.
- 7-8: a release developers or enthusiasts will try or talk about.
- 4-6: interesting, but only to one field.
- 1-3: customer stories ("how X uses our product"), partnerships, \
marketing, policy positions, and anything in the list below.

A launch of a model, product feature or tool that people can use is news: \
score it on what it can do, as long as the item states a concrete \
capability. A release that publishes how it works — a technical report, a \
paper, a method or an architecture — scores on what it shows.

Score 3 or below on every axis and on relevance for: funding rounds and \
acquisitions, hiring, firings and personnel news, lawsuits and company \
drama, opinion pieces and editorials, listicles, awards, conference \
announcements, customer stories, and stories or announcements that name no \
specific finding, mechanism or concrete capability (marketing).

Also name each item's beat. {beats}

Return ONLY a JSON object with a "results" array, one entry per item, no \
prose and no code fences:
{{"results": [{{"i": <item number>, "novelty": <1-10>, "visual": <1-10>, \
"explain": <1-10>, "surprise": <1-10>, "relevance": <1-10>, \
"beat": "<one beat>", \
"why": "<at most 12 words>"}}]}}

Items:
{items}"""


# Naming a beat is far lighter than scoring four axes, so the backfill sends
# many rows to a call. Not headlines alone and not 100 at a time: on
# 2026-09-28 that put Z-boson entanglement under `computing`, and on
# 2026-10-02 daily drafted it as the day's "tech" story.
BEATS_BATCH = 40
BEATS_SUMMARY_CHARS = 200

BEATS_PROMPT = """Name the beat of each item below. {beats}

Return ONLY a JSON object, no prose and no code fences:
{{"results": [{{"i": <item number>, "beat": "<one beat>"}}]}}

Items:
{items}"""


def build_items_block(batch: list[dict]) -> str:
    lines = []
    for item in batch:
        lines.append(
            f"{item['i']}. [{item['source']}] {item['title']}\n"
            f"   {item['summary'][:400]}"
        )
    return "\n\n".join(lines)


def parse_scores(text: str) -> list[dict]:
    """Pull the JSON array out of the model's reply."""
    text = (text or "").strip()
    if not text:
        return []
    if text.startswith("```"):                    # belt and braces: the mime
        text = text.strip("`")                    # type should prevent fences
        text = text.split("\n", 1)[-1] if text.lower().startswith("json") else text

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        print(f"  warning: response was not JSON, skipping batch: {text[:120]}")
        return []

    if isinstance(data, list):
        return data
    if isinstance(data, dict) and isinstance(data.get("results"), list):
        return data["results"]
    return []


def overall(scores: dict) -> float:
    """The mean of AXES, or the item's relevance when that is LIFT_AT or more.

    A lift, never a drag: a science result keeps the score it always had,
    and a launch people will use is not held under THRESHOLD by axes that
    were written for findings.
    """
    mean = round(sum(float(scores.get(axis, 0)) for axis in AXES) / len(AXES), 2)
    try:
        # Clamped: the scale is 1-10, and a model that answers 15 must not
        # outrank every finding in the queue.
        relevance = min(float(scores.get(RELEVANCE, 0)), 10.0)
    except (TypeError, ValueError):
        relevance = 0.0
    return max(mean, relevance) if relevance >= LIFT_AT else mean


def beat_of(result: dict) -> str:
    """The item's beat, or blank when the model said something off the list."""
    beat = str(result.get("beat", "")).strip().lower()
    return beat if beat in BEATS else ""


def backfill_beats(worksheet, rows: list[list[str]], col: dict,
                   api_key: str, model: str, dry_run: bool,
                   again: bool = False) -> int:
    """Name the beat of every queued row that has none — or, with `again`,
    of every queued row, overwriting what an older BEAT_RULE named.

    Rows scored before score.py named a beat would otherwise fall back to
    their feed's topic in draft.py, and a feed is not a subject: on
    2026-09-27 that fallback put a battery, a solar cell and a cookie made
    of plastic among the five "tech" rows it would draft first.

    `again` exists because a fixed prompt only reaches rows scored after it.
    On 2026-09-28 the next priority rows were metalworking under `software`
    and a dead star under `computing`, named before BEAT_RULE said the beat
    is the subject. A model answer off the list leaves the old beat alone.
    """
    pending = [(n, row) for n, row in enumerate(rows[1:], start=2)
               if row[col["status"]] == "queued"
               and (again
                    or not (row[col["beat"]] if col["beat"] < len(row) else ""))]
    print(f"Naming the beat of {len(pending)} queued rows, "
          f"{BEATS_BATCH} to a call")
    named = 0
    for start in range(0, len(pending), BEATS_BATCH):
        batch = pending[start:start + BEATS_BATCH]
        block = "\n".join(
            f"{i}. [{row[col['source']]}] {row[col['title']]}\n"
            f"   {row[col['summary']][:BEATS_SUMMARY_CHARS]}"
            for i, (_, row) in enumerate(batch, start=1))
        prompt = BEATS_PROMPT.format(beats=BEAT_RULE, items=block)
        results = parse_scores(llm.generate(prompt, api_key, model))
        by_index = {int(r["i"]): r for r in results if "i" in r}
        letter = chr(65 + col["beat"])
        updates = []
        for i, (n, _) in enumerate(batch, start=1):
            beat = beat_of(by_index.get(i, {}))
            if beat:
                updates.append({"range": f"{letter}{n}", "values": [[beat]]})
        named += len(updates)
        print(f"  {start + len(batch):>5}/{len(pending)}  named {len(updates)}")
        # Per batch, for score.py's reason: a daily cap hit halfway keeps
        # what was already paid for, and a re-run starts where this stopped.
        if updates and not dry_run:
            check_unmoved(worksheet,
                          {n: row[col["url"]] for n, row in batch}, col)
            worksheet.batch_update(updates, value_input_option="RAW")
        if start + BEATS_BATCH < len(pending):
            time.sleep(SLEEP_BETWEEN_CALLS)
    print(f"\nNamed {named} of {len(pending)}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, help="score at most this many items")
    ap.add_argument("--dry-run", action="store_true",
                    help="score and print without writing to the sheet")
    ap.add_argument("--beats", action="store_true",
                    help="name the beat of queued rows that have none, "
                         "instead of scoring")
    ap.add_argument("--again", action="store_true",
                    help="with --beats, re-name every queued row's beat, "
                         "not only the blank ones")
    args = ap.parse_args()

    api_key, model = llm.config()

    worksheet = open_sheet()
    rows = worksheet.get_all_values()             # one read for the whole sheet
    if not rows:
        sys.exit("The sheet is empty. Run `python src/ingest.py` first.")

    col = {name: rows[0].index(name) for name in COLUMNS if name in rows[0]}
    if args.beats:
        if "beat" not in col:
            sys.exit("The sheet has no `beat` column yet. Run "
                     "`python src/ingest.py` once — it rewrites the header.")
        return backfill_beats(worksheet, rows, col, api_key, model,
                              args.dry_run, again=args.again)
    pending = [
        {"row": n, "i": len(rows),                # placeholder, renumbered below
         "url": row[col["url"]],
         "title": row[col["title"]],
         "summary": row[col["summary"]],
         "source": row[col["source"]]}
        for n, row in enumerate(rows[1:], start=2)
        if row[col["status"]] == "new"
    ]
    if args.limit:
        pending = pending[:args.limit]

    if not pending:
        print("Nothing to score — no rows with status 'new'.")
        return 0

    print(f"Scoring {len(pending)} items with {model} "
          f"in batches of {BATCH_SIZE}")

    scored = queued = 0

    for start in range(0, len(pending), BATCH_SIZE):
        batch = pending[start:start + BATCH_SIZE]
        for n, item in enumerate(batch, start=1):
            item["i"] = n                          # numbering is per request

        results = parse_scores(llm.generate(
            PROMPT.format(beats=BEAT_RULE, items=build_items_block(batch)),
            api_key, model))
        by_index = {int(r["i"]): r for r in results if "i" in r}

        updates = []
        for item in batch:
            result = by_index.get(item["i"])
            if not result:
                continue                           # stays "new", picked up next run
            score = overall(result)
            status = "queued" if score >= THRESHOLD else "rejected"
            note = " ".join(f"{axis[0]}{result.get(axis, '?')}"
                            for axis in (*AXES, RELEVANCE))
            note = f"{note} · {str(result.get('why', ''))[:80]}"

            scored += 1
            queued += status == "queued"
            print(f"  {score:>5.2f}  {status:<8} {item['title'][:58]}")

            # status..beat is contiguous because beat is the last column; if
            # the sheet predates it, write up to notes as before.
            last = "beat" if "beat" in col else "notes"
            values = [status, score, note] + ([beat_of(result)] if last == "beat" else [])
            updates.append({
                "range": f"{chr(65 + col['status'])}{item['row']}:"
                         f"{chr(65 + col[last])}{item['row']}",
                "values": [values],
            })

        # Write after every batch, not once at the end: if the daily cap is
        # hit mid-run, the work already paid for is safe in the sheet.
        if updates and not args.dry_run:
            check_unmoved(worksheet,
                          {item["row"]: item["url"] for item in batch}, col)
            worksheet.batch_update(updates, value_input_option="RAW")

        if start + BATCH_SIZE < len(pending):
            time.sleep(SLEEP_BETWEEN_CALLS)

    verb = "would queue" if args.dry_run else "queued"
    print(f"\nScored {scored} of {len(pending)} · {verb} {queued} "
          f"at or above {THRESHOLD}")
    if scored < len(pending):
        print(f"{len(pending) - scored} item(s) came back unscored and are "
              "still 'new' — they'll be retried on the next run.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
