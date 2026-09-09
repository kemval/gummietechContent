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

The overall score is the mean of the four axes. Items at or above
THRESHOLD become "queued"; the rest become "rejected" and stay in the
sheet as a record of what was considered.

Usage:
    python src/score.py
    python src/score.py --limit 40          # score at most 40 items
    python src/score.py --dry-run           # score and print, write nothing

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

import llm                       # forwards to gemini or groq per LLM_PROVIDER
from ingest import COLUMNS, open_sheet

# 15-20 items per request. One request per item would exhaust the daily cap
# in an afternoon; this keeps a full day's ingest inside 20-30 calls.
BATCH_SIZE = 18
SLEEP_BETWEEN_CALLS = 5          # seconds; ~12 requests/minute

AXES = ["novelty", "visual", "explain", "surprise"]

# docs/gummietech_content_system.md: "Only items scoring >= 7 total surface
# in the morning queue."
THRESHOLD = 7.0

PROMPT = """You are the editorial filter for @gummietech, an Instagram account \
that explains science, technology and engineering to a smart non-expert audience.

Score each item below from 1 to 10 on four axes:

- novelty: genuinely new work, or a rehash of something already everywhere?
- visual: is there a real image, diagram, dataset or physical object to build \
five slides from? Text-only policy news scores low.
- explain: can a smart non-expert understand the point in five slides?
- surprise: does it violate an intuition? This is what makes people share.

Score 3 or below on every axis for: funding rounds, hiring and personnel news, \
product launches with no technical substance, opinion pieces and editorials, \
listicles, awards, conference announcements, and stories with no specific \
finding or mechanism.

Return ONLY a JSON array, one object per item, no prose and no code fences:
[{{"i": <item number>, "novelty": <1-10>, "visual": <1-10>, "explain": <1-10>, \
"surprise": <1-10>, "why": "<at most 12 words>"}}]

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

    return data if isinstance(data, list) else []


def overall(scores: dict) -> float:
    return round(sum(float(scores.get(axis, 0)) for axis in AXES) / len(AXES), 2)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, help="score at most this many items")
    ap.add_argument("--dry-run", action="store_true",
                    help="score and print without writing to the sheet")
    args = ap.parse_args()

    api_key, model = llm.config()

    worksheet = open_sheet()
    rows = worksheet.get_all_values()             # one read for the whole sheet
    if not rows:
        sys.exit("The sheet is empty. Run `python src/ingest.py` first.")

    col = {name: rows[0].index(name) for name in COLUMNS if name in rows[0]}
    pending = [
        {"row": n, "i": len(rows),                # placeholder, renumbered below
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
            PROMPT.format(items=build_items_block(batch)), api_key, model))
        by_index = {int(r["i"]): r for r in results if "i" in r}

        updates = []
        for item in batch:
            result = by_index.get(item["i"])
            if not result:
                continue                           # stays "new", picked up next run
            score = overall(result)
            status = "queued" if score >= THRESHOLD else "rejected"
            note = " ".join(f"{axis[0]}{result.get(axis, '?')}" for axis in AXES)
            note = f"{note} · {str(result.get('why', ''))[:80]}"

            scored += 1
            queued += status == "queued"
            print(f"  {score:>5.2f}  {status:<8} {item['title'][:58]}")

            updates.append({
                "range": f"{chr(65 + col['status'])}{item['row']}:"
                         f"{chr(65 + col['notes'])}{item['row']}",
                "values": [[status, score, note]],
            })

        # Write after every batch, not once at the end: if the daily cap is
        # hit mid-run, the work already paid for is safe in the sheet.
        if updates and not args.dry_run:
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
