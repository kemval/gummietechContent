#!/usr/bin/env python3
"""
Render a published Drop as a silent 1080x1920 reel.

The reel is the carousel's own five slides, swiped through one at a time —
templates/reel.html includes the same partial drop.html does, so a reel can
say nothing its carousel did not. That is what lets it skip the fact-check:
every claim in it already passed one, and a person already approved it at
the gate. It is also why this refuses a post without `published_at` unless
told `--draft`, which is for previewing locally and the smoke fixture only.

Captured frame by frame rather than recorded. Playwright can record video,
but in real time, so a slow runner drops frames; and its fake clock drives
JavaScript timers, not CSS animations. So every animation on the page is
paused and stepped to each frame's time through the Web Animations API, and
the screenshots are piped into ffmpeg. The same JSON gives the same video.

ffmpeg is the one tool here that is not a Python package. It is free, and it
is *not* on GitHub's ubuntu-24.04 image — reel.yml apt-installs it.

Audio is not added. Trending audio can only be chosen inside the Instagram
app, and choosing it is a person's call.

Usage:
    python src/reel.py posts/2026-09-15-tides.json
    python src/reel.py --latest              # newest published Drop without a reel
    python src/reel.py --which               # ...just print which that is
    python src/reel.py posts/era.json --draft
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

from proof import Report
from render import (DEFAULT_OUT, REPO_ROOT, format_name, load_post,
                    open_page, post_order, post_preprint_flag, render_html,
                    shown, warn_on_length)

REEL_W, REEL_H = 1080, 1920
FPS = 30

# Instagram draws the account name over the top of a reel and the caption,
# audio line and buttons over the bottom. Measured by others rather than
# published by Meta, so these are the conservative end of what they report.
SAFE_TOP = 200
SAFE_BOTTOM = REEL_H - 400

TEMPLATE = "reel.html"
VIDEO = "reel.mp4"
COVER = "reel-cover.png"
REPORT = "reel-proof.md"

# Pauses every animation and returns when the last one ends. The template
# owns the reel's length; this only reads it.
PAUSE = """
() => {
  const all = document.getAnimations();
  all.forEach(a => a.pause());
  return Math.max(0, ...all.map(a => a.effect.getComputedTiming().endTime));
}
"""

SEEK = "t => { for (const a of document.getAnimations()) a.currentTime = t; }"

# When each scene starts: its slide's swipe delay, 0 for the first slide,
# which is on screen from the first frame.
SCENES = """
() => [...document.querySelectorAll('.card > .slide')].map(s => {
  const own = s.getAnimations().map(a => a.effect.getComputedTiming().delay);
  return own.length ? Math.min(...own) : 0;
})
"""

BOXES = """
() => [...document.querySelectorAll('.card > .slide')].map(s => {
  const r = s.getBoundingClientRect();
  return {top: r.top, bottom: r.bottom, left: r.left, right: r.right};
})
"""

# Whether the flag is fully there on this frame: present, laid out, inside
# the safe zone, and at full opacity all the way up the tree.
FLAG = """
([top, bottom, width]) => {
  const el = document.querySelector('.reel-flag');
  if (!el) return 'missing';
  const r = el.getBoundingClientRect();
  if (!r.width || !r.height) return 'not laid out';
  if (r.top < top || r.bottom > bottom || r.left < 0 || r.right > width)
    return `outside the safe zone (y ${Math.round(r.top)}-${Math.round(r.bottom)})`;
  for (let n = el; n; n = n.parentElement) {
    const s = getComputedStyle(n);
    if (s.visibility !== 'visible' || s.display === 'none' || +s.opacity < 1)
      return 'not fully visible';
  }
  return '';
}
"""


def latest() -> Path:
    """The newest published Drop that has no reel yet."""
    for path in reversed(post_order()):
        post = json.loads(path.read_text())
        if (post.get("published_at") and not post.get("reel")
                and format_name(post.get("post_type")) == "drop"):
            return path
    sys.exit("No published Drop is waiting for a reel. Name one with the "
             "post input, e.g. posts/2026-09-15-tides.json.")


def ffmpeg() -> str:
    found = shutil.which("ffmpeg")
    if not found:
        sys.exit("ffmpeg is not installed. It is free: `brew install ffmpeg` "
                 "on macOS, `sudo apt-get install -y ffmpeg` on Ubuntu.")
    return found


def check_scenes(page, report: Report) -> list[float]:
    """Each scene's slide, settled, must sit inside the safe zone.

    Measured at the last moment of the scene, when its slide has landed and
    the next has not started. The words inside are not measured again: the
    markup is the carousel's, and proof.py already measured that.
    """
    starts: list[float] = page.evaluate(SCENES)
    end = page.evaluate(PAUSE)
    ends = [*starts[1:], end]
    for i, t in enumerate(ends):
        page.evaluate(SEEK, max(t - 1, 0))
        box = page.evaluate(BOXES)[i]
        if box["top"] < SAFE_TOP or box["bottom"] > SAFE_BOTTOM:
            report.block(f"scene {i + 1}",
                         f"slide spans y {box['top']:.0f}-{box['bottom']:.0f}; "
                         f"Instagram covers above {SAFE_TOP} and below "
                         f"{SAFE_BOTTOM}")
        if box["left"] < 0 or box["right"] > REEL_W:
            report.block(f"scene {i + 1}", "slide runs off the side of the frame")
    if len(starts) != 5:
        report.block("template", f"{len(starts)} scene(s); a Drop reel has 5")
    return ends


def capture(html: str, outdir: Path, flagged: bool) -> Report:
    report = Report()
    encoder = ffmpeg()
    video, cover = outdir / VIDEO, outdir / COVER

    with open_page(html, size=(REEL_W, REEL_H)) as page:
        length = page.evaluate(PAUSE)
        ends = check_scenes(page, report)

        # The hook scene settled is the natural cover — the carousel's own
        # first slide, which is what the grid will show beside it.
        page.evaluate(SEEK, ends[0] - 1)
        page.screenshot(path=str(cover))

        frames = int(length * FPS / 1000) + 1
        proc = subprocess.Popen(
            [encoder, "-y", "-loglevel", "error",
             "-f", "image2pipe", "-framerate", str(FPS), "-i", "-",
             "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18",
             "-movflags", "+faststart", str(video)],
            stdin=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            for i in range(frames):
                t = i * 1000 / FPS
                page.evaluate(SEEK, t)
                # Enforced here, per frame, not by the template's promise:
                # a preprint must carry its label for the whole reel.
                if flagged:
                    wrong = page.evaluate(FLAG, [SAFE_TOP, SAFE_BOTTOM, REEL_W])
                    if wrong:
                        proc.kill()
                        video.unlink(missing_ok=True)
                        sys.exit(f"Preprint flag {wrong} at {t / 1000:.2f}s. "
                                 f"A preprint reel must show it on every "
                                 f"frame — check .reel-flag in "
                                 f"templates/{TEMPLATE}.")
                proc.stdin.write(page.screenshot(type="png"))
            proc.stdin.close()
        except BrokenPipeError:
            pass
        if proc.wait() != 0:
            err = proc.stderr.read().decode(errors="replace").strip()
            sys.exit(f"ffmpeg failed: {err or 'no output'}. The frames were "
                     f"fine; check the ffmpeg install has libx264.")

    print(f"  wrote {shown(video)} — {frames} frames, {length / 1000:.1f}s")
    print(f"  wrote {shown(cover)}")
    report.note("reel", f"{length / 1000:.1f}s at {FPS} fps, silent — add "
                        f"audio in the Instagram app")
    return report


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("post", nargs="?", type=Path, help="path to the post JSON")
    ap.add_argument("--latest", action="store_true",
                    help="the newest published Drop without a reel")
    ap.add_argument("--which", action="store_true",
                    help="print the post --latest would pick, and exit — "
                         "reel.yml names it to render.py and telegram.py too")
    ap.add_argument("--draft", action="store_true",
                    help="allow an unpublished post (local preview only)")
    ap.add_argument("--outdir", type=Path, default=None,
                    help="default output/<stem>/, beside the slides")
    args = ap.parse_args()

    if args.which:
        print(latest().relative_to(REPO_ROOT))
        return 0
    if args.latest == bool(args.post):
        sys.exit("Name a post, or pass --latest — one of the two.")
    path = latest() if args.latest else args.post
    if not path.is_absolute():
        path = REPO_ROOT / path
    if not path.exists():
        sys.exit(f"No such post file: {path}")

    post = load_post(path)
    if format_name(post.get("post_type")) != "drop":
        sys.exit(f"{path.name} is a {post.get('post_type')}; only a Drop has "
                 f"a reel so far.")
    if not post.get("published_at") and not args.draft:
        sys.exit(f"{path.name} has no published_at. A reel repeats claims the "
                 f"gate already approved, so it waits for the carousel to go "
                 f"out. Pass --draft to preview it locally.")
    warn_on_length(post)

    outdir = args.outdir or DEFAULT_OUT / path.stem
    if not outdir.is_absolute():
        outdir = REPO_ROOT / outdir
    outdir.mkdir(parents=True, exist_ok=True)

    print(f"Rendering the reel for {path.name} → {shown(outdir)}")
    flagged = post_preprint_flag(post)
    report = capture(render_html(post, template=TEMPLATE), outdir, flagged)

    text = report.render()
    (outdir / REPORT).write_text(text + "\n")
    print(text)
    return 1 if report.verdict == "BLOCK" else 0


if __name__ == "__main__":
    sys.exit(main())
