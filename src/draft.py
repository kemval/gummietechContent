#!/usr/bin/env python3
"""
Layer 3: turn the top queued item into a post JSON that render.py accepts.

Takes the highest-scoring row with status "queued", fetches the source
article, and asks the LLM for the strict JSON contract in CLAUDE.md. Writes
posts/<date>-<slug>.json and marks the row "drafted".

Usage:
    python src/draft.py
    python src/draft.py --row 47            # draft a specific sheet row
    python src/draft.py --dry-run           # print the JSON, write nothing

Environment: same as score.py (LLM_PROVIDER, GEMINI_API_KEY / GROQ_API_KEY,
GOOGLE_SHEET_ID, GOOGLE_SHEETS_CREDENTIALS).

Three things are decided in code rather than left to the model, because
they are the fields that damage the account if they are wrong:

  - source_url is copied from the sheet. A model asked for a URL will
    produce a plausible one that 404s.
  - attribution must come from the fetched text; when no authors or
    journal can be found, it falls back to the outlet name rather than
    inventing a citation.
  - peer_reviewed is forced False for known preprint servers, so the
    template's "not yet peer-reviewed" flag cannot be dropped by a
    confident guess.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
from datetime import date
from pathlib import Path

import requests

import llm                       # forwards to gemini or groq per LLM_PROVIDER
from ingest import COLUMNS, open_sheet
from render import COLORWAYS, DEFAULT_COLORWAY, HOOK_WORD_LIMIT, WORD_LIMIT
from verify_feeds import HEADERS, TIMEOUT

REPO_ROOT = Path(__file__).resolve().parent.parent
POSTS_DIR = REPO_ROOT / "posts"

ARTICLE_CHARS = 6000

# peer_reviewed is False for these no matter what the model says.
PREPRINT_HOSTS = ("arxiv.org", "biorxiv.org", "medrxiv.org", "chemrxiv.org",
                  "ssrn.com", "researchsquare.com", "preprints.org",
                  "osf.io", "hal.science")

REQUIRED = ["post_type", "domain", "hook", "what_happened", "why_it_matters",
            "the_catch", "caption", "alt_text", "attribution"]

PARA_RE = re.compile(r"<p[^>]*>(.*?)</p>", re.S | re.I)
SCRIPT_RE = re.compile(r"<(script|style)[^>]*>.*?</\1>", re.S | re.I)
TAG_RE = re.compile(r"<[^>]+>")

PROMPT = """You write posts for @gummietech, an Instagram account explaining \
science, technology and engineering to a smart non-expert audience.

Write a five-slide carousel about the item below. Return ONLY a JSON object, \
no prose and no code fences, with exactly these keys:

{{
  "post_type": "drop",
  "domain": "<2-3 word field label, e.g. AI research, materials, astronomy>",
  "colorway": "<the palette family whose subject matches this story: signal \
(AI, computing, software, robotics), orbit (space, astronomy, physics), bloom \
(biology, medicine, climate, ecology), ember (energy, materials, engineering, \
chemistry). Use exactly one of those four words. If none clearly fits, use \
signal>",
  "hook": "<at most {hook_limit} words. The finding, stated plainly. No \
questions, no 'scientists say', no hype>",
  "what_happened": "<at most {word_limit} words. Who did what, and how it works>",
  "why_it_matters": "<at most {word_limit} words. The consequence. Name the \
bottleneck it removes or the assumption it breaks>",
  "the_catch": "<at most {word_limit} words. A real limitation stated in the \
source: sample size, conditions, what was not tested. Never invent one, and \
never overstate it>",
  "caption": "<one sentence for the Instagram caption>",
  "keywords": ["<3 short topic keywords>"],
  "hashtags": ["#<4 hashtags, lowercase, last one #gummietech>"],
  "alt_text": "<one sentence describing the carousel for screen readers>",
  "attribution": "<'Surname et al., Journal (Year)' if the text names authors \
and a journal; otherwise the publishing organisation's name. Use only names \
that appear in the text below. Never guess>",
  "peer_reviewed": <true if this is published in a peer-reviewed journal, \
false if it is a preprint>
}}

Rules:
- Every claim must be supported by the text below. If the text does not say \
it, do not write it.
- No numbers that do not appear in the text.
- the_catch is the credibility slide. A weak but true limitation beats a \
strong invented one.

Source: {source}
Title: {title}
URL: {url}

Text:
{text}"""


def slugify(title: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return slug[:40].rstrip("-") or "post"


def fetch_article(url: str) -> tuple[str, str | None]:
    """
    Return (text, warning). Falls back to an empty string when the publisher
    blocks the fetch — the caller then drafts from the feed summary alone,
    which is worth saying out loud rather than papering over.
    """
    try:
        resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT,
                            allow_redirects=True)
    except requests.exceptions.RequestException as exc:
        return "", f"could not fetch the article ({type(exc).__name__})"

    if resp.status_code >= 400:
        return "", f"publisher returned HTTP {resp.status_code}"

    body = SCRIPT_RE.sub(" ", resp.text)
    paragraphs = []
    for chunk in PARA_RE.findall(body):
        text = html.unescape(TAG_RE.sub(" ", chunk))
        text = " ".join(text.split())
        if len(text) > 80:                    # skip nav, captions and bylines
            paragraphs.append(text)

    article = "\n\n".join(paragraphs)[:ARTICLE_CHARS]
    if len(article) < 400:
        return article, "article body was too short to use much of"
    return article, None


def pick_row(rows: list[list[str]], col: dict, wanted: int | None) -> tuple[int, dict]:
    """The highest-scoring queued row, or the one the caller asked for."""
    candidates = []
    for n, row in enumerate(rows[1:], start=2):
        if wanted and n != wanted:
            continue
        if not wanted and row[col["status"]] != "queued":
            continue
        try:
            score = float(row[col["score"]] or 0)
        except ValueError:
            score = 0.0
        candidates.append((score, n, row))

    if not candidates:
        sys.exit("Nothing to draft. Run `python src/score.py` first, or pass "
                 "--row with a specific sheet row." if not wanted
                 else f"Row {wanted} is not in the sheet.")

    score, n, row = max(candidates, key=lambda c: c[0])
    return n, {name: row[idx] for name, idx in col.items()} | {"score": score}


def validate(post: dict, url: str) -> dict:
    """Fill the fields we own, then refuse anything render.py would reject."""
    post["source_url"] = url                  # never the model's version
    if any(host in url.lower() for host in PREPRINT_HOSTS):
        post["peer_reviewed"] = False

    # A colour that does not suit the topic is a cosmetic miss, not a
    # credibility one, so an invented family name falls back instead of
    # killing a draft that is otherwise fine.
    if post.get("colorway") not in COLORWAYS:
        if post.get("colorway"):
            print(f"  warning: model returned colorway "
                  f"{post['colorway']!r} — using {DEFAULT_COLORWAY}")
        post["colorway"] = DEFAULT_COLORWAY

    missing = [f for f in REQUIRED if not str(post.get(f, "")).strip()]
    if missing:
        sys.exit(f"Refusing to write. The model left these empty: "
                 f"{', '.join(missing)}. Re-run to try again.")
    if not isinstance(post.get("peer_reviewed"), bool):
        sys.exit("Refusing to write. peer_reviewed came back as "
                 f"{post.get('peer_reviewed')!r}, not true or false. "
                 "An unlabelled preprint is a credibility risk.")

    for field, limit in [("hook", HOOK_WORD_LIMIT), ("what_happened", WORD_LIMIT),
                         ("why_it_matters", WORD_LIMIT), ("the_catch", WORD_LIMIT)]:
        count = len(str(post[field]).split())
        if count > limit:
            print(f"  warning: {field} is {count} words (limit {limit})")

    ordered = ["post_type", "domain", "colorway", "hook", "what_happened", "why_it_matters",
               "the_catch", "caption", "keywords", "hashtags", "alt_text",
               "source_url", "code_url", "attribution", "peer_reviewed"]
    return {k: post[k] for k in ordered if k in post}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--row", type=int, help="draft this sheet row instead")
    ap.add_argument("--dry-run", action="store_true",
                    help="print the JSON without writing or marking the row")
    args = ap.parse_args()

    api_key, model = llm.config()
    worksheet = open_sheet()
    rows = worksheet.get_all_values()
    if not rows:
        sys.exit("The sheet is empty. Run `python src/ingest.py` first.")

    col = {name: rows[0].index(name) for name in COLUMNS if name in rows[0]}
    row_number, item = pick_row(rows, col, args.row)
    print(f"Drafting row {row_number} · {item['score']} · {item['title'][:60]}")

    article, warning = fetch_article(item["url"])
    if warning:
        print(f"  warning: {warning} — drafting from the feed summary, so "
              "check the slides against the source before posting")

    reply = llm.generate(
        PROMPT.format(hook_limit=HOOK_WORD_LIMIT, word_limit=WORD_LIMIT,
                      source=item["source"], title=item["title"],
                      url=item["url"], text=article or item["summary"]),
        api_key, model, temperature=0.4)

    try:
        post = json.loads(reply.strip())
    except json.JSONDecodeError:
        sys.exit(f"The model did not return JSON:\n{reply[:400]}\nRe-run to try again.")

    post = validate(post, item["url"])
    print(json.dumps(post, indent=2, ensure_ascii=False))

    if args.dry_run:
        print("\nDry run — nothing written, row left queued")
        return 0

    POSTS_DIR.mkdir(exist_ok=True)
    out = POSTS_DIR / f"{date.today():%Y-%m-%d}-{slugify(item['title'])}.json"
    out.write_text(json.dumps(post, indent=2, ensure_ascii=False) + "\n")

    # Mark the row so the next run picks a different story.
    worksheet.update_cell(row_number, col["status"] + 1, "drafted")

    print(f"\nWrote {out.relative_to(REPO_ROOT)}")
    print(f"Render it:  python src/render.py {out.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
