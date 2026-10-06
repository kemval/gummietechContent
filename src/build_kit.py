#!/usr/bin/env python3
"""
Render The Build's brand kit for one episode: four 1080x1920 PNG stills.

The Build is a person's reel, recorded and cut by hand (docs §1), and
nothing here makes one. What this makes is the frames that keep it on the
grid's design: a cover in the Drop's hook styling, a title card for the
problem, a transparent lower third to lay over the screen recording, and an
end card. They are drop-in stills for the editor (CapCut, DaVinci).

The words come from docs/build_episodes.md — each episode's Cover, Problem
and End-on lines, verbatim — so the kit says what the episode list says and
a person edits that file, not this one.

Usage:
    python src/build_kit.py 1                  # episode 1, into output/build-01/
    python src/build_kit.py 3 --colorway orbit
    python src/build_kit.py --list
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from markupsafe import Markup, escape

from render import (COLORWAYS, DEFAULT_OUT, REPO_ROOT, TEMPLATE_DIR,
                    colorway_pair, emphasis, open_page, shown, typeset)

EPISODES = REPO_ROOT / "docs" / "build_episodes.md"
SIZE = (1080, 1920)
FRAMES = ("cover", "problem", "lower-third", "end")

HEADING = re.compile(r"^### (\d+) · (.+)$")
FIELD = re.compile(r"^- \*\*(Cover|Problem|End on)\*\* — (.+)$")


def unquote(text: str) -> str:
    """The episode list quotes its spoken lines; the frames do not."""
    return text.strip().strip('"“”').strip()


def inline_code(text: str) -> Markup:
    """`backticked` names in the episode list, set in the mono face."""
    parts = re.split(r"`([^`]+)`", text)
    return Markup("".join(
        f"<code>{escape(p)}</code>" if i % 2 else str(escape(p))
        for i, p in enumerate(parts)))


def episodes(path: Path = EPISODES) -> dict[int, dict]:
    """Every episode in the list that has a Cover, a Problem and an End on."""
    found: dict[int, dict] = {}
    current: dict | None = None
    for line in path.read_text().splitlines():
        if m := HEADING.match(line):
            current = {"number": int(m.group(1)), "title": m.group(2).strip()}
            found[current["number"]] = current
        elif current is not None and (m := FIELD.match(line)):
            current[{"Cover": "cover", "Problem": "problem",
                     "End on": "end"}[m.group(1)]] = m.group(2)
    return {n: e for n, e in found.items()
            if {"cover", "problem", "end"} <= e.keys()}


def render_kit(episode: dict, colorway: str | None, outdir: Path) -> list[Path]:
    env = Environment(loader=FileSystemLoader(TEMPLATE_DIR),
                      autoescape=select_autoescape(["html"]))
    env.filters["typeset"] = typeset
    env.filters["emphasis"] = lambda text, figures_only=False: emphasis(
        text, [], figures_only)
    lead, support = colorway_pair(colorway)
    html = env.get_template("build.html").render(
        font_dir=(REPO_ROOT / "fonts").as_uri(), lead=lead,
        support=support,
        episode={
            "number": episode["number"],
            "title": episode["title"],
            "cover": typeset(unquote(episode["cover"])),
            "problem": inline_code(typeset(episode["problem"])),
            "end": typeset(unquote(episode["end"])),
        },
        # slide_parts.html reads these; a Build has no post record behind it.
        show_preprint_flag=False, figure=None, diff=None, domain="")

    outdir.mkdir(parents=True, exist_ok=True)
    written = []
    with open_page(html, size=SIZE) as page:
        for name in FRAMES:
            out = outdir / f"{name}.png"
            # The lower third is the only one with no field of its own: it
            # is saved with an alpha channel so the recording shows through.
            page.locator(f"#{name}").screenshot(
                path=str(out), omit_background=(name == "lower-third"))
            written.append(out)
            print(f"  wrote {shown(out)}")
    return written


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("episode", nargs="?", type=int,
                    help="episode number in docs/build_episodes.md")
    ap.add_argument("--colorway", default="signal", choices=sorted(COLORWAYS),
                    help="the field hue family (default signal: the Build "
                         "is about software)")
    ap.add_argument("--outdir", type=Path, default=None,
                    help="default output/build-NN/")
    ap.add_argument("--list", action="store_true", help="list the episodes")
    args = ap.parse_args()

    found = episodes()
    if args.list or args.episode is None:
        for n, e in sorted(found.items()):
            print(f"  {n:2}  {e['title']}")
        return 0
    if args.episode not in found:
        sys.exit(f"No episode {args.episode} with a Cover, Problem and End on "
                 f"line in {EPISODES.relative_to(REPO_ROOT)}. "
                 f"Run with --list to see the numbers.")

    outdir = args.outdir or DEFAULT_OUT / f"build-{args.episode:02d}"
    print(f"The Build #{args.episode:02d} kit → {shown(outdir)}")
    render_kit(found[args.episode], args.colorway, outdir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
