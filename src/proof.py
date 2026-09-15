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

from render import (COLORWAYS, HOOK_WORD_LIMIT, REPO_ROOT, WORD_LIMIT,
                    load_post, open_page, render_html, slide_fields)

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
CONTENT = ("hook", "slide-title", "slide-body", "flag",
           "cta-handle", "cta-line", "source")
CHROME = ("domain", "wordmark", "dots")

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

    const els = [...frame.querySelectorAll(
      '.domain,.hook,.slide-title,.slide-body,.flag,.wordmark,.dots,' +
      '.cta-handle,.cta-line,.source')].map(el => {
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


def check_rhythm(slides: list[dict], expected: list[str], report: Report) -> None:
    """lead · cream · support · dark · lead, or the grid stops reading as
    one account. render.py resolves the names; this confirms they landed."""
    actual = [s["field"] for s in slides]
    if actual != expected:
        report.block("colorway",
                     f"slide fields are {' · '.join(actual)}, expected "
                     f"{' · '.join(expected)}")


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
        elif -out < TIGHT and kind in CONTENT:
            report.fix(where, f".{kind} clears the frame by only "
                              f"{-out:.0f}px (want {TIGHT:.0f})")

        # Flow text against the absolutely positioned chrome.
        if kind in CONTENT:
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
        floor = MIN_CONTRAST if kind in CONTENT else MIN_CHROME_CONTRAST
        if ratio < floor:
            note = report.block if kind in CONTENT else report.fix
            note(where, f".{kind} is {ratio:.1f}:1 against its field "
                        f"(want {floor}:1) — this colorway is not readable")


def check_preprint(slides: list[dict], peer_reviewed: bool,
                   report: Report) -> None:
    """
    The flag is the one thing on the slides that is a claim about the source
    rather than about the subject, so its absence is never cosmetic.
    """
    catch = next((s for s in slides if s["id"] == "slide-4"), None)
    if catch is None:
        report.block("slide-4", "missing from the render")
        return

    flag = next((e for e in catch["els"] if e["kind"] == "flag"), None)
    if not peer_reviewed:
        if flag is None:
            report.block("slide-4", "peer_reviewed is false but no preprint "
                                    "flag rendered")
        elif flag["rect"]["w"] <= 0 or flag["rect"]["h"] <= 0:
            report.block("slide-4", "the preprint flag rendered with no size")
        else:
            report.note("slide-4", "preprint flag present and visible")
    elif flag is not None:
        report.block("slide-4", "peer_reviewed is true but a preprint flag "
                                "rendered anyway")


def check_words(post: dict, report: Report) -> None:
    """render.py already warns on these; a warning in a log nobody reads is
    not a gate, so they ride into the report too."""
    for field, limit in (("hook", HOOK_WORD_LIMIT),
                         ("what_happened", WORD_LIMIT),
                         ("why_it_matters", WORD_LIMIT),
                         ("the_catch", WORD_LIMIT)):
        count = len(str(post.get(field, "")).split())
        if count > limit:
            report.fix("copy", f"{field} is {count} words (limit {limit})")


def proof(post: dict, colorway: str | None) -> Report:
    report = Report()
    _, expected = slide_fields(colorway or post.get("colorway"))

    html = render_html(post, colorway)
    with open_page(html) as page:
        slides: list[dict[str, Any]] = page.evaluate(MEASURE)

    if len(slides) != len(expected):
        report.block("template", f"{len(slides)} slides rendered, expected "
                                 f"{len(expected)}")
        return report

    check_rhythm(slides, expected, report)
    check_preprint(slides, bool(post.get("peer_reviewed")), report)
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
