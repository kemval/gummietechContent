#!/usr/bin/env python3
"""
The evergreen queue's shape: docs/evergreen_queue.md, read as rows.

Its own module because two readers need it and one cannot pay for the
other: draft.py drafts a Drop from a row, and weekly.py (stdlib only, run
before anything is installed) picks Sunday's Incident Report from the rows
marked `**Kind** — incident`. One parser, so the two cannot disagree about
what a row is.

Standard library only.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import NamedTuple

REPO_ROOT = Path(__file__).resolve().parent.parent
QUEUE = REPO_ROOT / "docs" / "evergreen_queue.md"

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



class Row(NamedTuple):
    """One `###` candidate. `fields` maps each bold label, lower-cased, to
    its value; `body` is the row's whole text, for checks that read it."""
    rank: int
    score: str
    colorway: str
    title: str
    fields: dict[str, str]
    body: str


def rows(text: str) -> list[Row]:
    """Every candidate in the file, in file order, which is score order."""
    heads = list(CANDIDATE_RE.finditer(text))
    out = []
    for n, head in enumerate(heads):
        end = heads[n + 1].start() if n + 1 < len(heads) else len(text)
        body = text[head.end():end]
        fields = {m["label"].strip().lower(): m["value"].strip()
                  for m in FIELD_RE.finditer(body)}
        out.append(Row(int(head["rank"]), head["score"], head["colorway"],
                       head["title"].strip(), fields, body))
    return out


def source_url(fields: dict[str, str]) -> str:
    """The row's primary URL: an arXiv id if it cites one, else the Source
    line's first link, else ""."""
    source = fields.get("source", "")
    arxiv = ARXIV_RE.search(source)
    if arxiv:
        return f"https://arxiv.org/abs/{arxiv['id']}"
    link = MD_LINK_RE.search(source)
    return link.group(1) if link else ""


def credit(fields: dict[str, str]) -> str:
    """Who the row says to attribute, or ""."""
    found = ATTRIBUTE_RE.search(fields.get("source", ""))
    return found["who"].strip().rstrip(".") if found else ""
