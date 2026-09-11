#!/usr/bin/env python3
"""
Build the web archive: posts/*.json to a static site.

One page per carousel plus an index, published to GitHub Pages. This is
what the Instagram bio links to, and it exists for one reason: Instagram
does not make caption URLs clickable, so `source_url` — which draft.py
records and render.py writes into caption.txt — never reaches a reader.
Slide 5 shows `attribution` as plain text and points here.

No new writing per post: every page is a pure function of the JSON the
drafting step already produces.

Usage:
    python src/site.py
    python src/site.py --outdir /tmp/preview

Pages ship both languages and show one, toggled by the button in the
masthead. The Spanish comes from the post's `es` block, written by
translate.py; a post without a complete one is simply English-only, and
the toggle disappears when no post on the page has been translated.

A post is published only when it carries a `published_at` date. draft.py
writes into posts/ BEFORE the human gate, so building from every file
there would put unreviewed drafts on the open web — the exact failure
Layer 5 exists to prevent. Add the date by hand when the post goes live.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

from jinja2 import Environment, FileSystemLoader, select_autoescape
from markupsafe import Markup, escape

from render import ES_FIELDS, REPO_ROOT, REQUIRED, slide_fields

POSTS_DIR = REPO_ROOT / "posts"
TEMPLATE_DIR = REPO_ROOT / "templates"
FONTS_DIR = REPO_ROOT / "fonts"
DEFAULT_OUT = REPO_ROOT / "site"


# Hard-coded rather than taken from the C locale: es_ES is not installed on
# a GitHub Actions runner by default, and a missing locale would silently
# fall back to English dates on the deployed site.
MONTHS_ES = ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
             "agosto", "septiembre", "octubre", "noviembre", "diciembre")


def human_date(d: date) -> str:
    """'3 September 2026'. Built from the parts rather than with %-d,
    which is not portable off glibc/BSD."""
    return f"{d.day} {d:%B %Y}"


def human_date_es(d: date) -> str:
    """'3 de septiembre de 2026'."""
    return f"{d.day} de {MONTHS_ES[d.month - 1]} de {d.year}"


def spanish(post: dict, name: str) -> dict:
    """
    The post's usable `es` block, or {} when there is not a complete one.

    Partial Spanish is worse than none: a reader who switches language and
    gets a Spanish hook over an English catch cannot tell a missing
    translation from a sloppy one. Degrade the whole post instead.
    """
    es = post.get("es")
    if not isinstance(es, dict):
        if es is not None:
            print(f"  warning: {name}: `es` is not an object — ignoring it")
        return {}

    wanted = [f for f in ES_FIELDS if str(post.get(f, "")).strip()]
    missing = [f for f in wanted if not str(es.get(f, "")).strip()]
    if missing:
        print(f"  warning: {name}: `es` is missing {', '.join(missing)} — "
              "the page stays English. Run `python src/translate.py "
              f"posts/{name}` to fill it in")
        return {}
    return {f: es[f] for f in wanted}


def t(en: str, es: str = "") -> Markup:
    """
    One string in both languages, for the page's language toggle.

    Both are in the DOM and CSS shows the one `<html data-lang>` names, so
    switching needs no rebuild and no second set of pages. An untranslated
    string gets no `data-lang`, which leaves it visible in both languages —
    the fallback the whole toggle degrades through.

    The `lang` attribute is not decoration: without it a screen reader
    pronounces the Spanish with an English voice.
    """
    if not es:
        return Markup(f"<span>{escape(en)}</span>")
    return Markup(f'<span lang="en" data-lang="en">{escape(en)}</span>'
                  f'<span lang="es" data-lang="es">{escape(es)}</span>')


def source_host(url: str) -> str:
    """A readable link label. The full URL of a press release is long,
    ugly, and tells a reader less than the publisher's domain does."""
    netloc = urlparse(url).netloc
    if netloc.startswith("www."):
        netloc = netloc[4:]
    return netloc or url


def absolute(url: str) -> str:
    """draft.py records code_url as the model wrote it, which is usually
    bare ('github.com/google-research/era'). A bare host in an href is
    read as a relative path, so the link would 404 inside the site."""
    return url if "://" in url else f"https://{url}"


def load_posts() -> tuple[list[dict], int]:
    """
    Every published post, newest first, plus a count of what was skipped.

    Skips with a warning rather than exiting: render.py is right to
    hard-fail a single post it was asked to render, but one malformed
    draft must not take the whole site down.
    """
    posts: list[dict] = []
    skipped = 0

    for path in sorted(POSTS_DIR.glob("*.json")):
        try:
            post = json.loads(path.read_text())
        except json.JSONDecodeError as exc:
            print(f"  skipped {path.name}: not valid JSON ({exc})")
            skipped += 1
            continue

        published_at = str(post.get("published_at", "")).strip()
        if not published_at:
            print(f"  skipped {path.name}: no published_at — still behind "
                  "the human gate")
            skipped += 1
            continue

        try:
            published = date.fromisoformat(published_at)
        except ValueError:
            print(f"  skipped {path.name}: published_at is "
                  f"{published_at!r}, expected YYYY-MM-DD")
            skipped += 1
            continue

        missing = [f for f in REQUIRED if not post.get(f)]
        if missing:
            print(f"  skipped {path.name}: missing {', '.join(missing)}")
            skipped += 1
            continue

        # Never defaulted. An unlabelled preprint is the same credibility
        # risk here as it is on slide 4, so the post stays off the site
        # until someone says which it is.
        if not isinstance(post.get("peer_reviewed"), bool):
            print(f"  skipped {path.name}: peer_reviewed is not true or "
                  "false — an unlabelled preprint is a credibility risk")
            skipped += 1
            continue

        # Same allowlist the slides use, so the page carries the post's
        # topic hue and an invented family name degrades identically.
        lead, _ = slide_fields(post.get("colorway"))

        post.update(
            slug=path.stem,
            lead=lead,
            published=published,
            published_on=human_date(published),
            published_on_es=human_date_es(published),
            es=spanish(post, path.name),
            source_host=source_host(post["source_url"]),
            code_href=absolute(post["code_url"]) if post.get("code_url") else "",
            domain=post.get("domain", ""),
        )
        posts.append(post)

    posts.sort(key=lambda p: p["published"], reverse=True)
    return posts, skipped


def prepare(outdir: Path) -> None:
    """
    Clear a previous build so an unpublished post's page cannot linger.

    Only an absent, empty, or previously-built directory is removed:
    --outdir is a free-form path and must not be able to delete an
    unrelated directory because of a typo.
    """
    if outdir.exists():
        if any(outdir.iterdir()) and not (outdir / "index.html").exists():
            sys.exit(
                f"{outdir} is not empty and does not look like a previous "
                "site build (no index.html at its root).\n"
                "Point --outdir at a new directory, or delete that one first."
            )
        shutil.rmtree(outdir)
    outdir.mkdir(parents=True)


def build(posts: list[dict], outdir: Path) -> None:
    env = Environment(
        loader=FileSystemLoader(TEMPLATE_DIR),
        autoescape=select_autoescape(["html"]),
    )
    env.globals["t"] = t

    # The toggle is only offered where there is something to toggle to.
    # A button that swaps the furniture around unchanged English prose
    # advertises a Spanish edition the archive does not have.
    translated = [p for p in posts if p["es"]]

    # `base` is the path back to the site root: post pages live one
    # directory down. Relative, not root-absolute, because Pages serves
    # this under /gummietechContent/ while a local preview is opened at file://.
    (outdir / "index.html").write_text(
        env.get_template("index.html").render(
            posts=posts, base="", translated=bool(translated))
    )
    print(f"  wrote index.html ({len(posts)} post{'s' * (len(posts) != 1)})")

    post_template = env.get_template("post.html")
    for post in posts:
        page = outdir / post["slug"]
        page.mkdir()
        (page / "index.html").write_text(
            post_template.render(post=post, base="../",
                                 translated=bool(post["es"]))
        )
        print(f"  wrote {post['slug']}/index.html")

    # Self-hosted for the same reason drop.html avoids the CDN: the look
    # should not depend on a third party staying up.
    shutil.copytree(FONTS_DIR, outdir / "fonts")
    print("  wrote fonts/")
    print(f"  {len(translated)} of {len(posts)} page"
          f"{'s' * (len(posts) != 1)} carry Spanish")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--outdir", default=None, help="where to build the site")
    args = ap.parse_args()

    outdir = Path(args.outdir) if args.outdir else DEFAULT_OUT
    if not outdir.is_absolute():
        outdir = REPO_ROOT / outdir

    print(f"Building {POSTS_DIR.name}/ → {outdir}")
    posts, skipped = load_posts()

    prepare(outdir)
    build(posts, outdir)

    print(f"\nDone. {len(posts)} published, {skipped} skipped.")
    if not posts:
        print("Nothing is published yet. Add \"published_at\": "
              f"\"{date.today():%Y-%m-%d}\" to a post JSON once it has "
              "cleared the human gate.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
