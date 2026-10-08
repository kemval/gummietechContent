#!/usr/bin/env python3
"""
The paper behind a story: fetch the page, find its DOI, ask Crossref who
wrote it, and build the text a post is drafted from with the paper first.

Most feeds are news coverage, not papers. Coverage simplifies the mechanism,
overstates what the result overturns, and quotes whoever gave the interview —
who is often a senior author and sometimes not an author at all. So draft.py
pulls the DOI off the page through this module and hands the model the
abstract as the primary source, with the coverage demoted to context.

Every step degrades rather than failing: a blocked fetch, a page with no DOI
or a Crossref outage returns a warning, and the caller drafts from the
coverage alone. Split out of draft.py on 2026-09-28; the reasoning behind
each rule is in the comments beside it and in docs/decisions/paper-first.md
and docs/decisions/dedup.md.
"""

from __future__ import annotations

import html
import re
from datetime import date
from urllib.parse import quote

import requests

from verify_feeds import HEADERS, TIMEOUT


ARTICLE_CHARS = 6000
ABSTRACT_CHARS = 4000
# A collaboration paper lists thousands of authors. On 2026-10-02 an ATLAS
# paper's full list made the draft prompt ~35k characters, past Groq's free
# 8000 tokens-per-minute cap (HTTP 413), and the day went undrafted. The
# prompt only needs enough names to check who is quoted; citation() uses
# the first one and still reads the whole list.
AUTHORS_IN_PROMPT = 30

# A "run it" post's README, cut short for the same 8000 tokens-per-minute
# reason as AUTHORS_IN_PROMPT: it rides on top of the abstract and the
# coverage. The setup a reader needs is near the top of a README.
README_CHARS = 2500

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
CONTENT_RE = re.compile(r"content=[\"']([^\"']+)[\"']", re.I)
# Aggregators park the real citation behind one of these headings. Ordered
# most specific first, because a page's related-stories rail carries other
# papers' DOIs and a bare "doi:" can land in it.
DOI_CUES = ("journal reference", "more information", "cite this",
            "citation", "doi:")
# The last three are weak on a page with a reference list: it says "doi:"
# before every entry, and its "cite this" is the page citing itself — qorl's
# "Please cite this work as: Bansal, Rohan" carries no DOI, so the search ran
# on to the first reference. See BIBLIOGRAPHY_DOIS for when they stop counting.
WEAK_DOI_CUES = ("cite this", "citation", "doi:")

# A page carrying this many distinct DOIs is a reference list, and then it is
# usually the work itself — a blog post, an essay, a paper — citing others,
# not coverage of one of them. On 2026-09-28 rohanbansal.com/qorl, the
# author's own write-up with a reference list, had its first entry, Leis et
# al. (2015), credited on the slides. The year test cannot save that case:
# the same list cited a 2026 arXiv preprint. So on such a page only the meta
# tag and the coverage cues ("journal reference", "more information") name a
# paper, and mentions are not guessed from. Coverage names its paper with one
# DOI or a cue; the Research Briefing GUESS_MAX_AGE describes carried five
# references and no paper at all.
BIBLIOGRAPHY_DOIS = 4

# How far past a weak cue its DOI may sit, in characters of raw HTML. A
# citation box puts the DOI right after the word; a page that merely says
# "citation" somewhere does not. On 2026-10-07 openai.com/index/gpt-6-astra
# said "citation" in its markup and carried one DOI, footnote 7, 135k
# characters further down: a 2023 musicology dataset the launch was
# evaluated on. Below BIBLIOGRAPHY_DOIS, so the weak cue still counted, and
# the search ran on to that footnote and named it the paper — the draft
# credited "Gotham et al., Digital Libraries for Musicology (2023)" for
# OpenAI's model. Lab announcements reach the queue since the relevance
# lift, and they cite in footnotes, not in citation boxes. Generous for
# markup between the word and the link; nowhere near a page away.
WEAK_CUE_REACH = 2000


def paragraphs(page: str) -> list[str]:
    """The <p> text of a page, minus scripts and the short ones — nav,
    captions and bylines."""
    found = []
    for chunk in PARA_RE.findall(SCRIPT_RE.sub(" ", page)):
        text = " ".join(html.unescape(TAG_RE.sub(" ", chunk)).split())
        if len(text) > 80:
            found.append(text)
    return found


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

    article = "\n\n".join(paragraphs(resp.text))[:ARTICLE_CHARS]
    if len(article) < 400:
        return article, resp.text, "article body was too short to use much of"
    return article, resp.text, None


def fetch_readme(repo: str) -> tuple[str, str | None]:
    """Return (readme, warning) for a repository code_link() found.

    The README is what a "run it" post's try_it slide is written from and
    what fact-check reads it against, so it is the repo's own file, never
    the model's memory of the project. GitHub's API returns the README
    whatever its name or branch (60 unauthenticated calls an hour — one a
    draft); Hugging Face serves it raw from main. GitLab is not tried: no
    paper in the feeds has linked one yet. Any failure is a warning, and the
    caller drafts a plain Drop instead.
    """
    parts = repo.split("://", 1)[-1].split("/")
    host, path = parts[0].removeprefix("www.").lower(), "/".join(parts[1:])
    if host == "github.com":
        url = f"https://api.github.com/repos/{path}/readme"
        headers = {**HEADERS, "Accept": "application/vnd.github.raw"}
    elif host == "huggingface.co":
        url, headers = f"https://huggingface.co/{path}/raw/main/README.md", HEADERS
    else:
        return "", f"no README fetch for {host} — drafting a plain Drop"
    try:
        resp = requests.get(url, headers=headers, timeout=TIMEOUT)
    except requests.exceptions.RequestException as exc:
        return "", (f"could not fetch the README ({type(exc).__name__}) — "
                    "drafting a plain Drop")
    if resp.status_code >= 400:
        return "", (f"README fetch returned HTTP {resp.status_code} — "
                    "drafting a plain Drop")
    text = resp.text.strip()
    if len(text) < 200:
        return "", "the README is too short to say how to run it — drafting a plain Drop"
    return text[:README_CHARS], None


def _trimmed_doi(found: re.Match[str] | None) -> str | None:
    """A matched DOI with trailing sentence punctuation removed, or None."""
    return found.group(0).rstrip(".,;:'\"") if found else None


def doi_candidates(page: str) -> tuple[list[str], list[str]]:
    """
    The DOIs on a page, split by what the page claims about them.

    `named` are the ones the page states are the work it reports: the
    publisher's citation_doi meta tag, then the first DOI after a
    journal-reference heading. A news story's meta tag names the story
    itself, so the leading named candidate is routinely the coverage;
    resolve_paper walks past it.

    `mentioned` is every other DOI in document order. On a news page that is
    the reference list, and a reference list is what a story cites rather
    than what it is about — which is why resolve_paper will not credit one
    without corroboration. Kept because an aggregator that uses no cue
    heading leaves the paper's DOI nowhere else.

    A page with BIBLIOGRAPHY_DOIS or more is read as a reference list: the
    weak cues name nothing and `mentioned` is empty.
    """
    named: list[str] = []
    mentioned: list[str] = []

    def add(doi: str | None, into: list[str] | None = None) -> None:
        into = named if into is None else into
        if doi and doi not in named and doi not in mentioned:
            into.append(doi)

    meta = META_DOI_RE.search(page)
    if meta:
        content = CONTENT_RE.search(meta.group(0))
        if content:
            add(_trimmed_doi(DOI_RE.search(content.group(1))))

    every = {_trimmed_doi(m) for m in DOI_RE.finditer(page)}
    bibliography = len(every) >= BIBLIOGRAPHY_DOIS

    lowered = page.lower()
    for cue in DOI_CUES:
        if bibliography and cue in WEAK_DOI_CUES:
            continue
        at = lowered.find(cue)
        if at == -1:
            continue
        found = DOI_RE.search(page, at)
        if found and cue in WEAK_DOI_CUES and found.start() - at > WEAK_CUE_REACH:
            continue                          # a footnote, not this cue's DOI
        add(_trimmed_doi(found))

    if bibliography:
        return named, mentioned               # a reference list, not guesses

    for match in DOI_RE.finditer(page):
        add(_trimmed_doi(match), mentioned)

    return named, mentioned


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
# exactly like a paper, so nothing about the record's shape tells them apart.
# Only the identifier does — see COVERAGE_VENUES and NATURE_NEWS_DOI_RE.
# Each candidate costs a Crossref round trip, and a reference list can be
# long. Six is enough for a story's own DOI plus the first few things it
# cites, which is where the covered paper sits.
MAX_CROSSREF_LOOKUPS = 6


def venue_key(name: str) -> str:
    """A venue name flattened for comparison: 'Physics World' -> physicsworld."""
    return re.sub(r"[^a-z0-9]+", "", name.lower())


# Crossref does not distinguish popular science from research. A magazine
# feature is a "journal-article" with an ISSN, a volume and a page, exactly
# like a paper, and every field that looks like a tell was checked and is not
# one:
#
#   - no abstract          modern Nature and Cell papers deposit none either
#   - no references        Nature's own news pieces deposit 1-6, while
#                          genuine Nature letters deposit 0
#   - venue matches host   so does a journal's own site, which is the case
#                          worth keeping
#   - one author           so is a solo-authored paper
#
# So the outlet has to be named. These mint their own DOIs and are not
# research venues, so a record here is the coverage however it is filed —
# unconditionally, since Physics World deposits an abstract for every article
# and an abstract would otherwise wave it through as the primary source.
# Crediting one puts a magazine's staff writers on the slide as the
# researchers. Add an outlet when one appears; the symptom is an attribution
# naming a publication where a lab should be.
COVERAGE_VENUES = frozenset(map(venue_key, (
    "Scientific American",
    "New Scientist",
    "Physics World",
    "IEEE Spectrum",
    "Physics Today",
    "American Scientist",
)))


# Nature's own magazine — news, features, comment, careers — is the outlet
# COVERAGE_VENUES cannot name, because Crossref files it under container-title
# "Nature" like the papers. The DOI is what separates them: Springer Nature
# mints d-prefixed suffixes for editorial content (10.1038/d41586-026-02895-6,
# "'Multifunctional' brain implant translates speech and gestures in real
# time", by a reporter) and s-prefixed or legacy short ones for research
# (10.1038/s41586-026-10968-9, nmat4089). No research article carries a d.
NATURE_NEWS_DOI_RE = re.compile(r"^10\.1038/d\d{4,5}-", re.I)


def is_coverage(facts: dict) -> bool:
    """
    Whether a Crossref record is the story being read rather than the paper.

    Only the identifier can answer it; see COVERAGE_VENUES for why nothing
    about the record itself can.

    This also used to reject a record that carried no abstract and shared the
    headline we ingested, on the reasoning that a news item has neither an
    abstract nor a title distinct from the page's. Both halves are equally
    true of a paper read from its publisher's own feed: Nature deposits no
    abstracts at all, and a journal feed's headline *is* the paper's title.
    On 2026-09-18 that threw away 10.1038/s41586-026-10968-9 — the paper, on
    the paper's own page — walked into its reference list and credited the
    slides to the first thing it cited, Wegst et al. (2014), twelve years and
    one subject apart. A title that matches is evidence a record is the work,
    not evidence against it.
    """
    return (venue_key(facts["journal"]) in COVERAGE_VENUES
            or bool(NATURE_NEWS_DOI_RE.match(facts["doi"])))


# What a page merely mentions is only ever a guess at the paper, so it has to
# corroborate itself, and the one thing every candidate carries is a year. A
# story is drafted within days of the work it reports — the queue is scored
# and drafted the same week — while a reference list is years of background.
# One year of slack rather than none, because a story ingested in January
# covers a paper published in December.
#
# The case this is here for: nature.com/articles/d41586-026-02705-z is a
# Research Briefing whose paper is linked by URL and appears on the page as no
# DOI at all. Its five reference DOIs are all it mentions, and the first of
# them — Building and Environment (2012) — was about to be credited on the
# slides of a 2026 story about charged droplets.
GUESS_MAX_AGE = 1


def is_recent(facts: dict) -> bool:
    """Whether a record is new enough to be the paper a story is reporting."""
    return bool(facts["year"]) and facts["year"] >= date.today().year - GUESS_MAX_AGE


def resolve_paper(page: str) -> tuple[dict | None, str | None]:
    """Return (facts, warning) for the paper a page is covering."""
    if not page:
        return None, None                     # fetch already warned
    named, mentioned = doi_candidates(page)
    if not (named or mentioned) and DOI_RE.search(page):
        return None, ("every DOI on the page is in its reference list, so it "
                      "is the work itself rather than coverage of a paper — "
                      "credit its author, and check peer_reviewed by hand")
    if not (named or mentioned):
        return None, ("no DOI on the page — drafting from the coverage alone, "
                      "so check the authors and the mechanism against the paper")

    # (doi, named) — a named DOI is the page's own statement of what it
    # reports and is taken at its word; everything else has to be recent.
    queue = [(doi, True) for doi in named] + [(doi, False) for doi in mentioned]
    seen: set[str] = set()
    coverage: dict | None = None
    stale: dict | None = None
    budget = MAX_CROSSREF_LOOKUPS

    while queue and budget > 0:
        doi, was_named = queue.pop(0)
        if doi in seen:
            continue
        seen.add(doi)
        budget -= 1

        work, warning = fetch_crossref(doi)
        if work is None:
            continue                          # dead DOI, try the next one

        facts = paper_facts(work)
        if is_coverage(facts):
            # The story's own DOI. Its Crossref record lists what it cites,
            # and a news story cites the paper it covers — usually first, and
            # reachable even when the page itself is paywalled. Queued behind
            # the remaining on-page candidates, and as guesses: a reference
            # list read from the record is no better evidence than the same
            # list read off the page.
            if coverage is None:
                coverage = facts
                queue += [(r["DOI"], False)
                          for r in work.get("reference") or [] if r.get("DOI")]
            continue

        if was_named or is_recent(facts):
            return facts, None

        stale = stale or facts                # remember the first, to name it

    if stale is not None:
        return None, (f"every paper this page only mentions is older than "
                      f"the story — the first is {citation(stale)} — so they "
                      f"are what it cites, not what it reports. Drafting from "
                      f"the coverage alone, so check the authors and the "
                      f"mechanism against the paper")
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


# ---------------------------------------------------------------- the limits
#
# The catch is the slide a paper's abstract almost never supplies: abstracts
# sell the result, and the limits live in the discussion. On 2026-10-08 the
# nuclear-clock draft had only the abstract, and the model invented "not
# mini-scaled"; the paper's own limit — runs on different days agreed only to
# 5×10⁻¹³ — was in the body. So for the paper a Drop is drafted from, code
# reads the body and hands over only the sentences that state a limit.
#
# Only sentences, and few: Groq's free tier caps a request at 8000 tokens a
# minute (AUTHORS_IN_PROMPT above), the prompt without a source is ~2500, and
# a whole paper is 25–100k characters. LIMITS_CHARS keeps the worst case
# under the cap with room for the reply.
#
# Free and keyless, and it degrades like everything here: a publisher that
# refuses a bot (Wiley, Science and Elsevier did, measured 2026-10-08) or a
# paywall that serves only the abstract gives no sentences, and the draft is
# made from the abstract as before — where the prompt's empty catch takes over.
LIMITS_CHARS = 1500

# doi.org negotiates on Accept: HEADERS asks for RSS first, and a DOI asked
# that way is redirected to Crossref's metadata API (HTTP 406), not the paper.
PAGE_HEADERS = {**HEADERS, "Accept": "text/html,application/xhtml+xml"}

# arXiv's /abs/ page, where its DOIs land, is the abstract; /html/ is the
# paper, for every submission arXiv could convert.
ARXIV_DOI_RE = re.compile(r"^10\.48550/arxiv\.(.+)$", re.I)

# A sentence needs a LIMIT_RE cue to be picked; HEDGE_RE only ranks it.
# "uncertainty", "however" or "cannot" alone is not a limit — on 2026-10-08
# an arXiv paper *about* uncertainty, and full of proofs, filled the whole
# budget with its own topic.
LIMIT_RE = re.compile(
    r"\blimit(?:s|ed|ation|ations|ing)?\b|reproducib|caveat|drawback|"
    r"shortcoming|\bnot yet\b|remains? (?:unclear|unknown|to be|an open)|"
    r"future (?:work|studies|research|implementations)|"
    r"small sample|in mice\b|in vitro\b|in simulations?\b|"
    r"restricted to|only (?:one|two|three|a single|a small)\b",
    re.I)
HEDGE_RE = re.compile(
    r"uncertaint|\bhowever\b|\balthough\b|\bwas not\b|\bwere not\b|"
    r"\bdid not\b|\bonly\b|\bmay\b|\bcannot\b|\bcould not\b", re.I)
# Page furniture that says "limited" too: Nature's first paragraph is
# "a browser version with limited support for CSS".
FURNITURE_RE = re.compile(
    r"browser|cookie|javascript|subscri|sign in|log in|your institution|"
    r"permissions|reprints|copyright|creative commons|download pdf", re.I)
SENTENCE_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z])")


def full_text_url(doi: str) -> str:
    if arxiv := ARXIV_DOI_RE.match(doi):
        return f"https://arxiv.org/html/{arxiv.group(1)}"
    return "https://doi.org/" + quote(doi, safe="/")


def limit_sentences(page: str, abstract: str = "") -> str:
    """The sentences of a paper's body that state a limit, in reading order,
    up to LIMITS_CHARS. The ones with the most cues win the budget; the
    abstract's own sentences are left out, since the prompt already has it."""
    picked: list[tuple[int, int, str]] = []
    order = 0
    for para in paragraphs(page):
        if FURNITURE_RE.search(para):
            continue
        for sentence in SENTENCE_RE.split(para):
            order += 1
            limits = len(LIMIT_RE.findall(sentence))
            if limits and 40 < len(sentence) < 600 and sentence not in abstract:
                cues = 2 * limits + len(HEDGE_RE.findall(sentence))
                picked.append((cues, order, sentence))
    kept, used = [], 0
    for cues, order, sentence in sorted(picked, key=lambda p: (-p[0], p[1])):
        if used + len(sentence) > LIMITS_CHARS:
            continue
        kept.append((order, sentence))
        used += len(sentence) + 1
    return " ".join(sentence for _, sentence in sorted(kept))


def fetch_limits(facts: dict) -> tuple[str, str | None]:
    """Return (sentences, warning) from the body of the paper in `facts`."""
    url = full_text_url(facts["doi"])
    try:
        resp = requests.get(url, headers=PAGE_HEADERS, timeout=TIMEOUT,
                            allow_redirects=True)
    except requests.exceptions.RequestException as exc:
        return "", (f"could not read the paper's body ({type(exc).__name__}) "
                    "— the catch has only the abstract to go on")
    if resp.status_code >= 400:
        return "", (f"the paper's page returned HTTP {resp.status_code} — the "
                    "catch has only the abstract to go on")
    found = limit_sentences(resp.text, facts.get("abstract", ""))
    if not found:
        return "", ("no limit stated in the paper's readable text (paywalled, "
                    "or none) — the catch has only the abstract to go on")
    return found, None


def source_text(facts: dict | None, article: str, summary: str) -> str:
    """The text block the model drafts from, paper first when we have one."""
    coverage = article or summary
    if not facts or not facts["abstract"]:
        return coverage

    paper = ["PAPER — the primary source. Where this and the coverage "
             "disagree, the paper is right."]
    if facts["title"]:
        paper.append(f"Title: {facts['title']}")
    names = facts["authors"]
    if names:
        listed = ", ".join(names[:AUTHORS_IN_PROMPT])
        if len(names) > AUTHORS_IN_PROMPT:
            listed += (f", and {len(names) - AUTHORS_IN_PROMPT} more not "
                       "listed here (a large collaboration)")
        paper.append("Authors, in order: " + listed)
    if facts["journal"]:
        paper.append(f"Journal: {facts['journal']}")
    paper.append(f"Abstract: {facts['abstract']}")
    if facts.get("limits"):
        paper.append("Limits, quoted from the paper's body (chosen by code, "
                     "out of context — use one only as the paper states it): "
                     + facts["limits"])

    return ("\n".join(paper)
            + "\n\nCOVERAGE — context and plain-language framing only. Anyone "
              "quoted here may not be an author.\n" + coverage)
