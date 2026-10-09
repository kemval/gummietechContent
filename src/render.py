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
import re
import shutil
import subprocess
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
from formats import (DEFAULT_FORMAT, FORMATS, PAIR, RECORD, Format, Section,  # noqa: F401
                     body_text, entries, es_fields, format_name,  # noqa: F401
                     announcement, missing_fields, missing_from_entries, pieces,
                     post_preprint_flag, preprint, preprint_claims, required,
                     sections, spec, template_for, unpaired)

REPO_ROOT = Path(__file__).resolve().parent.parent
TEMPLATE_DIR = REPO_ROOT / "templates"
DEFAULT_OUT = REPO_ROOT / "output"
POSTS_DIR = REPO_ROOT / "posts"

# Every post draft.py writes is posts/YYYY-MM-DD-<slug>.json, so the prefix
# both identifies a real post and sorts it. See post_order().
DATED_NAME = re.compile(r"\d{4}-\d{2}-\d{2}-")

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
    # Owner's call, 2026-09-30: amber read as washed out as a lead under the
    # v3 backdrop. Ember wore signal's pink/olive for a few hours, which left
    # the grid three looks for four families; blush is the one lead no other
    # family uses, and amber survives as the support slide. vary() compares
    # pairs, not names, in case two families ever share one again.
    "ember":  ("blush", "amber"),   # energy, materials, engineering, chemistry
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
    # so the test is presence, not truthiness (formats.missing_fields).
    missing = missing_fields(post, required(post))
    missing += missing_from_entries(post)
    if missing:
        sys.exit(
            f"Refusing to render a {format_name(post.get('post_type'))}. "
            f"Missing required field(s): {', '.join(missing)}.\n"
            "attribution and alt_text are mandatory and peer_reviewed must be "
            "explicit — an unlabelled preprint is a credibility risk. Add "
            "them to the JSON and re-run."
        )

    if bad := unpaired(post):
        sys.exit(f"Refusing to render a {format_name(post.get('post_type'))}: "
                 f"{', '.join(bad)} must read \"Term: line\" — the term, a "
                 "colon and a space, then its line. Fix the JSON and re-run.")
    if "example_post" in spec(post).record:
        example_post(post)
    return post


def example_post(post: dict) -> dict:
    """The published post a glossary term points to as its example.

    Refused unless it is in posts/ and carries published_at: "where we saw
    it" is a claim that this account showed it, and a draft or a rejected
    post was never shown. The stem is a lookup in posts/, never a path — a
    name with a separator in it is refused rather than followed.
    """
    stem = str(post.get("example_post", "")).strip()
    path = POSTS_DIR / f"{stem}.json"
    if not stem or Path(stem).name != stem or not path.is_file():
        sys.exit(f"example_post {stem!r} is not a post in posts/. Name the "
                 "stem of a published post, e.g. "
                 "2026-09-27-why-language-models-hallucinate.")
    try:
        example = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        sys.exit(f"example_post {stem}: {path.name} is not valid JSON: {exc}")
    if not example.get("published_at"):
        sys.exit(f"example_post {stem} has no published_at — only a post "
                 "that went live can be the example. Pick a published one.")
    return example


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


# ---------- the Drop's typographic devices ----------
#
# Every word on a Drop slide is a field of the record, and nothing below
# rewrites one. On 2026-09-28 a hand-typed prototype dropped "than defaults"
# from what_happened and turned "default plans" into "own planner" — the
# design had quietly changed the claim. So these only ever *choose* a span
# of the record's own text to emphasise; `typeset` is the single change to a
# character the slides make, and it is a glyph, not a word.

# "1.81x" set as "1.81×". Only a digit followed by a bare x at a word end:
# "0x1F", "4x4" and "Qwen2-x" are left alone.
MULTIPLIER = re.compile(r"(\d)x\b")

# A figure: a number carrying % or ×/x, or a range of them ("1–10 %" is
# one figure, not a "10 %" to box on its own). "4B" and "15" are not
# figures — they are counts, and the cover does not put a count at 300px.
FIGURE = re.compile(r"\d[\d.,]*(?:[–-]\d[\d.,]*)?\s?(?:%|×|x\b)")


LINKING_WORDS = {"of", "the", "a", "an", "to", "in", "on", "for", "and", "or",
                 "per", "at", "by", "with", "from", "than", "as", "is", "was"}


def typeset(text: str) -> str:
    return MULTIPLIER.sub(r"\1×", text or "")


def figure_phrase(text: str) -> str | None:
    """The first figure in `text` with the word after it — "81% faster"."""
    t = typeset(text)
    m = FIGURE.search(t)
    if not m:
        return None
    # The next word travels with the figure ("81% faster") unless it only
    # links it to what follows — a box around "20% of" reads as a typo.
    rest = re.match(r"\s*([\w-]+)", t[m.end():])
    if rest and rest.group(1).lower() in LINKING_WORDS:
        rest = None
    return t[m.start():m.end() + (rest.end() if rest else 0)].strip()


def cover_figure(hook: str) -> dict | None:
    """
    The number the cover sets large, and the hook's own words that qualify it.

    On 2026-09-28 the cover set "81%" at 300px with no context, where the
    hook said "81% faster — best of 15 tries": the design made the
    best-of-15 result the loudest thing in the post while the catch was
    there to say the model's own picks gave 1.40x. The figure is therefore
    never shown bare — it carries whatever the hook puts after its last
    em dash, or failing that the rest of the clause the figure opens,
    verbatim. And a hook with two figures gets none: "survival rose 8% to
    60%" would set "8%" large, the one number the hook is moving away from.
    """
    t = typeset(hook)
    found = list(FIGURE.finditer(t))
    if len(found) != 1:
        return None
    m = found[0]
    if " — " in t:
        qualifier = t.rsplit(" — ", 1)[1]
    else:
        qualifier = re.split(r"[.;:,—]", t[m.end():], maxsplit=1)[0]
    qualifier = qualifier.strip(" .")
    if not qualifier:
        return None
    return {"value": m.group(0).replace(" ", ""), "qualifier": qualifier}


def catch_diff(the_catch: str, figure: dict | None) -> list[dict] | None:
    """
    The catch as a diff — the cover's figure struck through, the corrected
    one below it — but only when the catch names the cover's figure first
    and a second figure after it. Each row's label is the clause of the
    catch that figure sits in, with the figure and its linking verb taken
    out; nothing is paraphrased. Anything less regular gets no diff and the
    catch is shown as plain text, which is always correct.
    """
    if not figure:
        return None
    t = typeset(the_catch)
    found = [m.group(0).replace(" ", "") for m in FIGURE.finditer(t)]
    if len(found) < 2 or found[0] != figure["value"]:
        return None
    clauses = re.split(r"(?<=[;.])\s+", t)

    def label(value: str) -> str:
        clause = next((c for c in clauses if value in c), "")
        words = clause.replace(value, "", 1).strip(" ;.")
        return re.sub(r"^(?:is|was|gave|gives|are)\s+|\s+(?:is|was|gave|gives|are)$",
                      "", words).strip()

    return [{"sign": "−", "value": found[0], "label": label(found[0])},
            {"sign": "+", "value": found[1], "label": label(found[1])}]


def emphasis(text: str, keywords: list[str] | None = None,
             figures_only: bool = False) -> str | None:
    """The span a slide boxes: its first figure phrase, else the first of
    the post's keywords that appears in it, else nothing. The cover passes
    `figures_only`: a boxed phrase cannot wrap, so a long keyword there
    ("Decorrelation stretch") holds the whole hook to its width.

    A keyword match is widened to whole words — "Bunsen burner" inside
    "Bunsen burners" boxes "Bunsen burners", or the box ends mid-word and
    its last letter wraps onto the next line alone."""
    phrase = figure_phrase(text)
    if phrase or figures_only:
        return phrase
    t = typeset(text)
    for k in keywords or []:
        m = re.search(r"(?<!\w)" + re.escape(k) + r"\w*", t, re.IGNORECASE) if k else None
        if m:
            return m.group(0)
    return None


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


def post_order(directory: Path | None = None) -> list[Path]:
    """Every real post, in the order a reader meets them.

    That order is `published_at` when there is one and the filename's date
    when there is not, so a drafted-but-ungated post sits where it will land
    rather than nowhere. Ties break on the filename, which is what two posts
    drafted the same day get.

    The date-prefix filter is the one resolve-post needs for the same reason:
    posts/era*.json are hand-built fixtures with neither a prefix nor a
    published_at, and they would sort after every real draft.
    """
    directory = directory or POSTS_DIR
    dated = []
    for path in sorted(directory.glob("*.json")):
        if not DATED_NAME.match(path.name):
            continue
        try:
            post = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            continue          # site.py skips a malformed post; so does this
        dated.append((post.get("published_at") or path.name[:10],
                      path.name, path))
    return [path for _, _, path in sorted(dated)]


def previous_colorway(before: Path | None = None,
                      directory: Path | None = None) -> str | None:
    """The colorway of the post a reader meets just before `before`.

    Strictly the predecessor, never merely "the newest other post": a post
    being re-rendered sits inside posts/ with successors after it, and
    answering with one of those would compare it against a post nobody has
    seen yet. A `before` that is not on disk — draft.py asking about the
    post it is about to write — is treated as landing at the end, which is
    where a new draft goes.

    Posts with no recognised colorway are stepped over rather than ending
    the search, so one malformed neighbour cannot silently disable the rule.
    """
    order = post_order(directory)
    if before is None:
        cut = len(order)
    else:
        before = Path(before).resolve()
        cut = next((i for i, path in enumerate(order)
                    if path.resolve() == before), len(order))

    for path in reversed(order[:cut]):
        try:
            name = json.loads(path.read_text()).get("colorway")
        except (OSError, json.JSONDecodeError):
            continue
        if name in COLORWAYS:
            return name
    return None


def vary(chosen: str, previous: str | None) -> str:
    """`chosen`, unless the post before it already had that field.

    rhythm() refuses to put the same field on two neighbouring slides. This
    is that rule one level up, and it exists for the same reason: two posts
    running in the same hue read as one post in the grid, and the grid is
    the whole point of the palette rotating at all.

    It cost three posts before it existed — 2026-09-18 materials, 09-19
    biohybrid robotics and 09-20 applied thermodynamics all mapped to
    `ember`, and shipped as three amber posts in a row. Topic alone cannot
    avoid this: a science feed clusters, and four families divided among
    everything published means neighbours collide often.

    The substitute is the next family in COLORWAYS order whose pair differs
    from `previous`'s — the colours, not the name, since two families can
    share a pair. Deterministic, so the same queue always renders
    the same way and a test can say what it must do. The subject keeps its
    own family whenever the post before it leaves that family free, so the
    topic mapping still holds in the ordinary case — this only ever fires on
    a collision.
    """
    # Compared by the colours the reader sees, not the family name: two
    # families can wear the same pair (ember and signal, since 2026-09-30).
    if previous is None or COLORWAYS.get(chosen) != COLORWAYS.get(previous):
        return chosen
    order = list(COLORWAYS)
    at = order.index(chosen) if chosen in COLORWAYS else 0
    for step in range(1, len(order)):
        candidate = order[(at + step) % len(order)]
        if COLORWAYS[candidate] != COLORWAYS[previous]:
            return candidate
    return chosen


def slide_fields(name: str | None, count: int = 5,
                 catch: int | None = None) -> tuple[str, list[str]]:
    """Resolve a colorway to (lead hue, one field class name per slide)."""
    lead, support = colorway_pair(name)
    return lead, rhythm(lead, support, count, catch)


def render_html(post: dict, colorway: str | None = None,
                template: str | None = None) -> str:
    """The post in its format's template, or in `template` when named.

    reel.py names reel.html: the same context — flag, hook size, lead, rhythm
    — so the reel cannot come out in different colours or without the flag.
    """
    env = Environment(
        loader=FileSystemLoader(TEMPLATE_DIR),
        autoescape=select_autoescape(["html"]),
    )

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
        # The cover says what an unreviewed source is when it is not a
        # preprint. Post-level only, like the flag; a Signal labels items.
        show_announcement=not spec(post).entries and announcement(post),
        hook_size=hook_size_class(post.get("hook", "")),
        font_dir=(REPO_ROOT / "fonts").as_uri(),
        lead=lead,
        support=support,
        figure=cover_figure(post.get("hook", "")),
    )
    if "example_post" in spec(post).record:
        context["example_from"] = example_post(post)
    context["diff"] = catch_diff(post.get("the_catch", ""), context["figure"])
    env.filters["typeset"] = typeset
    env.filters["emphasis"] = (lambda text, figures_only=False:
                               emphasis(text, post.get("keywords"), figures_only))
    # The template calls this with its own slide count: it is the only thing
    # that knows how many it has, and this is the only thing that knows what
    # colour they go in.
    env.globals["PAIR"] = PAIR
    # signal.html labels each item by these, so a roundup cannot hold a
    # second opinion of what a preprint is.
    env.tests["preprint"] = preprint
    env.tests["announcement"] = announcement
    env.globals["rhythm"] = (lambda count, catch=None:
                             rhythm(lead, support, count, catch))
    # Fetched after the filters and globals are registered: Jinja resolves a
    # filter when it compiles a template, so a format that uses `typeset`
    # outside a slide_parts macro fails to load if it is fetched first.
    template = env.get_template(template or template_for(post.get("post_type")))
    return template.render(context)


@contextmanager
def open_page(html: str,
              size: tuple[int, int] = (SLIDE_W, SLIDE_H)) -> Iterator[Page]:
    """
    A Chromium page with the slides loaded and the webfonts settled.

    The page has to be loaded from file://, not injected with set_content():
    Chromium refuses local subresources on an about:blank page ("Not allowed
    to load local resource"), so the self-hosted fonts drop out silently and
    the slides render in a fallback face.

    proof.py measures the same page this screenshots, which is the point of
    it living here: a layout checked in a differently-built page is a layout
    nobody checked. reel.py opens it at the reel's 9:16 size for that reason.
    """
    with sync_playwright() as p, tempfile.TemporaryDirectory() as tmp:
        page_file = Path(tmp) / "slides.html"
        page_file.write_text(html)

        browser = p.chromium.launch()
        page = browser.new_page(
            viewport={"width": size[0], "height": size[1]},
            device_scale_factor=1,
        )
        page.goto(page_file.as_uri(), wait_until="load")
        page.wait_for_timeout(600)          # let webfonts settle
        # A template with a layout pass (slides_layout.js) measures glyphs and
        # moves boxes after the fonts load; it sets window.__ready false at
        # parse and true when done. Templates without one never set it.
        page.wait_for_function("window.__ready !== false", timeout=15_000)
        error = page.evaluate("window.__layoutError || null")
        if error:
            raise RuntimeError(
                f"The template's layout pass failed, so the slides would "
                f"render half-laid-out. Fix templates/slides_layout.js:\n{error}")
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


# The moving backdrop (templates/slides_layout.js) loops every
# window.__backdropLoop ms. Each slide is filmed over exactly one loop, so
# the clip repeats seamlessly in the carousel.
MOTION_FPS = 30


def film(html: str, outdir: Path) -> list[Path]:
    """One looping MP4 per slide, beside its PNG, for a moving carousel.

    Frames are stepped, not recorded, for the reason reel.py gives: the same
    post gives the same video. JPEG frames rather than PNG because encoding
    was most of the time, and the video is lossy anyway. Only the slide being
    filmed is repainted each frame. No ffmpeg or no WebGL is a warning, not a
    failure: the still carousel is complete without motion.
    """
    encoder = shutil.which("ffmpeg")
    if not encoder:
        print("  warning: ffmpeg is not installed, so no motion clips. It is "
              "free: `brew install ffmpeg` or `sudo apt-get install -y ffmpeg`.")
        return []
    written: list[Path] = []
    with open_page(html) as page:
        loop = page.evaluate("window.__backdropLoop || 0")
        if not loop:
            print("  warning: the backdrop did not draw (no WebGL in this "
                  "browser), so no motion clips — the PNGs are unaffected.")
            return []
        for i, el in enumerate(page.query_selector_all(".slide"), start=1):
            out = outdir / f"slide-{i}.mp4"
            proc = subprocess.Popen(
                [encoder, "-y", "-loglevel", "error",
                 "-f", "image2pipe", "-framerate", str(MOTION_FPS), "-i", "-",
                 # JPEG frames are full-range; Instagram expects TV range,
                 # and left as yuvj420p the colours shift on upload.
                 "-vf", "scale=in_range=pc:out_range=tv,format=yuv420p",
                 "-c:v", "libx264", "-crf", "18",
                 "-movflags", "+faststart", str(out)],
                stdin=subprocess.PIPE, stderr=subprocess.PIPE)
            for f in range(loop * MOTION_FPS // 1000):
                page.evaluate("([t, el]) => window.__backdrop(t, el)",
                              [f * 1000 / MOTION_FPS, el])
                proc.stdin.write(el.screenshot(type="jpeg", quality=92))
            proc.stdin.close()
            if proc.wait() != 0:
                err = proc.stderr.read().decode(errors="replace").strip()
                sys.exit(f"ffmpeg failed on {out.name}: {err or 'no output'}. "
                         f"Check the ffmpeg install has libx264, or re-run "
                         f"with --no-motion for stills only.")
            written.append(out)
            print(f"  wrote {shown(out)}")
    return written


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("post", help="path to the post JSON")
    ap.add_argument("--outdir", default=None, help="where to write PNGs")
    ap.add_argument("--colorway", default=None, choices=sorted(COLORWAYS),
                    help="override the colorway in the JSON")
    ap.add_argument("--no-motion", action="store_true",
                    help="stills only: skip the looping MP4 per slide")
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

    # draft.py applies vary() to what it writes, but a Breakdown is written
    # by hand and never passes through it — 2026-09-20's was the third amber
    # post in a row for exactly that reason. This is the same rule as a
    # warning rather than a rewrite, because render.py renders the record it
    # was given: say it, and let --colorway be the answer.
    used = args.colorway or post.get("colorway")
    if used and used == (before := previous_colorway(post_path)):
        print(f"  warning: {post_path.name} is the second {before} post in a "
              f"row — the post before it has the same field. Re-render with "
              f"--colorway {vary(used, before)} to break the run.")
    # How many slides, not whether: a Signal flags per item, so "ON" alone
    # said nothing about which of five claims is unreviewed.
    if flags := preprint_claims(post):
        print(f"  preprint flag ON — {flags} slide{'s' * (flags != 1)} "
              f"must carry it")
    elif announcement(post):
        print("  announcement — the cover says it is not a peer-reviewed "
              "study; check that the source really has no paper behind it")

    html = render_html(post, args.colorway)
    written = shoot(html, outdir)
    # Stale clips from an earlier render must not ride along with new stills.
    for old in outdir.glob("slide-*.mp4"):
        old.unlink()
    clips = [] if args.no_motion else film(html, outdir)

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
    print(f"\nDone. {len(written)} slides"
          + (f", {len(clips)} motion clips." if clips else "."))
    return 0


if __name__ == "__main__":
    sys.exit(main())
