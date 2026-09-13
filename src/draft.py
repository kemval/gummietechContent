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
from urllib.parse import quote

import requests

import llm                       # forwards to gemini or groq per LLM_PROVIDER
from ingest import COLUMNS, open_sheet
from render import COLORWAYS, DEFAULT_COLORWAY, HOOK_WORD_LIMIT, WORD_LIMIT
from verify_feeds import HEADERS, TIMEOUT

REPO_ROOT = Path(__file__).resolve().parent.parent
POSTS_DIR = REPO_ROOT / "posts"

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
DOI_RE = re.compile(r"10\.\d{4,9}/[^\s\"'<>&)\]]+", re.I)
META_DOI_RE = re.compile(r"<meta[^>]*citation_doi[^>]*>", re.I)
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


def find_doi(page: str) -> str | None:
    """
    The DOI of the paper a page is about, or None.

    Three passes, most trustworthy first: the publisher's own citation_doi
    meta tag, then the first DOI after a journal-reference heading, then the
    first DOI anywhere. The middle pass is what keeps an aggregator's
    related-stories rail from supplying somebody else's paper.
    """
    meta = META_DOI_RE.search(page)
    if meta:
        content = CONTENT_RE.search(meta.group(0))
        if content:
            found = DOI_RE.search(content.group(1))
            if found:
                return found.group(0).rstrip(".,;:'\"")

    lowered = page.lower()
    for cue in DOI_CUES:
        at = lowered.find(cue)
        if at != -1:
            found = DOI_RE.search(page, at)
            if found:
                return found.group(0).rstrip(".,;:'\"")

    found = DOI_RE.search(page)
    return found.group(0).rstrip(".,;:'\"") if found else None


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


def resolve_paper(page: str) -> tuple[dict | None, str | None]:
    """Return (facts, warning) for the paper a page is covering."""
    if not page:
        return None, None                     # fetch already warned
    doi = find_doi(page)
    if not doi:
        return None, ("no DOI on the page — drafting from the coverage alone, "
                      "so check the authors and the mechanism against the paper")
    work, warning = fetch_crossref(doi)
    if work is None:
        return None, f"{warning} — drafting from the coverage alone"
    return paper_facts(work), None


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


def validate(post: dict, url: str, paper: dict | None) -> dict:
    """Fill the fields we own, then refuse anything render.py would reject."""
    post["source_url"] = url                  # never the model's version

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

    article, page, warning = fetch_article(item["url"])
    if warning:
        print(f"  warning: {warning} — drafting from the feed summary, so "
              "check the slides against the source before posting")

    paper, paper_warning = resolve_paper(page)
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

    post = validate(post, item["url"], paper)
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
