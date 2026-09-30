#!/usr/bin/env python3
"""
Layer 3: turn the top queued item into a post JSON that render.py accepts.

Takes the highest-scoring row with status "queued", fetches the source
article, resolves the paper behind it, and asks the LLM for the strict JSON
contract in CLAUDE.md. Writes posts/<date>-<slug>.json and marks the row
"drafted".

`--signal` walks five rows instead of one and writes a Signal — the weekly
roundup. It is the same walk, the same Crossref detour and the same code
ownership of the credit and the preprint flag, applied per item rather than
per post, and one LLM call writes all five claims. The queue is where those
items come from because it already holds far more rows above the scoring
threshold than ever get drafted, and every one that is not picked stays
there (docs §1, The Signal). The order the sources go into the prompt is
the queue's score order and the model is told not to change it: that index
is the only thing tying a claim to its attribution.

Usage:
    python src/draft.py
    python src/draft.py --row 47            # draft a specific sheet row
    python src/draft.py --url https://...   # draft an evergreen source
    python src/draft.py --signal            # the weekly roundup, top 5 rows
    python src/draft.py --dry-run           # print the JSON, write nothing
    python src/draft.py --reject posts/X.json --reason "..."
                                            # retire a waiting draft (redraft.yml)

Environment: same as score.py (LLM_PROVIDER, GEMINI_API_KEY / GROQ_API_KEY,
GOOGLE_SHEET_ID, GOOGLE_SHEETS_CREDENTIALS).

Most feeds are news coverage, not papers. Coverage simplifies the mechanism,
overstates what the result overturns, and quotes whoever gave the interview —
who is often a senior author and sometimes not an author at all. So before
drafting, this pulls the DOI off the page and asks Crossref who actually
wrote the thing; the abstract, when Crossref has one, goes to the model as
the primary source with the coverage demoted to context.

Three things are decided in code rather than left to the model, because
they are the fields that damage the account if they are wrong:

  - source_url is copied from the sheet. A model asked for a URL will
    produce a plausible one that 404s.
  - attribution is built from the Crossref author list when the paper
    resolves. Failing that it must come from the fetched text, falling back
    to the outlet name rather than inventing a citation.
  - peer_reviewed follows the Crossref record type, which catches a preprint
    reported on a news domain — the case the host check below cannot see —
    and a preprint host then forces it False regardless.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
from collections.abc import Iterator
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

import llm                       # forwards to gemini or groq per LLM_PROVIDER
from formats import entries as format_entries
from formats import missing_from_entries, required as format_required
from ingest import COLUMNS, open_sheet
from papers import (CONTENT_RE, TAG_RE, citation, fetch_article, resolve_paper,
                    source_text)
from render import (COLORWAYS, DEFAULT_COLORWAY, HOOK_WORD_LIMIT, WORD_LIMIT,
                    previous_colorway, vary, warn_on_length)

REPO_ROOT = Path(__file__).resolve().parent.parent
POSTS_DIR = REPO_ROOT / "posts"
EVERGREEN_QUEUE = REPO_ROOT / "docs" / "evergreen_queue.md"

# docs §1: five items, one slide each. A Signal is five sources in one
# prompt, so each gets a fraction of a Drop's budget — one sentence per item
# needs the result, not the whole article, and five full ones would be 30k
# characters against a free tier for five lines of output.
SIGNAL_ITEMS = 5
SIGNAL_SOURCE_CHARS = 1500
# An item claim is a hook, not a body field: signal.html sets it in 66px
# display type, where WORD_LIMIT's 25 words overflow the frame. proof.py
# measures the rendered box either way; this is what keeps the model from
# writing past it in the first place.
CLAIM_WORD_LIMIT = HOOK_WORD_LIMIT

# peer_reviewed is False for these no matter what Crossref or the model says.
PREPRINT_HOSTS = ("arxiv.org", "biorxiv.org", "medrxiv.org", "chemrxiv.org",
                  "ssrn.com", "researchsquare.com", "preprints.org",
                  "osf.io", "hal.science")

# What a *draft* needs on top of what render.py will refuse to render
# without. formats.py owns the rest, per format, and is asked for it —
# this used to name a Drop's body fields, which made it a fourth copy of
# that table and the reason a Signal could not come out of this file at all.
#
#   domain   — required here though formats.py has it optional: drop.html
#              prints it on every slide and the archive translates it, so a
#              drafted post without one is a post with a hole in it.
#   caption  — needed to *post*, not to render. render.py is right not to
#              care; this is the file that writes caption.txt.
DRAFTED = ("post_type", "domain", "caption")

# owner/repo on the three hosts papers link code from. Deeper paths are
# dropped: a slide prints the repo, and /tree/main/... is noise on it.
# huggingface.co/papers/<id> is the paper again, not code.
CODE_URL_RE = re.compile(
    r"https?://(?:www\.)?(?:github\.com|gitlab\.com|huggingface\.co)"
    r"/(?!papers/)(?:(?:datasets|spaces)/)?[\w.-]+/[\w.-]+", re.I)
# How many cover lines the model offers. Three, because the gate message
# lists them and hook.yml's input is a choice of that many.
HOOK_CHOICES = 3
OG_TITLE_RE = re.compile(r"<meta[^>]*og:title[^>]*>", re.I)
TITLE_TAG_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.S | re.I)

# The alt_text line is specific about what the slides are not, because the
# model otherwise writes what a science post's images would normally be —
# "JWST images of IC 348 with highlighted candidates and spectra" — and
# drop.html has no <img> and no background-image. That is a screen-reader user
# being told about a photograph that is not there, and it had to be corrected
# by hand (3c1b29d) before this line existed.
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
  "hooks": ["<three cover lines for the same finding, each at most \
{hook_limit} words, each a different angle. 1: the finding, stated plainly. \
2: the assumption it breaks or the belief it corrects — only if the text \
names one; otherwise another plain statement. 3: what it changes for the \
reader, or its number made concrete ('as thin as', 'in the time it takes \
to'). No questions, no 'scientists say', no hype, and no claim the text does \
not support — a person picks one of these for the cover>"],
  "what_happened": "<at most {word_limit} words. Who did what, and how it works>",
  "why_it_matters": "<at most {word_limit} words. The consequence. Name the \
bottleneck it removes or the assumption it breaks>",
  "the_catch": "<at most {word_limit} words. A real limitation stated in the \
source: sample size, conditions, what was not tested. Never invent one, and \
never overstate it>",
  "caption": "<two sentences. The first states the finding and carries the \
words a reader would actually search for, spelled out in plain prose — \
Instagram indexes caption text, so the keywords earn their place here and \
not only in the hashtags. The second is a question to the reader about the \
finding, and the caption ends on it>",
  "keywords": ["<3 short topic keywords>"],
  "hashtags": ["#<4 hashtags, lowercase, last one #gummietech>"],
  "alt_text": "<one sentence describing the carousel for screen readers. \
The slides carry no photographs, charts or diagrams: each one is a flat \
colour field with the post's own words on it. Say what the carousel says, \
never what it depicts>",
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
- Where a PAPER section appears below, it outranks the coverage. Coverage \
simplifies mechanisms, overstates what a result overturns, and quotes \
researchers who did not write the paper. Never credit the work to a name \
that is not in the paper's author list, and never describe the method in \
terms the paper contradicts.
- Every hook is held to the rules below, not only the first: any one of \
them may end up on the cover.
- the_catch is the credibility slide. Prefer a limitation the paper states \
about itself. A weak but true limitation beats a strong invented one.

Source: {source}
Title: {title}
URL: {url}

{text}"""


SIGNAL_PROMPT = """You write posts for @gummietech, an Instagram account \
explaining science, technology and engineering to a smart non-expert audience.

Write this week's Signal: a ranked roundup of {count} results, one slide \
each. Return ONLY a JSON object, no prose and no code fences, with exactly \
these keys:

{{
  "domain": "<2-3 word label for the carousel as a whole, e.g. This week, \
Research roundup>",
  "colorway": "<the palette family matching the week's dominant subject: \
signal (AI, computing, software, robotics), orbit (space, astronomy, \
physics), bloom (biology, medicine, climate, ecology), ember (energy, \
materials, engineering, chemistry)>",
  "hook": "<the cover line, {hook_limit} words maximum: source 1's result \
as a teaser, then how many more follow. e.g. 'A brain implant decoded speech \
and gesture — plus {more} more'. It must be supported by source 1 alone. A \
cover that says the same thing every week is a cover nobody stops for>",
  "items": [
    {{"claim": "<the result in one sentence, {claim_limit} words maximum>",
      "attribution": "<who did the work: 'Surname et al., Journal (year)'>"}}
  ],
  "caption": "<2-3 sentences for the Instagram caption, ending in a question>",
  "keywords": ["<3-5 search terms>"],
  "hashtags": ["#<5-8 tags, mixing broad and niche>"],
  "alt_text": "<one sentence describing the carousel for a screen reader. \
It is text on flat colour fields — there are no photographs, charts or \
diagrams on these slides. Describe what the slides say, not what a science \
post's images would normally be.>"
}}

Rules:
- "items" must have exactly {count} entries, in the SAME ORDER as the \
sources below. Do not reorder, merge, drop or add. Item 1 is source 1.
- Each claim is one specific result, in plain words, with the number in it \
where there is one. "A brain implant decoded speech and gesture from one \
253-electrode array", not "researchers made progress on brain implants".
- No claim may overstate what its source says. This is a reference carousel; \
a reader saves it to look something up later.
- Write "attribution" from the source text as 'Surname et al., Journal \
(year)'. Never invent one — if the text does not say who did the work, name \
the outlet instead.
- Do not write a caveat slide. This format has no catch slide; a roundup has \
five caveats or none.

{sources}"""


def signal_sources(picks: list[dict]) -> str:
    """The numbered source block a Signal is drafted from.

    Numbered because the index is the only thing tying a claim back to its
    credit and its URL — validate_signal refuses a reply of the wrong length
    for the same reason. The paper comes first where Crossref resolved one,
    exactly as it does for a Drop, and is trimmed hard: this is one prompt
    carrying five sources and it buys five sentences.
    """
    blocks = []
    for n, pick in enumerate(picks, start=1):
        item = pick["item"]
        text = source_text(pick["paper"], pick["article"], item["summary"])
        blocks.append(f"--- SOURCE {n} ---\n"
                      f"Outlet: {item['source']}\n"
                      f"Headline: {item['title']}\n"
                      f"URL: {item['url']}\n\n"
                      f"{text[:SIGNAL_SOURCE_CHARS]}")
    return "\n\n".join(blocks)


def parsed(reply: str) -> dict:
    """The model's JSON, or a stop that says to re-run."""
    try:
        post = json.loads(reply.strip())
    except json.JSONDecodeError:
        sys.exit(f"The model did not return JSON:\n{reply[:400]}\n"
                 "Re-run to try again.")
    if not isinstance(post, dict):
        sys.exit(f"The model returned {type(post).__name__}, not a JSON "
                 "object. Re-run to try again.")
    return post


def slugify(title: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return slug[:40].rstrip("-") or "post"


def page_title(page: str) -> str:
    """The publisher's own headline for a page, og:title first."""
    og = OG_TITLE_RE.search(page)
    if og:
        content = CONTENT_RE.search(og.group(0))
        if content:
            return " ".join(html.unescape(content.group(1)).split())
    tag = TITLE_TAG_RE.search(page)
    if tag:
        return " ".join(html.unescape(TAG_RE.sub(" ", tag.group(1))).split())
    return ""


def outlet(url: str) -> str:
    """'physics.stackexchange.com' — what the prompt calls the source."""
    return urlparse(url).netloc.lower().removeprefix("www.") or url


# Each rejected candidate costs a page fetch and a Crossref call inside a job
# with a 15-minute timeout, so the guard gives up rather than walking a queue
# of 1440 rows. Five is enough for a story covered by every feed at once.
MAX_DUPLICATE_SKIPS = 5


# The account is tech-first: AI, software, automation, ML and robotics are
# what it is for, and science fills in only when none of those is queued.
# Taking the single highest score regardless of subject never gets there:
# measured over 8,095 rows on 2026-09-27, the `ai` feeds averaged 4.88
# against biology's 6.74, and 1 of 195 AI items reached the 8.75 the top of
# the queue starts at — so September shipped almost no AI while 777 tech
# candidates sat above the threshold. The score stays topic-blind; the
# preference is applied here, where one row is chosen from many.
PRIORITY_BEATS = frozenset({"ai", "software", "automation", "robotics",
                            "computing"})
# Rows scored before score.py named a beat have none. Their feed's topic is
# the fallback — coarser, since a feed is not a subject, but it costs no
# call, and re-scoring a queue of ~2,400 rows would spend days of quota.
PRIORITY_TOPICS = frozenset({"ai", "tech", "robotics"})


def is_priority(row: list[str], col: dict) -> bool:
    """Is this row about one of the subjects the account puts first?"""
    def cell(name: str) -> str:
        idx = col.get(name)
        return row[idx].strip().lower() if idx is not None and idx < len(row) else ""
    beat = cell("beat")
    return beat in PRIORITY_BEATS if beat else cell("topic") in PRIORITY_TOPICS


def pick_row(rows: list[list[str]], col: dict, wanted: int | None,
             skip: set[int] = frozenset()) -> tuple[int, dict]:
    """The highest-scoring queued row on a priority subject, or the one the
    caller asked for.

    Science is taken only when no priority row is left — see PRIORITY_BEATS.
    A row named with --row is the override and ignores the preference.

    `skip` holds rows this run has already rejected as duplicates. Their
    status is updated in the sheet too, but `rows` is the snapshot read
    before that, so without this the next pass would pick the same one.
    """
    candidates = []
    for n, row in enumerate(rows[1:], start=2):
        if n in skip:
            continue
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

    preferred = [c for c in candidates if is_priority(c[2], col)]
    if not wanted and not preferred:
        print("  note: no queued row on a priority subject — taking the best "
              "science row instead")
    score, n, row = max(preferred or candidates, key=lambda c: c[0])
    return n, {name: row[idx] for name, idx in col.items()
               if idx < len(row)} | {"score": score}


# Tier 6 evergreen subjects never come through a feed, so there is no page to
# scrape and no row in the sheet. What there is instead is the queue the
# evergreen-scout agent writes, where each candidate already carries the hook,
# the mechanism, the catch and the primary to attribute — the substance a
# scrape would have had to recover. Drafting from a URL instead throws that
# away and the model fills the gap from memory: pointed at the tides
# candidate's sources it produced the two-bulge myth the post exists to
# debunk, and a Wikipedia history section, whose reference list then supplied
# a DOI that overwrote the attribution. So the brief is the source text.
#
# The agent writes a fixed shape, in score order:
#
#   ### 1 · 8.50 · `orbit` — The tidal bulges that don't exist
#   **Hook** — ...
#   **Source** — [Physics SE](url) · **attribute to** Laplace's ...
#   **Settled?** / **Why it matters** / **The catch**
CANDIDATE_RE = re.compile(
    r"^### (?P<rank>\d+) [·.] (?P<score>[\d.]+) [·.] `(?P<colorway>\w+)`"
    r" [—-] (?P<title>.+)$", re.M)
FIELD_RE = re.compile(r"^\*\*(?P<label>[^*]+)\*\*\s*[—-]?\s*(?P<value>.+)$",
                      re.M)
MD_LINK_RE = re.compile(r"\[[^\]]*\]\((https?://[^)\s]+)\)")
# Seven rows name who to credit, because the page a subject is explained on is
# rarely the work being credited — a Stack Exchange answer about Laplace's
# tides, a Wikipedia article about a 2008 review. Left to itself the model
# credits the page's organisation ("Physics SE"), which is what fact-check
# BLOCKs on. This cannot be copied into the field verbatim, though: three of
# the seven are instructions to a person, naming a choice ("the vis-viva
# result or a NASA mission page") or carrying a second sentence of guidance.
# So it is hoisted to the top of the brief as binding, and the model resolves
# it to a citation — then a person checks it at the gate.
ATTRIBUTE_RE = re.compile(r"\*\*attribute to\*\*\s*(?P<who>[^\n]+)", re.I)
# A row whose primary is a preprint cites it as a bare "arXiv:2601.04621" and
# links only the coverage, so taking the first link would put a magazine URL
# in source_url and leave PREPRINT_HOSTS silent on a preprint. The id is the
# primary, so it wins — which is what makes the flag fire, as the queue's own
# preface promises it does.
ARXIV_RE = re.compile(r"arxiv:\s*(?P<id>\d{4}\.\d{4,5}(?:v\d+)?)", re.I)


def evergreen_candidate(rank: int, skip: frozenset[int] = frozenset()) -> dict:
    """
    A row from the evergreen queue as a draftable item, rank 0 meaning the
    highest-scoring one left. The brief becomes the summary, which is what the
    model drafts from, and the Source line's first link becomes source_url.

    `skip` holds ranks this run rejected as already covered. It applies to
    rank 0 only: asking for a numbered candidate is naming one by hand, and a
    named candidate is drafted whatever posts/ says.
    """
    if not EVERGREEN_QUEUE.exists():
        sys.exit(f"No evergreen queue at "
                 f"{EVERGREEN_QUEUE.relative_to(REPO_ROOT)}. Run the "
                 "evergreen-scout agent to fill it, then draft from it.")

    text = EVERGREEN_QUEUE.read_text()
    heads = list(CANDIDATE_RE.finditer(text))
    if not heads:
        sys.exit(f"No candidates found in "
                 f"{EVERGREEN_QUEUE.relative_to(REPO_ROOT)}. Rows must look "
                 "like '### 1 · 8.50 · `orbit` — Title'; re-run "
                 "evergreen-scout if the file has drifted.")

    if rank:
        picked = next((h for h in heads if int(h["rank"]) == rank), None)
        if picked is None:
            ranks = ", ".join(h["rank"] for h in heads)
            sys.exit(f"No candidate #{rank} in the queue. Available: {ranks}.")
    else:
        # The file is written in score order, so the first candidate this run
        # has not rejected is the best one still worth drafting.
        picked = next((h for h in heads if int(h["rank"]) not in skip), None)
        if picked is None:
            sys.exit(f"Every candidate in "
                     f"{EVERGREEN_QUEUE.relative_to(REPO_ROOT)} is already "
                     f"covered by a post in posts/. Run the evergreen-scout "
                     f"agent to refill the queue, or pass --evergreen N to "
                     f"draft one of them anyway.")

    ends = [h.start() for h in heads if h.start() > picked.start()]
    body = text[picked.end():ends[0] if ends else len(text)]
    fields = {m["label"].strip().lower(): m["value"].strip()
              for m in FIELD_RE.finditer(body)}

    missing = [f for f in ("hook", "source", "why it matters", "the catch")
               if f not in fields]
    if missing:
        sys.exit(f"Candidate #{picked['rank']} is missing "
                 f"{', '.join(missing)}. Fix the row in "
                 f"{EVERGREEN_QUEUE.relative_to(REPO_ROOT)} and re-run.")

    arxiv = ARXIV_RE.search(fields["source"])
    link = MD_LINK_RE.search(fields["source"])
    if arxiv:
        url = f"https://arxiv.org/abs/{arxiv['id']}"
    elif link:
        url = link.group(1)
    else:
        url = ""
        print("  warning: the Source line has no URL, so source_url will be "
              "empty — the web archive prints it, so add one at the gate")

    lines = [f"{label.title()}: {value}" for label, value in fields.items()]
    credit = ATTRIBUTE_RE.search(fields["source"])
    if credit:
        who = credit["who"].strip().rstrip(".")
        print(f"  credit: the queue says attribute to {who!r} — check the "
              "field below says that and not the page's publisher")
        lines.insert(0, f"Attribution to use, overriding every rule below "
                        f"about organisations: {who}")

    # The scout writes "peer_reviewed: false" into a row that is not settled
    # science; everything else in the queue is established by the queue's own
    # entry criterion. The model cannot tell: the brief names no journal, so
    # it reads that as unpublished and returns False, which would put a
    # "not yet peer-reviewed" flag on a textbook result.
    return {
        "url": url,
        "rank": int(picked["rank"]),
        "source": f"evergreen queue #{picked['rank']}",
        "title": picked["title"].strip(),
        "summary": "\n".join(lines),
        "score": picked["score"],
        "colorway": picked["colorway"],
        "peer_reviewed": "peer_reviewed: false" not in body.lower(),
    }


def covered_papers() -> dict[str, str]:
    """Every paper posts/ already covers, keyed by DOI, citation and URL.

    The sheet is deduplicated by URL, and a story is not a URL: 45 feeds
    cover one press release, each copy arrives as its own row with its own
    score, and the siblings of the one that gets drafted stay queued
    forever. On 2026-09-17 the highest-scoring row in a queue of 1440 was
    the paper published that same morning, and another was a story from two
    weeks earlier.

    Older posts carry no `doi` — it was not written until this guard needed
    it — so the citation is the key that works on all of them. Both come
    from the same Crossref record, so they agree.

    `source_url` is the third key, and it is the only one an evergreen
    candidate has. That path never fetches a page, so resolve_paper gets
    nothing to work with and neither of the other two keys can ever be
    formed — which meant `--evergreen` would happily re-draft a subject
    already posted. The tides candidate is still #1 in the queue and was
    published on 2026-09-15; before this key it came back up clean. Matched
    as written, so a URL that differs by a query string or a trailing slash
    is a miss — the fact-check agent reads posts/ and catches what a key
    cannot.
    """
    seen: dict[str, str] = {}
    # A draft turned down at the gate still covered its paper: the story was
    # judged and passed on, and it must not come back through a sibling
    # feed's row. See reject().
    for path in sorted([*POSTS_DIR.glob("*.json"),
                        *(POSTS_DIR / REJECTED_DIR).glob("*.json")]):
        try:
            post = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            continue          # site.py skips a malformed post; so does this
        # A Signal carries none of these at the top level: its record moves
        # all three onto its five items. Without the second loop a roundup
        # covered five stories that this guard could not see, and the next
        # Signal would have picked the same rows straight back out of the
        # queue — which is the whole failure this function exists for.
        records = [post, *format_entries(post)]
        for record in records:
            for key in (record.get("doi"), record.get("attribution"),
                        record.get("source_url")):
                if key and str(key).strip():
                    seen.setdefault(" ".join(str(key).lower().split()),
                                    path.name)
    return seen


# Where reject() moves a draft. A subdirectory, not a deletion and not a
# field: every other reader of posts/ — site.py, resolve-post, watch.py,
# learn.py's post groups, daily.yml's gate — globs posts/*.json without
# recursing, so a moved draft leaves all of them at once, while
# covered_papers() above reads it on purpose.
REJECTED_DIR = "rejected"


def reject(path: Path, reason: str, today: str) -> Path:
    """Retire a waiting draft at the gate, keeping it as dedup memory.

    For redraft.yml: the story on the waiting draft was not worth posting,
    so it leaves the queue and the next one is drafted in its place. The
    sheet row stays `drafted`, which already keeps pick_row() off it.
    Refuses a dated post — that one is live — and a Breakdown, which a
    person wrote and nothing here can draft again.
    """
    try:
        post = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        sys.exit(f"Cannot read {path}: {exc}. Check the path, or leave "
                 f"redraft.yml's post input blank to take the waiting one.")
    if post.get("published_at"):
        sys.exit(f"{path.name} has published_at {post['published_at']} — it "
                 f"is live, and a live post is not rejected. Nothing moved.")
    if post.get("post_type") == "breakdown":
        sys.exit(f"{path.name} is a Breakdown, which is written by hand; "
                 f"nothing can draft another in its place. Edit it instead. "
                 f"Nothing moved.")
    post["rejected"] = {"at": today, "reason": reason.strip()}
    dest = path.parent / REJECTED_DIR / path.name
    dest.parent.mkdir(exist_ok=True)
    dest.write_text(json.dumps(post, indent=2, ensure_ascii=False) + "\n")
    path.unlink()
    return dest


def already_covered(paper: dict | None, url: str,
                    seen: dict[str, str]) -> str | None:
    """The post that already covers this candidate, if there is one.

    The paper's own keys first, then the URL the candidate came from — which
    is all an evergreen brief ever has, since that path fetches no page and
    so resolves no paper. Coverage with no DOI and a URL nobody has posted
    from is left to the fact-check agent, which reads posts/ and can see a
    duplicate the keys cannot.
    """
    keys = [paper.get("doi"), citation(paper)] if paper else []
    keys.append(url)
    for key in keys:
        if key:
            hit = seen.get(" ".join(str(key).lower().split()))
            if hit:
                return hit
    return None


def peer_review_flag(paper: dict | None, url: str,
                     fallback: bool | None = None) -> bool | None:
    """Whether a source is peer-reviewed.

    Crossref's record type first — it catches a preprint reported on a news
    domain, which the host check below cannot see — then the host, which can
    only ever force the flag down: a reader on arxiv.org is reading a
    preprint whatever Crossref says about a later version.

    `fallback` is what stands when neither of those knows: the model's own
    answer for a Drop, an evergreen row's for a named candidate, and None
    for a Signal item — which is not a value but a question, and
    settled_candidates rejects the candidate rather than letting the model
    answer it. Returning None rather than guessing is what makes that
    possible.
    """
    flag = fallback
    if paper:
        flag = not paper["is_preprint"]
    if any(host in url.lower() for host in PREPRINT_HOSTS):
        flag = False
    return flag


def finish(post: dict, order: list[str]) -> dict:
    """The checks every format shares, then the key order.

    Everything in here reads formats.py rather than a list of a Drop's
    fields, which is what lets a Signal come out of the same function.
    """
    # A colour that does not suit the topic is a cosmetic miss, not a
    # credibility one, so an invented family name falls back instead of
    # killing a draft that is otherwise fine.
    if post.get("colorway") not in COLORWAYS:
        if post.get("colorway"):
            print(f"  warning: model returned colorway "
                  f"{post['colorway']!r} — using {DEFAULT_COLORWAY}")
        post["colorway"] = DEFAULT_COLORWAY

    # The topic picks the family; the post before it can veto the hue. See
    # render.vary() for why a topic mapping alone is not enough. This asks
    # about the end of posts/ because the file is written after finish()
    # returns, and the end is where it lands.
    varied = vary(post["colorway"], previous_colorway())
    if varied != post["colorway"]:
        print(f"  colorway: {post['colorway']} would repeat the post before "
              f"it — using {varied}")
        post["colorway"] = varied

    # render.py's own rule, from the same table: presence for peer_reviewed,
    # because False is the whole point of the field, and truthiness for the
    # rest. A Signal's record carries none of the three source fields, so
    # this asks about `items` there and about the entries below.
    wanted = (*DRAFTED, *format_required(post))
    missing = [f for f in wanted
               if post.get(f) is None or (f != "peer_reviewed"
                                          and not post.get(f))]
    missing += missing_from_entries(post)
    if missing:
        sys.exit(f"Refusing to write. The model left these empty: "
                 f"{', '.join(missing)}. Re-run to try again.")
    if "peer_reviewed" in wanted and not isinstance(post["peer_reviewed"], bool):
        sys.exit("Refusing to write. peer_reviewed came back as "
                 f"{post.get('peer_reviewed')!r}, not true or false. "
                 "An unlabelled preprint is a credibility risk.")

    warn_on_length(post)
    return {k: post[k] for k in order if k in post}


DROP_KEYS = ["post_type", "domain", "colorway", "hook", "hooks",
             "what_happened", "why_it_matters", "the_catch", "caption",
             "keywords", "hashtags", "alt_text", "source_url", "code_url", "doi", "attribution",
             "peer_reviewed", "beat"]


def row_subject(item: dict) -> str:
    """What a drafted row was about, recorded for watch.py.

    A Drop or a Signal item that fell back to science means the tech pool ran
    dry, and the only other place that is said is a run log nobody reads. The
    scorer's beat, else the feed's topic for a row scored before beats
    existed — the order pick_row judges it in. An evergreen or --url draft
    has no row and records nothing.
    """
    return item.get("beat") or item.get("topic") or ""


def code_link(paper: dict | None, item: dict) -> str | None:
    """The repository the paper itself points to, if it points to one.

    Read from the paper's own abstract first, then the feed item's summary —
    for an arXiv row that summary *is* the abstract, and it is where authors
    write "code is available at". Never from the fetched page: an
    aggregator's sidebar links other projects' repos exactly as its
    related-stories rail carries other papers' DOIs (see DOI_CUES), and a
    wrong repo under a result on slide 5 is a wrong credit.
    """
    for text in ((paper or {}).get("abstract", ""), item.get("summary", "")):
        if found := CODE_URL_RE.search(text or ""):
            return found.group(0).rstrip(".,;:)")
    return None


def hook_choices(post: dict) -> dict:
    """`hook` and `hooks` from whichever shape the model replied in.

    The model writes three cover lines and a person picks one at the gate —
    hook.yml swaps it. The first is the one rendered until then. A reply in
    the old single-`hook` shape is still a draft: it just has no choices.
    """
    raw = post.pop("hooks", None)
    options = raw if isinstance(raw, list) else []
    if post.get("hook"):
        options.insert(0, post["hook"])
    hooks: list[str] = []
    for option in options:
        text = " ".join(str(option).split())
        if text and text not in hooks:
            hooks.append(text)
    hooks = hooks[:HOOK_CHOICES]
    if not hooks:
        return {}              # finish() reports the missing hook
    return {"hook": hooks[0], **({"hooks": hooks} if len(hooks) > 1 else {})}


def validate(post: dict, item: dict, paper: dict | None) -> dict:
    """Fill the fields we own, then refuse anything render.py would reject."""
    url = item["url"]
    post["source_url"] = url                  # never the model's version

    # An evergreen row settles the preprint flag itself — see
    # evergreen_candidate for why the model cannot. Retraction has no field in
    # the contract at all; flag that one by hand at the gate.
    post["peer_reviewed"] = peer_review_flag(
        paper, url,
        item["peer_reviewed"] if "peer_reviewed" in item
        else post.get("peer_reviewed"))

    # Attribution comes from Crossref when the paper resolved. It is a field
    # the model gets wrong in a repeatable way: coverage quotes whoever gave
    # the interview, who may be the senior author or — as in the
    # Moon-formation draft that prompted this — an outside commentator who
    # did not write the paper at all.
    if paper:
        cite = citation(paper)
        if cite:
            if post.get("attribution") and post["attribution"] != cite:
                print(f"  attribution: model wrote {post['attribution']!r}, "
                      f"using Crossref's {cite!r}")
            post["attribution"] = cite
        # Written for covered_papers() above, and for a person reading the
        # JSON at the gate. The model never supplies it.
        post["doi"] = paper["doi"]

    if subject := row_subject(item):
        post["beat"] = subject

    # Written by code, never by the model: a repo link the model supplies is
    # a URL nobody can tell from an invented one. See code_link().
    post.pop("code_url", None)
    if link := code_link(paper, item):
        post["code_url"] = link

    post.update(hook_choices(post))
    return finish(post, DROP_KEYS)


SIGNAL_KEYS = ["post_type", "domain", "colorway", "hook", "items", "caption",
               "keywords", "hashtags", "alt_text"]
ITEM_KEYS = ["claim", "attribution", "source_url", "doi", "peer_reviewed",
             "beat"]


def validate_signal(post: dict, picks: list[dict]) -> dict:
    """Same idea as validate(), once per item.

    `picks` is the candidate list in the order it went into the prompt, and
    the model is told not to reorder. That order is the only thing tying a
    claim to its source, so a reply of the wrong length is refused outright
    rather than zipped against whatever happens to line up: silently pairing
    claim 3 with paper 4 would credit the wrong authors on a public slide,
    which is the single worst thing this file can emit.
    """
    post["post_type"] = "signal"
    items = post.get("items")
    if not isinstance(items, list) or len(items) != len(picks):
        sys.exit(f"Refusing to write. {len(picks)} sources went in and "
                 f"{len(items) if isinstance(items, list) else 'not a list'} "
                 "came back. The order is the only thing that links a claim "
                 "to its credit. Re-run to try again.")

    out = []
    for item, pick in zip(items, picks):
        paper, url = pick["paper"], pick["item"]["url"]
        built = {"claim": str(item.get("claim", "")).strip(),
                 "attribution": str(item.get("attribution", "")).strip(),
                 "source_url": url,
                 "peer_reviewed": peer_review_flag(paper, url)}
        if subject := row_subject(pick["item"]):
            built["beat"] = subject
        if paper:
            if cite := citation(paper):
                built["attribution"] = cite
            built["doi"] = paper["doi"]
        elif built["peer_reviewed"] is None:
            # settled_candidates(labelled_only=True) rejects these before the
            # model is reached, so getting here means the picks did not come
            # from that walk. Still a stop: §7.2 is a per-claim rule, and an
            # unlabelled claim on a slide is the risk the rule exists for.
            sys.exit(
                f"Refusing to write. Nothing could settle peer_reviewed for "
                f"{url} — no DOI resolved and the host is not a known "
                "preprint server. An unlabelled claim on a slide is a "
                "credibility risk.")
        out.append({k: built[k] for k in ITEM_KEYS if k in built})

    post["items"] = out
    return finish(post, SIGNAL_KEYS)


def check_budget(rejected: int, wanted: int) -> None:
    """Give up rather than walking a 1440-row queue inside a 15-minute job.

    Each rejected candidate costs a page fetch and a Crossref call. Five is
    enough for a story covered by every feed at once, and a Signal asking
    for five items gets five times the rope for the same reason.
    """
    if rejected < MAX_DUPLICATE_SKIPS * wanted:
        return
    sys.exit(f"Rejected {rejected} rows in a row and gave up — the queue's "
             "top scores are all stories already posted, or sources nothing "
             "can resolve. Run `python src/ingest.py` for fresh items, or "
             "pass --row to draft a specific one anyway.")


def settled_candidates(args, rows: list[list[str]], col: dict, worksheet,
                       seen: dict[str, str], wanted: int,
                       labelled_only: bool = False) -> Iterator[dict]:
    """Candidates that survive the duplicate guard, in queue order.

    A candidate is only settled once its paper has been resolved, which is
    after the page has been fetched, so rejecting one means going back for
    another. Each pass costs one fetch and one Crossref call and no LLM
    call — the model is not reached until `wanted` of them survive.

    A Drop asks for one and a Signal for five, and the walk down the queue is
    the same either way, which is why it is one function rather than two.
    Only the plain sheet path ever asks for more than one: --row, --url and
    --evergreen each name a single candidate, and naming one is the override.

    Yields {"row", "item", "article", "paper"}.
    """
    # Rows this run has rejected as duplicates or already handed out, and
    # evergreen ranks likewise. pick_row reads a snapshot taken before any of
    # them were marked, so without this it would return the same one again.
    skipped: set[int] = set()
    skipped_ranks: set[int] = set()
    rejected = 0
    # `--evergreen` with no number asks for the best candidate left, which is
    # a question this loop can ask again after a rejection. `--evergreen N`
    # names one, and naming one is the override.
    auto_evergreen = args.evergreen == 0
    found = 0

    while found < wanted:
        row_number = None
        if args.evergreen is not None:
            item = evergreen_candidate(args.evergreen, frozenset(skipped_ranks))
        elif args.url:
            item = {"url": args.url, "source": outlet(args.url),
                    "title": "", "summary": "", "score": "—"}
        else:
            row_number, item = pick_row(rows, col, args.row, skipped)

        where = f"row {row_number}" if row_number else item["source"]
        print(f"{'Item ' + str(found + 1) if wanted > 1 else 'Drafting'} "
              f"{where} · {item['score']} · "
              f"{item['title'][:60] or item['url']}")

        # An evergreen candidate is drafted from its brief alone. Its Source line
        # names a general reference rather than a report of one result, and
        # fetching that is what produced the two wrong drafts described above.
        if args.evergreen is not None:
            article, page, warning = "", "", None
        else:
            article, page, warning = fetch_article(item["url"])

        # The headline names the post file and goes into the prompt. A --url
        # draft has no feed headline, so it takes the publisher's own.
        if not item["title"]:
            item["title"] = page_title(page) or item["url"]
        if warning:
            # Only a feed item has a summary to fall back to; a --url draft that
            # cannot fetch has nothing, and the guard below stops it.
            print(f"  warning: {warning} — "
                  + ("drafting from the feed summary, so " if item["summary"] else "")
                  + "check the slides against the source before posting")

        # A feed item always carries a summary, so a blocked fetch still leaves
        # the model something true to work from. A --url draft does not: with the
        # page gone there is nothing but the URL, and the model answers from
        # memory in the confident voice of the prompt. On the tides candidate
        # that produced the textbook two-bulge myth the post exists to debunk —
        # the exact inversion of the hook. Refuse instead.
        if not article and not item["summary"]:
            sys.exit(f"No source text: {item['url']} gave nothing readable. "
                     "Drafting from a URL alone makes the model invent the "
                     "content, so this is a stop. Use a source that is not "
                     "behind a bot check, or put the passage in the sheet as "
                     "the summary and draft that row.")

        paper, paper_warning = resolve_paper(page)
        if paper_warning:
            print(f"  warning: {paper_warning}")
        elif paper:
            print(f"  paper: {citation(paper) or paper['doi']}  [{paper['doi']}]")
            if not paper["abstract"]:
                print("  warning: Crossref has no abstract for that DOI — the "
                      "attribution is the paper's, the slides are the coverage's, "
                      "so check the mechanism before posting")

        settled = {"row": row_number, "item": item, "article": article,
                   "paper": paper}

        # A Signal picks five from a queue of a thousand, so it can afford to
        # want every item labelled by Crossref or by its host rather than by
        # the model. A Drop cannot: it must draft the row it was handed, and
        # its own peer_reviewed comes back in the reply. That is the whole
        # difference, and it is why this is a skip rather than a stop — the
        # row stays queued, because an unresolvable paper is still a fine
        # Drop tomorrow.
        if labelled_only and peer_review_flag(paper, item["url"]) is None:
            print(f"  skipping {where}: no DOI resolved and "
                  f"{outlet(item['url'])} is not a preprint host, so nothing "
                  f"but the model could label it peer-reviewed")
            if row_number is not None:
                skipped.add(row_number)
            rejected += 1
            check_budget(rejected, wanted)
            continue

        covered = already_covered(paper, item["url"], seen)

        if not covered:
            yield settled
            found += 1
            # Taken, not rejected: it must not come back on the next pass of
            # a Signal, and it is not a duplicate so it does not count as one.
            if row_number is not None:
                skipped.add(row_number)
            continue

        # An evergreen candidate is matched on its URL alone — see
        # covered_papers — and the queue keeps a subject listed after it has
        # been posted, so a hit here is the expected case rather than a
        # surprise. Walking on costs nothing: this path fetches no page and
        # calls no API, so there is no budget to spend and no cap to respect.
        if auto_evergreen:
            print(f"  skipping evergreen #{item['rank']}: {covered} already "
                  f"covers it")
            skipped_ranks.add(item["rank"])
            continue

        # A --row, a --url and a numbered evergreen candidate were all chosen
        # by a person. Say the post exists and draft it anyway: overriding is
        # the point of naming a candidate by hand.
        if row_number is None or args.row:
            print(f"  warning: {covered} already covers this")
            yield settled
            found += 1
            continue

        # `paper` is None when the match came from the URL rather than from a
        # resolved DOI, which is why this names the post and not the citation.
        print(f"  skipping row {row_number}: {covered} already covers "
              f"{citation(paper) if paper else item['url']}")
        if not args.dry_run:
            worksheet.update_cell(row_number, col["status"] + 1, "duplicate")
        skipped.add(row_number)
        rejected += 1
        check_budget(rejected, wanted)


def main() -> int:
    ap = argparse.ArgumentParser()
    picked = ap.add_mutually_exclusive_group()
    picked.add_argument("--row", type=int, help="draft this sheet row instead")
    picked.add_argument("--url", help="draft this page instead of a sheet row")
    picked.add_argument("--evergreen", type=int, nargs="?", const=0, metavar="N",
                        help="draft from docs/evergreen_queue.md: the "
                             "highest-scoring candidate, or candidate N")
    picked.add_argument("--signal", type=int, nargs="?", const=SIGNAL_ITEMS,
                        metavar="N",
                        help=f"draft a Signal — the weekly roundup — from the "
                             f"top {SIGNAL_ITEMS} queued rows, or the top N")
    picked.add_argument("--reject", type=Path, metavar="POST",
                        help="move a waiting draft to posts/rejected/ and "
                             "draft nothing — redraft.yml's first step")
    ap.add_argument("--reason", default="",
                    help="with --reject: why, kept for learn.py")
    ap.add_argument("--dry-run", action="store_true",
                    help="print the JSON without writing or marking the row")
    args = ap.parse_args()

    # Before llm.config() and the sheet: rejecting needs neither.
    if args.reject:
        dest = reject(args.reject, args.reason, date.today().isoformat())
        print(f"Rejected {args.reject} → {dest}")
        return 0

    if args.signal is not None and args.signal < 2:
        sys.exit(f"--signal {args.signal} is not a roundup. "
                 f"docs §1 says five items; two is the fewest that reads as "
                 f"a list.")

    api_key, model = llm.config()

    # Read once, before the loop: what posts/ already covers.
    seen = covered_papers()

    # Neither of the off-sheet paths has a row to mark afterwards, so neither
    # opens the sheet — which also means they need no Google credentials.
    worksheet, rows, col = None, [], {}
    if args.evergreen is None and not args.url:
        worksheet = open_sheet()
        rows = worksheet.get_all_values()
        if not rows:
            sys.exit("The sheet is empty. Run `python src/ingest.py` first.")
        col = {name: rows[0].index(name) for name in COLUMNS if name in rows[0]}

    wanted = args.signal or 1
    picks = list(settled_candidates(args, rows, col, worksheet, seen, wanted,
                                    labelled_only=bool(args.signal)))

    if args.signal:
        reply = llm.generate(
            SIGNAL_PROMPT.format(count=len(picks), more=len(picks) - 1,
                                 hook_limit=HOOK_WORD_LIMIT,
                                 claim_limit=CLAIM_WORD_LIMIT,
                                 sources=signal_sources(picks)),
            api_key, model, temperature=0.4)
        post = validate_signal(parsed(reply), picks)
        title = f"signal-week-{date.today().isocalendar().week:02d}"
    else:
        pick = picks[0]
        item, paper = pick["item"], pick["paper"]
        reply = llm.generate(
            PROMPT.format(hook_limit=HOOK_WORD_LIMIT, word_limit=WORD_LIMIT,
                          source=item["source"], title=item["title"],
                          url=item["url"],
                          text=source_text(paper, pick["article"],
                                           item["summary"])),
            api_key, model, temperature=0.4)
        post = validate(parsed(reply), item, paper)
        title = slugify(item["title"])

    print(json.dumps(post, indent=2, ensure_ascii=False))

    marks = [p["row"] for p in picks if p["row"] is not None]
    if args.dry_run:
        print("\nDry run — nothing written"
              + (f", {len(marks)} row(s) left queued" if marks else ""))
        return 0

    POSTS_DIR.mkdir(exist_ok=True)
    out = POSTS_DIR / f"{date.today():%Y-%m-%d}-{title}.json"
    out.write_text(json.dumps(post, indent=2, ensure_ascii=False) + "\n")

    # Mark the rows so the next run picks different stories. An evergreen
    # draft has no row to mark; the queue doc is edited by hand at the gate.
    for row_number in marks:
        worksheet.update_cell(row_number, col["status"] + 1, "drafted")

    print(f"\nWrote {out.relative_to(REPO_ROOT)}")
    print(f"Render it:  python src/render.py {out.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
