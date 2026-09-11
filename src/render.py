#!/usr/bin/env python3
"""
Render a Drop post to five 1080x1350 PNGs.

Reads a post JSON record, injects it into templates/drop.html with Jinja2,
and screenshots each .slide div individually with Playwright.

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
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from playwright.sync_api import sync_playwright

REPO_ROOT = Path(__file__).resolve().parent.parent
TEMPLATE_DIR = REPO_ROOT / "templates"
DEFAULT_OUT = REPO_ROOT / "output"

SLIDE_W, SLIDE_H = 1080, 1350
SLIDE_IDS = ["slide-1", "slide-2", "slide-3", "slide-4", "slide-5"]

REQUIRED = ["hook", "what_happened", "why_it_matters", "the_catch",
            "attribution", "alt_text", "source_url"]

# The fields the web archive shows in Spanish when a post carries an `es`
# block: translate.py writes them, site.py renders them behind the page's
# language toggle. The slides are English only, so nothing here touches a
# render — the list lives in this module because it is the one both of those
# can import. site.py cannot be imported by name (the standard library owns
# `site`), and site.py must not pull in the LLM stack just to build a page.
ES_FIELDS = ("domain", "hook", "what_happened", "why_it_matters", "the_catch")

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

    missing = [f for f in REQUIRED if not post.get(f)]
    if missing:
        sys.exit(
            f"Refusing to render. Missing required field(s): {', '.join(missing)}.\n"
            "attribution and alt_text are mandatory — add them to the JSON and re-run."
        )

    # peer_reviewed must be explicit. Defaulting it to True would let an
    # unlabelled preprint through, which is the exact failure this guards.
    if "peer_reviewed" not in post:
        sys.exit(
            "Refusing to render. `peer_reviewed` is missing.\n"
            "Set it to true or false — an unlabelled preprint is a credibility risk."
        )

    return post


def warn_on_length(post: dict) -> None:
    """Word limits are a style rule, so warn rather than fail."""
    checks = [
        ("hook", HOOK_WORD_LIMIT),
        ("what_happened", WORD_LIMIT),
        ("why_it_matters", WORD_LIMIT),
        ("the_catch", WORD_LIMIT),
    ]
    for field, limit in checks:
        count = len(str(post.get(field, "")).split())
        if count > limit:
            print(f"  warning: {field} is {count} words (limit {limit}) — "
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


def slide_fields(name: str | None) -> tuple[str, list[str]]:
    """
    Resolve a colorway name to (lead hue, five field class names).

    An unknown name warns and falls back rather than exiting: a wrong hue is
    cosmetic, unlike a missing attribution, and refusing to render would
    throw away the Gemini call that produced the draft.
    """
    if name not in COLORWAYS:
        if name:
            print(f"  warning: unknown colorway {name!r} — using "
                  f"{DEFAULT_COLORWAY}. Valid: {', '.join(COLORWAYS)}")
        name = DEFAULT_COLORWAY

    lead, support = COLORWAYS[name]
    return lead, [lead, "cream", support, "dark", lead]


def render_html(post: dict, colorway: str | None = None) -> str:
    env = Environment(
        loader=FileSystemLoader(TEMPLATE_DIR),
        autoescape=select_autoescape(["html"]),
    )
    template = env.get_template("drop.html")

    lead, fields = slide_fields(colorway or post.get("colorway"))

    # Built as a dict rather than splatted as **post: a post JSON carrying a
    # key that collides with one of the computed values would otherwise raise
    # "got multiple values for keyword argument".
    context = dict(post)
    context.update(
        show_preprint_flag=not post.get("peer_reviewed", False),
        hook_size=hook_size_class(post.get("hook", "")),
        font_dir=(REPO_ROOT / "fonts").as_uri(),
        lead=lead,
        fields=fields,
    )
    return template.render(context)


def shoot(html: str, outdir: Path) -> list[Path]:
    outdir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    with sync_playwright() as p, tempfile.TemporaryDirectory() as tmp:
        # The page has to be loaded from file://, not injected with set_content():
        # Chromium refuses local subresources on an about:blank page ("Not allowed
        # to load local resource"), so the self-hosted fonts drop out silently
        # and the slides render in a fallback face.
        page_file = Path(tmp) / "slides.html"
        page_file.write_text(html)

        browser = p.chromium.launch()
        page = browser.new_page(
            viewport={"width": SLIDE_W, "height": SLIDE_H},
            device_scale_factor=1,
        )
        page.goto(page_file.as_uri(), wait_until="load")
        page.wait_for_timeout(600)          # let webfonts settle

        for i, slide_id in enumerate(SLIDE_IDS, start=1):
            el = page.query_selector(f"#{slide_id}")
            if el is None:
                print(f"  warning: #{slide_id} not found in template, skipping")
                continue
            out = outdir / f"slide-{i}.png"
            el.screenshot(path=str(out))
            written.append(out)
            print(f"  wrote {shown(out)}")

        browser.close()
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
    if not post.get("peer_reviewed"):
        print("  preprint flag ON (peer_reviewed is false)")

    written = shoot(render_html(post, args.colorway), outdir)

    # The caption and alt text are needed at posting time, so drop them
    # next to the images rather than making you dig back into the JSON.
    # Hashtags ride with the caption so the top block pastes into Business Suite
    # in one go, rather than being retyped from the JSON.
    tags = " ".join(post.get("hashtags") or [])
    sidecar = outdir / "caption.txt"
    sidecar.write_text(
        f"{post.get('caption', '')}\n"
        + (f"\n{tags}\n" if tags else "")
        + f"\n--- ALT TEXT ---\n{post['alt_text']}\n\n"
        f"--- ATTRIBUTION ---\n{post['attribution']}\n{post['source_url']}\n"
    )
    print(f"  wrote {shown(sidecar)}")
    print(f"\nDone. {len(written)} slides.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
