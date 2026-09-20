#!/usr/bin/env python3
"""
Check a post's rendered layout by measuring it, not by looking at it.

render.py warns on word count but never inspects what it produced, and
hook_size_class() sizes the hook from a character count rather than a
measured layout. So a long compound word, a body field a few words over
budget, or a palette rotation can overflow the ink frame, fail contrast, or
hide the preprint flag with no error anywhere.

This is the half of that problem a measurement answers better than a reading
of the PNG. Every one of these failures is a number in the DOM of the page
render.py is about to screenshot: a bounding box outside the frame, a
scrollHeight past the container, a computed colour pair under 4.5:1, a flag
element that is absent or zero-sized. A model looking at an image estimates
all of that. Playwright knows it exactly.

    python src/proof.py posts/2026-09-15-the-tidal-bulges.json
    python src/proof.py posts/2026-09-15-tides.json --colorway orbit

Prints a report whose first line is `PROOF · BLOCK|FIX|PASS`, and exits 1 on
BLOCK so a shell can gate on it. telegram.py reads that first line to decide
whether the approval button is offered at all.

What this does NOT cover is the other half — whether the slides are *true*.
That is fact-check's, and it needs to read the paper. Nothing here reads
anything but geometry and colour.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from formats import preprint_claims, spec
from render import (COLORWAYS, MIN_SLIDES, REPO_ROOT, colorway_pair,
                    load_post, open_page, render_html, rhythm, word_budget)

# The project's own invariant, from CLAUDE.md: "A new lead or support hue
# must clear 4.5:1 against --ink." WCAG would allow 3:1 for text this large,
# but the locked palette is held to the stricter number, so this is that
# rule rather than a generic accessibility bar.
MIN_CONTRAST = 4.5

# .domain and .wordmark are drawn at opacity 0.75, which is a locked design
# decision — tokens and type are not up for negotiation, so a chrome pair
# that lands near the line must not BLOCK a post every single day. It is
# still worth hearing about when a rotation pushes it somewhere clearly bad.
MIN_CHROME_CONTRAST = 3.0

# Slack between a text box and the ink frame, or between text and the
# wordmark/dots, below which the layout is one long word from breaking.
TIGHT = 24.0

# The signature border is 10px and the type sits inside it; sub-pixel
# rounding in getBoundingClientRect is not a finding.
EPSILON = 0.5

# Text the post supplies, as opposed to the fixed chrome. These are the ones
# a draft can make too long and a colorway can make unreadable.
# Chrome is the fixed furniture — the handle, the field label, the position
# markers — held to a lower contrast bar because its `opacity: 0.75` is a
# locked design decision and pink already sits at 3.26:1 there.
#
# This is still a list, and the list of what to *measure* was just removed
# for being one. The difference is which way each fails: a class missing
# from the old list was never measured at all, so signal.html shipped an
# 18px overlap and a 1.5:1 watermark and this file said PASS. A class
# missing from this one is merely held to the stricter bar and says so
# loudly. Silence is the failure worth engineering against; a false BLOCK
# gets fixed the morning it appears.
CHROME = ("domain", "wordmark", "dots", "rank", "step-mark")

# Absolutely positioned, and the only things flow content can collide with.
# .hook carries `margin-bottom: 96px` in the template with the comment
# "clears the wordmark" — that margin is the entire defence, and this is
# what checks it held.
FIXTURES = ("wordmark", "dots")

MEASURE = """
() => {
  const px = v => parseFloat(v) || 0;
  const transparent = c => !c || c === 'transparent' ||
                           /rgba\\(\\s*0,\\s*0,\\s*0,\\s*0\\s*\\)/.test(c);
  const bgOf = el => {
    for (let n = el; n; n = n.parentElement) {
      const c = getComputedStyle(n).backgroundColor;
      if (!transparent(c)) return c;
    }
    return 'rgb(255, 255, 255)';
  };
  // Every rect is expressed relative to its own slide, so where the slide
  // happens to sit in a five-slide scrolling page never enters into it.
  const rel = (r, s) => ({x: r.x - s.x, y: r.y - s.y, w: r.width, h: r.height});

  return [...document.querySelectorAll('.slide')].map(slide => {
    const sr = slide.getBoundingClientRect();
    const frame = slide.querySelector('.frame');
    const fr = frame.getBoundingClientRect();
    const bw = px(getComputedStyle(frame).borderTopWidth);

    // Everything that carries text, found by shape rather than by a list of
    // class names. The list was the bug: a new template's classes were
    // simply not measured, so templates/signal.html shipped .item-source
    // overlapping the wordmark on five slides and this file reported PASS.
    // A format nobody has to remember to register is a format that cannot
    // be forgotten.
    //
    // Leaves only. An element whose text is all in its children is a
    // wrapper, and measuring it would re-report its children's geometry as
    // its own. .dots carries no text and is included by name because it is
    // a fixture everything else has to clear.
    const texted = el => el.textContent.trim().length > 0;
    const els = [...frame.querySelectorAll('*')].filter(el =>
        (texted(el) && ![...el.children].some(texted)) ||
        el.classList.contains('dots')).map(el => {
      const cs = getComputedStyle(el);
      // The element box of a left-aligned block spans the full column even
      // when its last line stops far short, so a block box is the wrong
      // thing to test for collisions: on slide 5 .source and .dots overlap
      // by a constant 3px in a layout where no glyph is anywhere near
      // another. Range rects are the line boxes the text actually occupies,
      // which is both quieter here and stricter where it matters — a line
      // that really does reach the dots is caught, and a short one is not.
      const range = document.createRange();
      range.selectNodeContents(el);
      const lines = [...range.getClientRects()]
        .filter(r => r.width > 0 && r.height > 0)
        .map(r => rel(r, sr));
      return {
        kind: el.className.split(' ')[0],
        rect: rel(el.getBoundingClientRect(), sr),
        lines: lines.length ? lines : [rel(el.getBoundingClientRect(), sr)],
        fontSize: px(cs.fontSize),
        color: cs.color,
        bg: bgOf(el),
        opacity: parseFloat(cs.opacity),
        text: (el.textContent || '').trim().slice(0, 48),
      };
    });

    return {
      id: slide.id,
      field: [...slide.classList].filter(c => c !== 'slide')[0] || '',
      // Inside the 10px signature border: the frame's padding box. This is
      // the line "contained in the frame" actually means.
      inner: {x: fr.x - sr.x + bw, y: fr.y - sr.y + bw,
              w: fr.width - 2 * bw, h: fr.height - 2 * bw},
      overflow: frame.scrollHeight - frame.clientHeight,
      els,
    };
  });
}
"""


def channels(value: str) -> tuple[float, float, float]:
    """'rgb(59, 44, 35)' or 'rgba(59, 44, 35, 0.5)' -> (r, g, b)."""
    nums = value[value.index("(") + 1:value.rindex(")")].split(",")
    return tuple(float(n) for n in nums[:3])          # type: ignore[return-value]


def over(fg: tuple[float, float, float], bg: tuple[float, float, float],
         alpha: float) -> tuple[float, float, float]:
    """Composite fg onto bg. Element opacity is a real contrast reduction —
    ink at 0.75 over a pale field is not ink."""
    return tuple(f * alpha + b * (1 - alpha) for f, b in zip(fg, bg))  # type: ignore[return-value]


def luminance(c: tuple[float, float, float]) -> float:
    def part(v: float) -> float:
        v /= 255.0
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = (part(v) for v in c)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(fg: str, bg: str, alpha: float = 1.0) -> float:
    back = channels(bg)
    front = over(channels(fg), back, alpha)
    a, b = luminance(front), luminance(back)
    lo, hi = sorted((a, b))
    return (hi + 0.05) / (lo + 0.05)


def gap(a: dict, b: dict) -> float:
    """
    Separation between two boxes: negative when they overlap, and then the
    depth of the smaller of the two overlaps — the direction you would have
    to move to part them.
    """
    dx = max(a["x"] - (b["x"] + b["w"]), b["x"] - (a["x"] + a["w"]))
    dy = max(a["y"] - (b["y"] + b["h"]), b["y"] - (a["y"] + a["h"]))
    # Separated on either axis, the larger value is the clearance. Overlapping
    # on both, both are negative and the larger is the shallower overlap.
    return max(dx, dy)


def escape(box: dict, inner: dict) -> float:
    """How far `box` reaches past `inner`, negative when it is clear."""
    return max(inner["x"] - box["x"],
               box["x"] + box["w"] - (inner["x"] + inner["w"]),
               inner["y"] - box["y"],
               box["y"] + box["h"] - (inner["y"] + inner["h"]))


class Report:
    """Findings, and the verdict they add up to."""

    def __init__(self) -> None:
        self.lines: list[tuple[str, str]] = []

    def block(self, where: str, what: str) -> None:
        self.lines.append(("BLOCK", f"{where} · {what}"))

    def fix(self, where: str, what: str) -> None:
        self.lines.append(("FIX", f"{where} · {what}"))

    def note(self, where: str, what: str) -> None:
        self.lines.append(("note", f"{where} · {what}"))

    @property
    def verdict(self) -> str:
        levels = {level for level, _ in self.lines}
        return "BLOCK" if "BLOCK" in levels else "FIX" if "FIX" in levels else "PASS"

    def render(self) -> str:
        mark = {"BLOCK": "🛑", "FIX": "⚠️", "note": "·"}
        body = "\n".join(f"{mark[level]} {text}" for level, text in self.lines)
        return f"PROOF · {self.verdict}\n{body}" if body else "PROOF · PASS"


def check_rhythm(slides: list[dict], lead: str, support: str,
                 has_catch: bool, report: Report) -> None:
    """The rhythm rule, checked against the length the template rendered.

    Where the catch falls is the format's business — a Drop ends catch then
    CTA, a Breakdown with a recap slide ends catch, recap, CTA, and a Signal
    has none — so the dark slide is located in the page and the rest of the
    rhythm is checked against the rule *for that position*. What is not the
    format's business, and is asserted here, is that the format has as many
    dark slides as it says it does, that slide 2 is the cream rest slide,
    that the bookends share the lead field, and that no two neighbours share
    a field. Get any of those wrong and the grid stops reading as one
    account.
    """
    actual = [s["field"] for s in slides]
    dark = [n for n, field in enumerate(actual, start=1) if field == "dark"]
    wanted = 1 if has_catch else 0
    if len(dark) != wanted:
        report.block("colorway",
                     f"{len(dark)} slide(s) drop to ink, expected {wanted}: "
                     f"the dark slide is the catch, and this format "
                     f"{'has one' if has_catch else 'has none'}")
        return

    expected = rhythm(lead, support, len(actual), dark[0] if dark else 0)
    if actual != expected:
        report.block("colorway",
                     f"slide fields are {' · '.join(actual)}, expected "
                     f"{' · '.join(expected)} for a catch on slide {dark[0]}")


def check_slide(slide: dict, report: Report) -> None:
    where = slide["id"]
    inner = slide["inner"]

    if slide["overflow"] > EPSILON:
        report.block(where, f"content runs {slide['overflow']:.0f}px past the "
                            f"frame and will be clipped — shorten the field "
                            f"or drop the hook a size")

    fixtures = {e["kind"]: e for e in slide["els"] if e["kind"] in FIXTURES}

    for el in slide["els"]:
        kind, box = el["kind"], el["rect"]

        if box["w"] <= 0 or box["h"] <= 0:
            continue

        out = max(escape(line, inner) for line in el["lines"])
        if out > EPSILON:
            report.block(where, f".{kind} crosses the ink frame by "
                                f"{out:.0f}px — {el['text']!r}")
        elif -out < TIGHT and kind not in CHROME:
            report.fix(where, f".{kind} clears the frame by only "
                              f"{-out:.0f}px (want {TIGHT:.0f})")

        # Flow text against the absolutely positioned chrome.
        if kind not in CHROME:
            for name, fixture in fixtures.items():
                if fixture["rect"]["w"] <= 0:
                    continue
                clear = min(gap(line, fixture["rect"]) for line in el["lines"])
                if clear < 0:
                    report.block(where, f".{kind} overlaps .{name} by "
                                        f"{-clear:.0f}px")
                elif clear < TIGHT:
                    report.fix(where, f".{kind} clears .{name} by only "
                                      f"{clear:.0f}px (want {TIGHT:.0f})")

        ratio = contrast(el["color"], el["bg"], el["opacity"])
        floor = MIN_CONTRAST if kind not in CHROME else MIN_CHROME_CONTRAST
        if ratio < floor:
            note = report.block if kind not in CHROME else report.fix
            note(where, f".{kind} is {ratio:.1f}:1 against its field "
                        f"(want {floor}:1) — this colorway is not readable")


def check_preprint(slides: list[dict], wanted: int, report: Report) -> None:
    """
    The flag is the one thing on the slides that is a claim about the source
    rather than about the subject, so its absence is never cosmetic.
    """
    # Counted, not located. §7.2 is a per-claim rule, not a per-post one: a
    # Drop and a Breakdown have one source and so at most one flag, and a
    # Signal has five items with five independent answers. Counting is the
    # check that reads the same for all of them, and it catches the failure
    # that matters either way — a preprint that reached a slide unlabelled.
    visible = [s for s in slides
               if any(e["kind"] == "flag" and e["rect"]["w"] > 0
                      and e["rect"]["h"] > 0 for e in s["els"])]
    rendered = [s for s in slides
                if any(e["kind"] == "flag" for e in s["els"])]

    if len(rendered) != wanted:
        report.block("preprint",
                     f"{wanted} source(s) are not peer-reviewed but "
                     f"{len(rendered)} slide(s) carry the flag")
        return
    if len(visible) != len(rendered):
        report.block("preprint", "a preprint flag rendered with no size, so "
                                 "it is on the slide but not on the screen")
        return
    if wanted:
        where = ", ".join(s["id"] or "?" for s in visible)
        report.note("preprint", f"{wanted} flag(s) present and visible "
                                f"on {where}")


def check_words(post: dict, report: Report) -> None:
    """render.py already warns on these; a warning in a log nobody reads is
    not a gate, so they ride into the report too."""
    for where, count, limit in word_budget(post):
        if count > limit:
            report.fix("copy", f"{where} is {count} words (limit {limit})")


def proof(post: dict, colorway: str | None) -> Report:
    report = Report()

    html = render_html(post, colorway)
    with open_page(html) as page:
        slides: list[dict[str, Any]] = page.evaluate(MEASURE)

    # The expected rhythm follows the rendered count, because the template
    # owns how many slides a format has. What is checked is that the fields
    # follow the rule for that many — a Drop of five and a Breakdown of nine
    # are both wrong in the same way if they do not.
    if len(slides) < MIN_SLIDES:
        report.block("template", f"{len(slides)} slide(s) rendered; a post "
                                 f"needs at least {MIN_SLIDES}")
        return report
    lead, support = colorway_pair(colorway or post.get("colorway"))

    check_rhythm(slides, lead, support, spec(post).catch, report)
    check_preprint(slides, preprint_claims(post), report)
    for slide in slides:
        check_slide(slide, report)
    check_words(post, report)
    return report


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("post", type=Path, help="path to the post JSON")
    ap.add_argument("--colorway", default=None, choices=sorted(COLORWAYS),
                    help="proof against this colorway instead of the JSON's")
    args = ap.parse_args()

    path = args.post if args.post.is_absolute() else REPO_ROOT / args.post
    if not path.exists():
        sys.exit(f"No such post file: {path}")

    report = proof(load_post(path), args.colorway)
    print(report.render())
    return 1 if report.verdict == "BLOCK" else 0


if __name__ == "__main__":
    sys.exit(main())
