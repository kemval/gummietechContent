#!/usr/bin/env python3
"""
The three voice rules code can check, and nothing else.

docs/voice.md is read by the model, and on 2026-10-07 the model did not
follow all of it: three fact-checked test drafts came back with "just
launched" on a 34-day-old launch, and with "you can" on products limited to
paid plans or not released yet. Most of voice.md needs judgement and stays
with the fact-check agent. These three need only a word list, so they are
enforced in code, where they cannot be ignored:

  - dating words. The model does not know today's date, and a post may go
    out weeks after its source was written.
  - reader words in an announcement. "You can" about a maker's release
    promises access the reader may not have.
  - a maker's figure stated as fact. In an announcement every percentage,
    multiple and benchmark gain is the maker's own test; a sentence that
    carries one and no "says" or "reports" claims an independence it does
    not have. The 2026-10-08 test drafts did it in every announcement, two
    rounds running, though the prompt says it twice.

draft.py drops a cover line that breaks any of them, while one is left to keep;
proof.py reports what remains, as a FIX, so it reaches the gate. A FIX and
not a BLOCK: "just" also means "only", and a person can tell which.

Standard library only: proof.py and draft.py both import it.
"""

from __future__ import annotations

import re

# Narrower than voice.md's list on purpose. "new", "now" and "today" are
# there and not here: "a new image format", "ice can now be 3D printed" and
# "today's quantum computers" describe rather than date, and a word list
# cannot tell which. Measured on the 35 posts in posts/ on 2026-10-07: with
# them, 9 were flagged and nearly all wrongly; a check that fires on one
# post in four is one the gate learns to scroll past.
DATING_RE = re.compile(r"\b(just|tonight|yesterday|latest|lately|recently|"
                       r"this week|this month)\b", re.I)
# A roundup's own frame is the week it rounds up: the Signal says so.
ROUNDUP_ALLOWS = ("this week",)
READER_RE = re.compile(r"\b(you|your|you're|you'll|you've|yours)\b", re.I)
# A maker's claim, as a figure: "30-50%", "3×", "9.92 points". A plain
# count is not one — "740 million parameters" and "Chrome 155" are specs,
# and the fact-check passes them unattributed.
FIGURE_RE = re.compile(r"\d[\d.,]*\s*(%|percent\b|×|x\b|-?fold\b|points?\b)",
                       re.I)
CREDIT_RE = re.compile(r"\b(says?|said|reports?|reported|claims?|claimed|"
                       r"according to|estimates?|in (its|their) (own )?"
                       r"(tests?|benchmarks?|evaluations?))\b", re.I)
# Sentences, split after their closing punctuation. A full stop inside a
# word or number ("9.92", ".jxl") is not an end: splitting there cut one
# sentence in two and left the figure without its "Google says".
SENTENCE_RE = re.compile(r"(?:[^.!?]|[.!?](?=\S))+[.!?]*")


def problems(text: str, announcement: bool, roundup: bool = False) -> list[str]:
    """The words in `text` that break a checkable voice rule, as labels.

    A question is exempt from the reader and figure rules: every caption ends by asking
    the reader something ("Would you use it?"), and a question promises
    nothing. Measured on the first three drafts this check saw, where it
    flagged every caption until it was.
    """
    found = [f'dates the story ("{m.group(0)}")'
             for m in DATING_RE.finditer(text)
             if not (roundup and m.group(0).lower() in ROUNDUP_ALLOWS)]
    if announcement:
        for sentence in SENTENCE_RE.findall(text):
            if sentence.rstrip().endswith("?"):
                continue
            found += [f'speaks to the reader about a maker\'s release '
                      f'("{m.group(0)}")' for m in READER_RE.finditer(sentence)]
            if (figure := FIGURE_RE.search(sentence)) and \
                    not CREDIT_RE.search(sentence):
                found.append(f'states the maker\'s figure as fact '
                             f'("{figure.group(0)}" without "says")')
    return found
