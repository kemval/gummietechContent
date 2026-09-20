#!/usr/bin/env python3
"""
Render a post to 1080x1350 PNGs, one per slide.

Reads a post JSON record, injects it into the template its `post_type` names,
and screenshots each .slide div individually with Playwright.

How many slides there are is the template's business, not this module's: a
Drop has five, a Breakdown eight to ten, a Signal one per item. So the slides
are discovered in the rendered page rather than listed here, and the template
asks for its own colour rhythm with `rhythm(n)`. This module owns what the
rhythm is; the template owns how long it is.

Usage:
    python src/render.py posts/2026-09-03-era.json
    python src/render.py posts/2026-09-03-era.json --outdir output/era
    python src/render.py posts/2026-09-03-era.json --colorway orbit

Guardrails enforced here, not by convention:
  - refuses to render without `attribution` and `alt_text`
  - forces the preprint flag when `peer_reviewed` is false
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from playwright.sync_api import Page, sync_playwright

# The format table is its own module so telegram.py can read it without
# importing this one — see formats.py. Re-exported here because render.py
# is where the rest of the shared vocabulary already lives.
from formats import (DEFAULT_FORMAT, FORMATS, RECORD, Format, Section,
                     body_text, entries, es_fields, format_name,
                     missing_from_entries, pieces, post_preprint_flag,
                     preprint_claims, required,
                     sections, spec, template_for)

REPO_ROOT = Path(__file__).resolve().parent.parent
TEMPLATE_DIR = REPO_ROOT / "templates"
DEFAULT_OUT = REPO_ROOT / "output"

SLIDE_W, SLIDE_H = 1080, 1350

# Below this a post cannot carry the rhythm at all — the bookends, the rest
# slide and the catch are four slides on their own. A template rendering
# fewer is broken, not a new format.
MIN_SLIDES = 4


# The fields the web archive shows in Spanish live in FORMATS above, read
# through es_fields(): translate.py writes them, site.py renders them behind
# the page's language toggle. The slides are English only, so nothing there
# touches a render — the table lives in this module because it is the one
# both of those can import. site.py cannot be imported by name (the standard
# library owns `site`), and it must not pull in the LLM stack to build a page.

# Field hues by topic family: (lead, support). The five-slide sequence is
# always lead - cream - support - dark - lead: the hook and CTA bookend the
# post, slide 2 is the cream rest slide, and the catch always drops to ink.
# Only the hues vary per post. That is what lets the color suit the subject
# while the grid still reads as one account.
#
# render.py owns these, not the model. draft.py offers the names as a menu
# and resolves them through here, so an invented name degrades to the
# default instead of reaching the CSS.
COLORWAYS: dict[str, tuple[str, str]] = {
    "signal": ("pink",  "olive"),   # AI, computing, software, robotics
    "orbit":  ("sky",   "pink"),    # space, astronomy, physics
    "bloom":  ("olive", "blush"),   # biology, medicine, climate, ecology
    "ember":  ("amber", "pink"),    # energy, materials, engineering, chemistry
}
DEFAULT_COLORWAY = "signal"

WORD_LIMIT = 25          # per §1 of the content system
HOOK_WORD_LIMIT = 12


def shown(path: Path) -> str:
    """Repo-relative for readability, absolute when --outdir points outside
    the repo — relative_to() raises rather than escaping with `..`."""
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def load_post(path: Path) -> dict:
    """Read and validate a post record."""
    try:
        post = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        sys.exit(f"{path} is not valid JSON: {exc}")

    # `peer_reviewed` is in RECORD rather than checked apart, so a missing
    # one is refused like any other field. Defaulting it to True would let an
    # unlabelled preprint through, which is the exact failure this guards —
    # so the test is presence, not truthiness.
    missing = [f for f in required(post)
               if post.get(f) is None or (f != "peer_reviewed"
                                          and not post.get(f))]
    missing += missing_from_entries(post)
    if missing:
        sys.exit(
            f"Refusing to render a {format_name(post.get('post_type'))}. "
            f"Missing required field(s): {', '.join(missing)}.\n"
            "attribution and alt_text are mandatory and peer_reviewed must be "
            "explicit — an unlabelled preprint is a credibility risk. Add "
            "them to the JSON and re-run."
        )

    return post


def word_budget(post: dict) -> Iterator[tuple[str, int, int]]:
    """(where, words, limit) for every piece of prose that has a budget.

    Walks the format's own sections, so a Breakdown's mechanism steps are
    measured one slide at a time — docs §1's rule is per slide, and a list of
    three steps measured as one string would pass a budget none of them meet.
    """
    yield "hook", len(str(post.get("hook", "")).split()), HOOK_WORD_LIMIT
    for section in sections(post):
        prose = pieces(post, section)
        for n, piece in enumerate(prose, start=1):
            where = (f"{section.field}[{n}]" if section.many and len(prose) > 1
                     else section.field)
            yield where, len(piece.split()), WORD_LIMIT


def warn_on_length(post: dict) -> None:
    """Word limits are a style rule, so warn rather than fail."""
    for where, count, limit in word_budget(post):
        if count > limit:
            print(f"  warning: {where} is {count} words (limit {limit}) — "
                  f"consider splitting across two slides")


def hook_size_class(hook: str) -> str:
    """Pick a display size so long hooks shrink instead of overflowing."""
    n = len(hook)
    if n < 45:
        return "xl"
    if n < 75:
        return "lg"
    if n < 110:
        return "md"
    return "sm"


def rhythm(lead: str, support: str, count: int,
           catch: int | None = None) -> list[str]:
    """The field of every slide, from the invariants in CLAUDE.md.

    Written as a rule rather than a list per format, because the rule is what
    makes a longer post still read as the same account:

      - the first and last slides share the lead field — the hook and the CTA
        bookend the post
      - slide 2 is always --cream, the rest slide
      - the catch always drops to --ink, and it is the only slide that does
      - everything else alternates support and lead, and no two neighbouring
        slides ever share a field

    At five slides this is lead · cream · support · dark · lead, which is the
    locked Drop rhythm, unchanged — a longer format only ever extends the
    middle, which is the only part it adds.

    `catch` is the 1-based slide the catch is on, defaulting to second from
    last, and 0 for a format that has none. It is a parameter because *where*
    the catch falls is the format's business and only the template knows it:
    a Drop ends catch then CTA, a Breakdown that keeps the recap slide from
    docs §1 ends catch, recap, CTA, and a Signal has no catch at all — the
    dark slide is where a post's caveat goes, and a roundup of five items has
    five of them or none. What is not the format's business is that the catch
    is the dark slide, which is why that is not a parameter.
    """
    count = max(count, MIN_SLIDES)
    if catch != 0:
        catch = count - 1 if catch is None else max(3, min(catch, count - 1))

    fields: list[str] = []
    for slide in range(1, count + 1):
        if slide in (1, count):
            fields.append(lead)                  # the bookends
        elif slide == 2:
            fields.append("cream")               # the rest slide
        elif slide == catch:
            fields.append("dark")
        else:
            # Alternating, expressed as "not what came before" rather than as
            # a counter. A counter puts lead next to the final lead whenever
            # the middle happens to be an odd length — at ten slides with a
            # recap it produced two identical fields in a row, which reads as
            # a duplicated slide rather than as a beat.
            fields.append(lead if fields[-1] == support else support)

    # Looking forward is not enough on its own: the last slide is a fixed
    # lead, and an even-length run before it ends on lead however it started.
    # A Signal of seven, which has no catch to break the run, came out
    # ... pink · pink. So the run is repaired from the right, where the fixed
    # end is, flipping only slides the rhythm leaves free — never a bookend,
    # never the cream rest slide, never the catch.
    free = {n for n in range(3, count)} - {catch}
    for i in range(count - 2, -1, -1):
        if fields[i] == fields[i + 1] and (i + 1) in free:
            fields[i] = support if fields[i] == lead else lead
    return fields


def colorway_pair(name: str | None) -> tuple[str, str]:
    """The (lead, support) hues of a colorway name.

    An unknown name warns and falls back rather than exiting: a wrong hue is
    cosmetic, unlike a missing attribution, and refusing to render would
    throw away the LLM call that produced the draft.
    """
    if name not in COLORWAYS:
        if name:
            print(f"  warning: unknown colorway {name!r} — using "
                  f"{DEFAULT_COLORWAY}. Valid: {', '.join(COLORWAYS)}")
        name = DEFAULT_COLORWAY
    return COLORWAYS[name]


def slide_fields(name: str | None, count: int = 5,
                 catch: int | None = None) -> tuple[str, list[str]]:
    """Resolve a colorway to (lead hue, one field class name per slide)."""
    lead, support = colorway_pair(name)
    return lead, rhythm(lead, support, count, catch)


def render_html(post: dict, colorway: str | None = None) -> str:
    env = Environment(
        loader=FileSystemLoader(TEMPLATE_DIR),
        autoescape=select_autoescape(["html"]),
    )
    template = env.get_template(template_for(post.get("post_type")))

    lead, support = colorway_pair(colorway or post.get("colorway"))

    # Built as a dict rather than splatted as **post: a post JSON carrying a
    # key that collides with one of the computed values would otherwise raise
    # "got multiple values for keyword argument".
    context = dict(post)
    context.update(
        # Not `not post["peer_reviewed"]`: a Signal has no such field,
        # and formats.py is what knows that a roundup's flags belong to
        # its items. signal.html never reads this.
        show_preprint_flag=post_preprint_flag(post),
        hook_size=hook_size_class(post.get("hook", "")),
        font_dir=(REPO_ROOT / "fonts").as_uri(),
        lead=lead,
    )
    # The template calls this with its own slide count: it is the only thing
    # that knows how many it has, and this is the only thing that knows what
    # colour they go in.
    env.globals["rhythm"] = (lambda count, catch=None:
                             rhythm(lead, support, count, catch))
    return template.render(context)


@contextmanager
def open_page(html: str) -> Iterator[Page]:
    """
    A Chromium page with the slides loaded and the webfonts settled.

    The page has to be loaded from file://, not injected with set_content():
    Chromium refuses local subresources on an about:blank page ("Not allowed
    to load local resource"), so the self-hosted fonts drop out silently and
    the slides render in a fallback face.

    proof.py measures the same page this screenshots, which is the point of
    it living here: a layout checked in a differently-built page is a layout
    nobody checked.
    """
    with sync_playwright() as p, tempfile.TemporaryDirectory() as tmp:
        page_file = Path(tmp) / "slides.html"
        page_file.write_text(html)

        browser = p.chromium.launch()
        page = browser.new_page(
            viewport={"width": SLIDE_W, "height": SLIDE_H},
            device_scale_factor=1,
        )
        page.goto(page_file.as_uri(), wait_until="load")
        page.wait_for_timeout(600)          # let webfonts settle
        try:
            yield page
        finally:
            browser.close()


def shoot(html: str, outdir: Path) -> list[Path]:
    outdir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    with open_page(html) as page:
        # Document order, not a list of ids: the template decides how many
        # slides a format has, and a new one must not need editing here.
        slides = page.query_selector_all(".slide")
        if len(slides) < MIN_SLIDES:
            sys.exit(f"The template rendered {len(slides)} .slide element(s). "
                     f"A post needs at least {MIN_SLIDES} — the two bookends, "
                     f"the rest slide and the catch. Check the template.")
        for i, el in enumerate(slides, start=1):
            out = outdir / f"slide-{i}.png"
            el.screenshot(path=str(out))
            written.append(out)
            print(f"  wrote {shown(out)}")

    return written


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("post", help="path to the post JSON")
    ap.add_argument("--outdir", default=None, help="where to write PNGs")
    ap.add_argument("--colorway", default=None, choices=sorted(COLORWAYS),
                    help="override the colorway in the JSON")
    args = ap.parse_args()

    post_path = Path(args.post)
    if not post_path.is_absolute():
        post_path = REPO_ROOT / post_path
    if not post_path.exists():
        sys.exit(f"No such post file: {post_path}")

    post = load_post(post_path)
    warn_on_length(post)

    outdir = Path(args.outdir) if args.outdir else DEFAULT_OUT / post_path.stem
    if not outdir.is_absolute():
        outdir = REPO_ROOT / outdir

    print(f"Rendering {post_path.name} → {outdir}")
    # How many slides, not whether: a Signal flags per item, so "ON" alone
    # said nothing about which of five claims is unreviewed.
    if flags := preprint_claims(post):
        print(f"  preprint flag ON — {flags} slide{'s' * (flags != 1)} "
              f"must carry it")

    written = shoot(render_html(post, args.colorway), outdir)

    # The caption and alt text are needed at posting time, so drop them
    # next to the images rather than making you dig back into the JSON.
    # Hashtags ride with the caption so the top block pastes into Business Suite
    # in one go, rather than being retyped from the JSON.
    tags = " ".join(post.get("hashtags") or [])

    # One credit for a Drop or a Breakdown, one per item for a Signal —
    # §7.3 makes attribution mandatory per source, and a roundup has five.
    credits = ([f"{e['attribution']}\n{e['source_url']}"
                for e in entries(post)]
               or [f"{post['attribution']}\n{post['source_url']}"])

    sidecar = outdir / "caption.txt"
    sidecar.write_text(
        f"{post.get('caption', '')}\n"
        + (f"\n{tags}\n" if tags else "")
        + f"\n--- ALT TEXT ---\n{post['alt_text']}\n\n"
        + "--- ATTRIBUTION ---\n" + "\n\n".join(credits) + "\n"
    )
    print(f"  wrote {shown(sidecar)}")
    print(f"\nDone. {len(written)} slides.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
