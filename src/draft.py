#!/usr/bin/env python3
"""
Layer 3: turn the top queued item into a post JSON that render.py accepts.

Takes the highest-scoring row with status "queued", fetches the source
article, resolves the paper behind it, and asks the LLM for the strict JSON
contract in CLAUDE.md. Writes posts/<date>-<slug>.json and marks the row
"drafted".

Usage:
    python src/draft.py
    python src/draft.py --row 47            # draft a specific sheet row
    python src/draft.py --url https://...   # draft an evergreen source
    python src/draft.py --dry-run           # print the JSON, write nothing

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
from datetime import date
from pathlib import Path
from urllib.parse import quote, urlparse

import requests

import llm                       # forwards to gemini or groq per LLM_PROVIDER
from ingest import COLUMNS, open_sheet
from render import COLORWAYS, DEFAULT_COLORWAY, HOOK_WORD_LIMIT, WORD_LIMIT
from verify_feeds import HEADERS, TIMEOUT

REPO_ROOT = Path(__file__).resolve().parent.parent
POSTS_DIR = REPO_ROOT / "posts"
EVERGREEN_QUEUE = REPO_ROOT / "docs" / "evergreen_queue.md"

ARTICLE_CHARS = 6000
ABSTRACT_CHARS = 4000

# peer_reviewed is False for these no matter what Crossref or the model says.
PREPRINT_HOSTS = ("arxiv.org", "biorxiv.org", "medrxiv.org", "chemrxiv.org",
                  "ssrn.com", "researchsquare.com", "preprints.org",
                  "osf.io", "hal.science")

REQUIRED = ["post_type", "domain", "hook", "what_happened", "why_it_matters",
            "the_catch", "caption", "alt_text", "attribution"]

PARA_RE = re.compile(r"<p[^>]*>(.*?)</p>", re.S | re.I)
SCRIPT_RE = re.compile(r"<(script|style)[^>]*>.*?</\1>", re.S | re.I)
TAG_RE = re.compile(r"<[^>]+>")

CROSSREF_API = "https://api.crossref.org/works/"
# Crossref asks for a contact address in the User-Agent. A project URL is
# enough, and it is what keeps us in the polite pool rather than the
# anonymous one that gets throttled without warning.
CROSSREF_HEADERS = {
    "User-Agent": ("gummietech-pipeline/1.0 "
                   "(+https://kemval.github.io/gummietechContent/)"),
    "Accept": "application/json",
}

# A DOI has no reserved terminator, so the trailing character class is a trim
# against surrounding markup and punctuation, not a parse of the DOI itself.
# ? and # are in it because a DOI is usually scraped out of an href, where a
# query string or fragment would otherwise be swallowed whole: the citation
# link .../10.1038/d41586-026-02895-6?format=refman yields a DOI that 404s at
# Crossref, and the draft silently falls back to the coverage.
DOI_RE = re.compile(r"10\.\d{4,9}/[^\s\"'<>&)\]?#]+", re.I)
META_DOI_RE = re.compile(r"<meta[^>]*citation_doi[^>]*>", re.I)
OG_TITLE_RE = re.compile(r"<meta[^>]*og:title[^>]*>", re.I)
TITLE_TAG_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.S | re.I)
CONTENT_RE = re.compile(r"content=[\"']([^\"']+)[\"']", re.I)

# Aggregators park the real citation behind one of these headings. Ordered
# most specific first, because a page's related-stories rail carries other
# papers' DOIs and a bare "doi:" can land in it.
DOI_CUES = ("journal reference", "more information", "cite this",
            "citation", "doi:")

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
- Where a PAPER section appears below, it outranks the coverage. Coverage \
simplifies mechanisms, overstates what a result overturns, and quotes \
researchers who did not write the paper. Never credit the work to a name \
that is not in the paper's author list, and never describe the method in \
terms the paper contradicts.
- the_catch is the credibility slide. Prefer a limitation the paper states \
about itself. A weak but true limitation beats a strong invented one.

Source: {source}
Title: {title}
URL: {url}

{text}"""


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


def fetch_article(url: str) -> tuple[str, str, str | None]:
    """
    Return (text, page_html, warning). Falls back to empty strings when the
    publisher blocks the fetch — the caller then drafts from the feed summary
    alone, which is worth saying out loud rather than papering over.
    """
    try:
        resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT,
                            allow_redirects=True)
    except requests.exceptions.RequestException as exc:
        return "", "", f"could not fetch the article ({type(exc).__name__})"

    if resp.status_code >= 400:
        return "", "", f"publisher returned HTTP {resp.status_code}"

    body = SCRIPT_RE.sub(" ", resp.text)
    paragraphs = []
    for chunk in PARA_RE.findall(body):
        text = html.unescape(TAG_RE.sub(" ", chunk))
        text = " ".join(text.split())
        if len(text) > 80:                    # skip nav, captions and bylines
            paragraphs.append(text)

    article = "\n\n".join(paragraphs)[:ARTICLE_CHARS]
    if len(article) < 400:
        return article, resp.text, "article body was too short to use much of"
    return article, resp.text, None


def _trimmed_doi(found: re.Match[str] | None) -> str | None:
    """A matched DOI with trailing sentence punctuation removed, or None."""
    return found.group(0).rstrip(".,;:'\"") if found else None


def doi_candidates(page: str) -> list[str]:
    """
    Every DOI on the page, most trustworthy first.

    The same three passes as before — the publisher's citation_doi meta tag,
    then a DOI after a journal-reference heading, then everything in document
    order — but collecting all of them instead of returning the first. A news
    story's meta tag names the story itself, so the leading candidate is
    routinely the coverage; resolve_paper walks the list until one turns out
    to be a paper. The pass order is what keeps an aggregator's related-
    stories rail from jumping the queue.
    """
    found: list[str] = []

    def add(doi: str | None) -> None:
        if doi and doi not in found:
            found.append(doi)

    meta = META_DOI_RE.search(page)
    if meta:
        content = CONTENT_RE.search(meta.group(0))
        if content:
            add(_trimmed_doi(DOI_RE.search(content.group(1))))

    lowered = page.lower()
    for cue in DOI_CUES:
        at = lowered.find(cue)
        if at != -1:
            add(_trimmed_doi(DOI_RE.search(page, at)))

    for match in DOI_RE.finditer(page):
        add(_trimmed_doi(match))

    return found


def fetch_crossref(doi: str) -> tuple[dict | None, str | None]:
    """Return (work, warning) for a DOI. Crossref is free and needs no key."""
    try:
        resp = requests.get(CROSSREF_API + quote(doi, safe="/"),
                            headers=CROSSREF_HEADERS, timeout=TIMEOUT)
    except requests.exceptions.RequestException as exc:
        return None, f"Crossref lookup failed ({type(exc).__name__})"

    if resp.status_code == 404:
        return None, f"Crossref has no record for {doi}"
    if resp.status_code >= 400:
        return None, f"Crossref returned HTTP {resp.status_code} for {doi}"

    try:
        return resp.json()["message"], None
    except (ValueError, KeyError):
        return None, f"Crossref returned an unreadable record for {doi}"


def venue(work: dict) -> str:
    """
    Where the work appeared. Preprints carry no container-title, so fall back
    to the depositing server — "Surname et al. (2025)" with no venue at all
    reads like a citation someone forgot to finish.
    """
    journal = next((t for t in work.get("container-title") or [] if t), "")
    if journal:
        return journal
    for inst in work.get("institution") or []:
        if inst.get("name"):
            return inst["name"]
    return ""


def paper_facts(work: dict) -> dict:
    """Flatten a Crossref work down to the fields a post actually needs."""
    authors = [a for a in work.get("author") or []
               if a.get("family") or a.get("name")]

    # Array order is authoritative, but honour an explicit sequence marker
    # if a publisher deposited the list out of order.
    lead = next((a for a in authors if a.get("sequence") == "first"), None)
    if lead is not None and authors and authors[0] is not lead:
        authors = [lead] + [a for a in authors if a is not lead]
    surnames = [a.get("family") or a.get("name", "") for a in authors]

    year = None
    for key in ("published", "issued", "posted", "published-print",
                "published-online"):
        parts = (work.get(key) or {}).get("date-parts") or []
        if parts and parts[0] and parts[0][0]:
            year = parts[0][0]
            break

    # Crossref carries abstracts as JATS XML, and many publishers deposit the
    # "Abstract" heading inside the body.
    abstract = work.get("abstract") or ""
    if abstract:
        abstract = " ".join(html.unescape(TAG_RE.sub(" ", abstract)).split())
        abstract = re.sub(r"^abstract[:\s]*", "", abstract, flags=re.I)

    return {
        "doi": work.get("DOI", ""),
        "title": next((t for t in work.get("title") or [] if t), ""),
        "authors": [s for s in surnames if s],
        "journal": venue(work),
        "year": year,
        "abstract": abstract[:ABSTRACT_CHARS],
        "is_preprint": (work.get("type") == "posted-content"
                        or work.get("subtype") == "preprint"),
    }


# A news story carries its own DOI and Crossref files it as a "journal-article"
# exactly like a paper, so the record type cannot tell them apart. What gives
# the coverage away is that its record describes the page being read rather
# than the work the page is about. Matching titles alone are not proof: a
# journal feed links straight at the paper, where the titles match and the
# record is precisely the source wanted. The absent abstract is the other
# half — a news record has none, and without one a resolved DOI contributes
# nothing but an attribution anyway.
# Each candidate costs a Crossref round trip, and a reference list can be
# long. Six is enough for a story's own DOI plus the first few things it
# cites, which is where the covered paper sits.
MAX_CROSSREF_LOOKUPS = 6
TITLE_OVERLAP = 0.9
MIN_TITLE_WORDS = 4


def venue_key(name: str) -> str:
    """A venue name flattened for comparison: 'Physics World' -> physicsworld."""
    return re.sub(r"[^a-z0-9]+", "", name.lower())


# The title check below only fires when the record's title still resembles the
# headline we ingested. A magazine's print title often does not — Scientific
# American filed "See how gravitational waves warp time and space" as "Ripples
# in Space and Time" — and nothing structural catches the difference, because
# Crossref does not distinguish popular science from research. That feature is
# a "journal-article" with an ISSN, a volume and a page, exactly like a paper,
# and every field that looks like a tell was checked and is not one:
#
#   - no abstract          modern Nature and Cell papers deposit none either
#   - no references        Nature's own news pieces deposit 1-6, while
#                          genuine Nature letters deposit 0
#   - venue matches host   so does a journal's own site, which is the case
#                          worth keeping
#
# So the outlet has to be named. These mint their own DOIs and are not
# research venues, so a record here is the coverage however it is filed —
# unconditionally, since Physics World deposits an abstract for every article
# and an abstract would otherwise wave it through as the primary source.
# Crediting one puts a magazine's staff writers on the slide as the
# researchers. Nature News is the gap this cannot close: it is filed under
# container-title "Nature" like the papers, and only the title check catches
# it. Add an outlet when one appears; the symptom is an attribution naming a
# publication where a lab should be.
COVERAGE_VENUES = frozenset(map(venue_key, (
    "Scientific American",
    "New Scientist",
    "Physics World",
    "IEEE Spectrum",
    "Physics Today",
    "American Scientist",
)))


def title_words(title: str) -> set[str]:
    """The comparable words of a title, case and punctuation discarded."""
    return set(re.sub(r"[^a-z0-9 ]+", " ", title.lower()).split())


def same_title(a: str, b: str) -> bool:
    """
    Whether two titles name the same work.

    Containment rather than equality, because a headline picks up the
    publisher's name on the way out ("... | Nature") and a paper's own title
    picks up a subtitle. Coverage of a paper never overlaps its title this
    heavily — it is written to be read by people who have not read it.
    """
    x, y = title_words(a), title_words(b)
    if len(x) < MIN_TITLE_WORDS or len(y) < MIN_TITLE_WORDS:
        return False            # too short to tell a match from a coincidence
    return len(x & y) / min(len(x), len(y)) >= TITLE_OVERLAP


def is_coverage(facts: dict, headline: str) -> bool:
    """
    Whether a Crossref record is the story being read rather than the paper.

    A record from a popular-science outlet is coverage outright — see
    COVERAGE_VENUES for why nothing about the record itself can say so.

    Otherwise both halves are needed. A journal feed links straight at the
    paper, where the titles match and the record is the source wanted; an
    abstract is what tells that apart from a news item, which has none — and
    without one a resolved DOI contributes nothing downstream but an
    attribution anyway.
    """
    if venue_key(facts["journal"]) in COVERAGE_VENUES:
        return True
    return not facts["abstract"] and same_title(facts["title"], headline)


def resolve_paper(page: str, headline: str) -> tuple[dict | None, str | None]:
    """Return (facts, warning) for the paper a page is covering."""
    if not page:
        return None, None                     # fetch already warned
    queue = doi_candidates(page)
    if not queue:
        return None, ("no DOI on the page — drafting from the coverage alone, "
                      "so check the authors and the mechanism against the paper")

    seen: set[str] = set()
    coverage: dict | None = None
    budget = MAX_CROSSREF_LOOKUPS

    while queue and budget > 0:
        doi = queue.pop(0)
        if doi in seen:
            continue
        seen.add(doi)
        budget -= 1

        work, warning = fetch_crossref(doi)
        if work is None:
            continue                          # dead DOI, try the next one

        facts = paper_facts(work)
        if not is_coverage(facts, headline):
            return facts, None

        # The story's own DOI. Its Crossref record lists what it cites, and a
        # news story cites the paper it covers — usually first, and reachable
        # even when the page itself is paywalled. Queued behind the remaining
        # on-page candidates, which are the better evidence when present.
        if coverage is None:
            coverage = facts
            queue += [r["DOI"] for r in work.get("reference") or [] if r.get("DOI")]

    if coverage is not None:
        return None, ("every DOI here resolves to the story itself or to "
                      "nothing, and nothing it cites looks like the paper — "
                      "drafting from the coverage alone, so check the authors "
                      "and the mechanism against the paper")
    return None, ("no DOI on the page resolved at Crossref — drafting from "
                  "the coverage alone, so check the authors and the mechanism "
                  "against the paper")


def citation(facts: dict) -> str:
    """'Denton et al., The Astrophysical Journal Letters (2026)'."""
    names = facts["authors"]
    if not names:
        return ""
    if len(names) == 1:
        who = names[0]
    elif len(names) == 2:
        who = f"{names[0]} and {names[1]}"
    else:
        who = f"{names[0]} et al."
    if facts["journal"]:
        who = f"{who}, {facts['journal']}"
    if facts["year"]:
        who = f"{who} ({facts['year']})"
    return who


def source_text(facts: dict | None, article: str, summary: str) -> str:
    """The text block the model drafts from, paper first when we have one."""
    coverage = article or summary
    if not facts or not facts["abstract"]:
        return coverage

    paper = ["PAPER — the primary source. Where this and the coverage "
             "disagree, the paper is right."]
    if facts["title"]:
        paper.append(f"Title: {facts['title']}")
    if facts["authors"]:
        paper.append("Authors, in order: " + ", ".join(facts["authors"]))
    if facts["journal"]:
        paper.append(f"Journal: {facts['journal']}")
    paper.append(f"Abstract: {facts['abstract']}")

    return ("\n".join(paper)
            + "\n\nCOVERAGE — context and plain-language framing only. Anyone "
              "quoted here may not be an author.\n" + coverage)


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


def evergreen_candidate(rank: int) -> dict:
    """
    A row from the evergreen queue as a draftable item, rank 0 meaning the
    highest-scoring one. The brief becomes the summary, which is what the
    model drafts from, and the Source line's first link becomes source_url.
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
        picked = heads[0]                  # the file is written in score order

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
        "source": f"evergreen queue #{picked['rank']}",
        "title": picked["title"].strip(),
        "summary": "\n".join(lines),
        "score": picked["score"],
        "colorway": picked["colorway"],
        "peer_reviewed": "peer_reviewed: false" not in body.lower(),
    }


def validate(post: dict, item: dict, paper: dict | None) -> dict:
    """Fill the fields we own, then refuse anything render.py would reject."""
    url = item["url"]
    post["source_url"] = url                  # never the model's version

    # An evergreen row settles the preprint flag itself — see
    # evergreen_candidate for why the model cannot. Retraction has no field in
    # the contract at all; flag that one by hand at the gate.
    if "peer_reviewed" in item:
        post["peer_reviewed"] = item["peer_reviewed"]

    # Attribution and the preprint flag come from Crossref when the paper
    # resolved. Both are fields the model gets wrong in a repeatable way:
    # coverage quotes whoever gave the interview, who may be the senior
    # author or — as in the Moon-formation draft that prompted this — an
    # outside commentator who did not write the paper at all.
    if paper:
        cite = citation(paper)
        if cite:
            if post.get("attribution") and post["attribution"] != cite:
                print(f"  attribution: model wrote {post['attribution']!r}, "
                      f"using Crossref's {cite!r}")
            post["attribution"] = cite
        post["peer_reviewed"] = not paper["is_preprint"]

    # A preprint host can only ever force the flag down. A reader on arxiv.org
    # is reading a preprint whatever Crossref says about a later version.
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
    picked = ap.add_mutually_exclusive_group()
    picked.add_argument("--row", type=int, help="draft this sheet row instead")
    picked.add_argument("--url", help="draft this page instead of a sheet row")
    picked.add_argument("--evergreen", type=int, nargs="?", const=0, metavar="N",
                        help="draft from docs/evergreen_queue.md: the "
                             "highest-scoring candidate, or candidate N")
    ap.add_argument("--dry-run", action="store_true",
                    help="print the JSON without writing or marking the row")
    args = ap.parse_args()

    api_key, model = llm.config()

    # Neither of the off-sheet paths has a row to mark afterwards, so neither
    # opens the sheet — which also means they need no Google credentials.
    if args.evergreen is not None:
        worksheet, row_number = None, None
        item = evergreen_candidate(args.evergreen)
    elif args.url:
        worksheet, row_number = None, None
        item = {"url": args.url, "source": outlet(args.url),
                "title": "", "summary": "", "score": "—"}
    else:
        worksheet = open_sheet()
        rows = worksheet.get_all_values()
        if not rows:
            sys.exit("The sheet is empty. Run `python src/ingest.py` first.")

        col = {name: rows[0].index(name) for name in COLUMNS if name in rows[0]}
        row_number, item = pick_row(rows, col, args.row)

    print(f"Drafting {f'row {row_number}' if row_number else item['source']} · "
          f"{item['score']} · {item['title'][:60] or item['url']}")

    # An evergreen candidate is drafted from its brief alone. Its Source line
    # names a general reference rather than a report of one result, and
    # fetching that is what produced the two wrong drafts described above.
    if args.evergreen is not None:
        article, page, warning = "", "", None
    else:
        article, page, warning = fetch_article(item["url"])

    # resolve_paper matches a Crossref title against the headline to spot a
    # record that is the page itself. A --url draft has no feed headline, so
    # it takes the publisher's own.
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

    paper, paper_warning = resolve_paper(page, item["title"])
    if paper_warning:
        print(f"  warning: {paper_warning}")
    elif paper:
        print(f"  paper: {citation(paper) or paper['doi']}  [{paper['doi']}]")
        if not paper["abstract"]:
            print("  warning: Crossref has no abstract for that DOI — the "
                  "attribution is the paper's, the slides are the coverage's, "
                  "so check the mechanism before posting")

    reply = llm.generate(
        PROMPT.format(hook_limit=HOOK_WORD_LIMIT, word_limit=WORD_LIMIT,
                      source=item["source"], title=item["title"],
                      url=item["url"],
                      text=source_text(paper, article, item["summary"])),
        api_key, model, temperature=0.4)

    try:
        post = json.loads(reply.strip())
    except json.JSONDecodeError:
        sys.exit(f"The model did not return JSON:\n{reply[:400]}\nRe-run to try again.")

    post = validate(post, item, paper)
    print(json.dumps(post, indent=2, ensure_ascii=False))

    if args.dry_run:
        print("\nDry run — nothing written"
              + (", row left queued" if row_number else ""))
        return 0

    POSTS_DIR.mkdir(exist_ok=True)
    out = POSTS_DIR / f"{date.today():%Y-%m-%d}-{slugify(item['title'])}.json"
    out.write_text(json.dumps(post, indent=2, ensure_ascii=False) + "\n")

    # Mark the row so the next run picks a different story. An evergreen
    # draft has no row to mark; the queue doc is edited by hand at the gate.
    if row_number is not None:
        worksheet.update_cell(row_number, col["status"] + 1, "drafted")

    print(f"\nWrote {out.relative_to(REPO_ROOT)}")
    print(f"Render it:  python src/render.py {out.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
