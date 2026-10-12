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
    python src/site.py --newsletter        # the last week, as a page to copy

Besides the pages it writes feed.xml (RSS 2.0, newest first) and, per month
with a published post, <yyyy-mm>/ — that month on one printable page — and
its PDF, the download a reader can keep.

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
import contextlib
import json
import os
import shutil
import sys
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta, timezone
from email.utils import format_datetime
from pathlib import Path
from urllib.parse import urlparse

from jinja2 import Environment, FileSystemLoader, select_autoescape
from markupsafe import Markup, escape

from formats import (PAIR, announcement, entries, es_fields,
                     missing_from_entries, pieces, post_preprint_flag,
                     preprint, required, sections, spec, unpaired)
from render import REPO_ROOT, colorway_pair, open_page, render_html, typeset

POSTS_DIR = REPO_ROOT / "posts"
TEMPLATE_DIR = REPO_ROOT / "templates"
FONTS_DIR = REPO_ROOT / "fonts"
DEFAULT_OUT = REPO_ROOT / "site"

# Where Pages serves the archive — the Instagram bio link. Link-preview tags
# must be absolute, and a crawler never sees the relative `base` the pages
# navigate by. Written down rather than derived: the build runs locally too,
# where nothing knows the public address.
SITE_URL = "https://kemval.github.io/gummietechContent/"

# Cloudflare Web Analytics' beacon token, from a repo variable in site.yml.
# Public by design — it ships in every page — but configuration, not code:
# without it no script is added, so a local build and a fork measure nothing.
BEACON_ENV = "CF_BEACON_TOKEN"

FEED = "feed.xml"
NEWSLETTER_DAYS = 7


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

    wanted = [f for f in es_fields(post) if post.get(f)]
    missing = [f for f in wanted if not es.get(f)]
    if missing:
        print(f"  warning: {name}: `es` is missing {', '.join(missing)} — "
              "the page stays English. Run `python src/translate.py "
              f"posts/{name}` to fill it in")
        return {}
    return {f: es[f] for f in wanted}


def body_sections(post: dict, es_block: dict) -> list[dict]:
    """Each body section as {label, pieces}, English paired with Spanish.

    A section's label is only translated when the post's Spanish survived
    validation: a Spanish heading over an English paragraph is the mixed
    edition spanish() exists to prevent.
    """
    out = []
    for section in sections(post):
        english = pieces(post, section)
        spanish_pieces = es_block.get(section.field) if es_block else None
        if isinstance(spanish_pieces, str):
            spanish_pieces = [spanish_pieces]
        # A length mismatch means a translation lost or gained a slide.
        # translate.py refuses to write one, so this is belt and braces: pair
        # what lines up and leave the rest English rather than misalign them.
        if not spanish_pieces or len(spanish_pieces) != len(english):
            spanish_pieces = [""] * len(english)
        pairs = list(zip(english, spanish_pieces))
        out.append({
            "en": section.en,
            "es": section.es if es_block else "",
            "pieces": pairs,
            # A cheat sheet's "Term: line", split so the page can set the
            # term bold as the slide does. A Spanish piece that lost the
            # separator in translation is shown in English, both halves,
            # rather than split in the wrong place.
            "terms": [split_pair(en, es) for en, es in pairs]
                     if section.pair else [],
        })
    return out


def split_pair(en: str, es: str) -> tuple[tuple[str, str], tuple[str, str]]:
    """((term_en, term_es), (line_en, line_es)) from two "Term: line"
    pieces. render.py and site.py refuse an English piece without the
    separator, so only the Spanish half can lack it."""
    term_en, _, line_en = en.partition(PAIR)
    term_es, sep, line_es = es.partition(PAIR)
    if not sep:
        term_es = line_es = ""
    return (term_en, term_es), (line_en, line_es)


def t(en: str, es: str = "") -> Markup:
    """
    One string in both languages, for the page's language toggle.

    Both are in the DOM and CSS shows the one `<html data-lang>` names, so
    switching needs no rebuild and no second set of pages. An untranslated
    string gets no `data-lang`, which leaves it visible in both languages —
    the fallback the whole toggle degrades through.

    The `lang` attribute is not decoration: without it a screen reader
    pronounces the Spanish with an English voice.

    `typeset` is the slides' one character change ("1.81x" → "1.81×"), so
    a number reads the same on the page as on the carousel it came from.
    """
    en, es = typeset(en), typeset(es)
    if not es:
        return Markup(f"<span>{escape(en)}</span>")
    return Markup(f'<span lang="en" data-lang="en">{escape(en)}</span>'
                  f'<span lang="es" data-lang="es">{escape(es)}</span>')


def source_entry(record: dict) -> dict:
    """One line of a post page's source list: who, where, and what it is.

    `status` is "reviewed", "preprint" or "announcement" — the three things a
    source can be, decided once by formats.py for the slides and the page.
    """
    status = ("preprint" if preprint(record)
              else "announcement" if announcement(record) else "reviewed")
    return {"attribution": record["attribution"],
            "url": record["source_url"],
            "host": source_host(record["source_url"]),
            "status": status}


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

        missing = ([f for f in required(post) if post.get(f) is None
                    or (f != "peer_reviewed" and not post.get(f))]
                   + missing_from_entries(post) + unpaired(post))
        if missing:
            print(f"  skipped {path.name}: missing {', '.join(missing)}")
            skipped += 1
            continue

        # Never defaulted. An unlabelled preprint is the same credibility
        # risk here as it is on the dark slide, so the post stays off the
        # site until someone says which it is — per item for a Signal, whose
        # five sources answer independently.
        flags = [e.get("peer_reviewed") for e in entries(post)] \
            or [post.get("peer_reviewed")]
        if not all(isinstance(f, bool) for f in flags):
            print(f"  skipped {path.name}: peer_reviewed is not true or "
                  "false — an unlabelled preprint is a credibility risk")
            skipped += 1
            continue

        # A glossary term's example is a post of ours, and its paper is a
        # second source (§7.3): credited from that post's own record, and
        # linked — unless it is the definition's own source, which is then
        # listed once. An example that is missing or was never published is the
        # same refusal render.example_post() makes, as a skip.
        example = None
        if "example_post" in spec(post).record:
            stem = str(post.get("example_post", "")).strip()
            try:
                example = json.loads((POSTS_DIR / f"{stem}.json").read_text())
            except (OSError, ValueError):
                example = None
            if (not example or Path(stem).name != stem
                    or not example.get("published_at")):
                print(f"  skipped {path.name}: example_post {stem!r} is not a "
                      "published post in posts/")
                skipped += 1
                continue
            example["slug"] = stem

        # Same allowlist the slides use, so the page carries the post's
        # topic hue and an invented family name degrades identically.
        lead, support = colorway_pair(post.get("colorway"))

        # Resolved before the body is built, because the body pairs each
        # English piece with its Spanish and must use the block that passed
        # validation rather than the raw one that may have just failed it.
        es_block = spanish(post, path.name)

        post.update(
            slug=path.stem,
            lead=lead,
            support=support,
            published=published,
            published_on=human_date(published),
            published_on_es=human_date_es(published),
            es=es_block,
            # The body in reading order, already paired with its Spanish, so
            # post.html prints a Breakdown's six sections and a Drop's three
            # from one loop. A section holds a list of pieces because a
            # Breakdown's mechanism is one entry per slide.
            body=body_sections(post, es_block),
            # One list for every format: a Drop and a Breakdown have a
            # single source, a Signal has one per item. §7.3 makes credit
            # mandatory per source, so the page prints them all.
            # Each source carries its label already decided, by the rule
            # the slides use (formats.preprint), so the page cannot call an
            # announcement a preprint the slides did not.
            sources=[source_entry(e) for e in entries(post)]
                    or [source_entry(post)]
                    + ([source_entry(example)]
                       if example and example.get("source_url")
                       != post.get("source_url") else []),
            example=example,
            # The hero flag is a claim about the whole post, so it is only
            # shown where the whole post has one source. A Signal labels its
            # preprints beside the items they belong to.
            preprint=post_preprint_flag(post),
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


def covers(posts: list[dict], outdir: Path) -> None:
    """Each post's first slide as <slug>/cover.png, for its link preview.

    Rendered from the post JSON exactly as render.py renders it — same
    render_html(), same open_page() — so a pasted link shows the cover that
    went to Instagram rather than a second design of it. From the file, not
    from the dict load_posts() has decorated for the page templates.

    A browser that will not launch (Chromium not installed, which is the
    normal state of a laptop that has never rendered) is not a failed build:
    it says so once and the pages go out with text-only previews. The first
    failure stops the rest, since it is almost always that same cause and
    thirty identical warnings bury it.
    """
    for post in posts:
        try:
            raw = json.loads((POSTS_DIR / f"{post['slug']}.json").read_text())
            with open_page(render_html(raw)) as page:
                first = page.query_selector(".slide")
                if first is None:
                    raise RuntimeError("the template rendered no .slide")
                first.screenshot(path=str(outdir / post["slug"] / "cover.png"))
            post["cover"] = True
        except Exception as exc:              # noqa: BLE001 — see docstring
            print(f"  warning: no preview images — {post['slug']} would not "
                  f"render ({str(exc).splitlines()[0]}). Run `python -m "
                  f"playwright install chromium` to build them locally; the "
                  "pages are built without them.")
            return
    print(f"  wrote {len(posts)} cover.png preview image"
          f"{'s' * (len(posts) != 1)}")


def summary(post: dict) -> str:
    """One paragraph for the feed and the newsletter: why it matters where
    the format has it, else its first body piece."""
    for section in post["body"]:
        if section["en"] == "Why it matters":
            return " ".join(en for en, _ in section["pieces"])
    first = post["body"][0]["pieces"] if post["body"] else []
    return first[0][0] if first else ""


def feed(posts: list[dict]) -> str:
    """RSS 2.0 of the published posts, newest first.

    What a newsletter tool, a reader app or a person's own script can follow;
    no service in between, so nothing here can start charging for it.
    """
    rss = ET.Element("rss", version="2.0")
    channel = ET.SubElement(rss, "channel")
    for tag, text in (("title", "gummietech"), ("link", SITE_URL),
                      ("description", "Science, technology and engineering "
                       "— every @gummietech carousel, with its sources."),
                      ("language", "en")):
        ET.SubElement(channel, tag).text = text
    for post in posts:
        item = ET.SubElement(channel, "item")
        url = f"{SITE_URL}{post['slug']}/"
        ET.SubElement(item, "title").text = typeset(post["hook"])
        ET.SubElement(item, "link").text = url
        ET.SubElement(item, "guid", isPermaLink="true").text = url
        when = datetime.combine(post["published"], datetime.min.time(),
                                tzinfo=timezone.utc)
        ET.SubElement(item, "pubDate").text = format_datetime(when)
        ET.SubElement(item, "description").text = typeset(summary(post))
    return ('<?xml version="1.0" encoding="utf-8"?>\n'
            + ET.tostring(rss, encoding="unicode") + "\n")


def newsletter(posts: list[dict], today: date,
               days: int = NEWSLETTER_DAYS) -> str:
    """The posts published in the last `days`, as a page to copy into the
    newsletter. Every word is the posts' own, so nothing new needs checking;
    each links to its archive page, which links the sources.

    HTML, not markdown: Substack's editor pastes markdown as literal `##` and
    `**` (2026-10-12). Opened in a browser and copied, a page arrives as
    formatted text — headings, bold and links intact. The title line is
    the issue's title, and stays out of the body.
    """
    since = today - timedelta(days=days)
    recent = [p for p in reversed(posts) if since < p["published"] <= today]
    title = f"gummietech — the week to {human_date(today)}"
    body: list[str] = []
    for post in recent:
        # Slide 1 as the archive already serves it (covers()), so the email
        # shows the post people scrolled past on Instagram. Absolute URL:
        # Substack copies a pasted image from where it lives.
        page = f"{SITE_URL}{post['slug']}/"
        body.append(f'<p><a href="{page}"><img src="{page}cover.png" '
                    f'alt="{escape(post.get("alt_text") or post["hook"])}" '
                    'width="540"></a></p>')
        body.append(f"<h2>{escape(typeset(post['hook']))}</h2>")
        for section in post["body"]:
            if not section["pieces"]:
                continue
            # One paragraph a piece, as the archive page has it: joined, a
            # Signal's launches ran together into one sentence (2026-10-12).
            first, *rest = [escape(typeset(en)) for en, _ in section["pieces"]]
            body.append(f"<p><strong>{escape(section['en'])}.</strong> "
                        f"{first}</p>")
            body.extend(f"<p>{text}</p>" for text in rest)
        credits = "; ".join(s["attribution"] for s in post["sources"])
        body.append(f'<p>Source: {escape(credits)} — <a href="{page}">'
                    "sources and full post</a></p>")
    if not body:
        body.append(f"<p>Nothing published between {since} and {today}.</p>")
    return ("<!doctype html><meta charset=utf-8>"
            f"<title>{escape(title)}</title>"
            "<style>body{font:17px/1.55 Georgia,serif;max-width:640px;"
            "margin:40px auto;padding:0 16px}"
            ".title{font:600 13px/1.4 system-ui;color:#666;"
            "border-bottom:1px solid #ddd;padding-bottom:16px}</style>"
            f'<p class="title">Title for the issue — paste it into the '
            f"title field, then copy from the next line down:<br>"
            f"<b>{escape(title)}</b></p>\n" + "\n".join(body) + "\n")


def months(posts: list[dict]) -> list[dict]:
    """One entry per month with a published post, newest first."""
    found: dict[str, list[dict]] = {}
    for post in posts:
        found.setdefault(f"{post['published']:%Y-%m}", []).append(post)
    return [{"key": key,
             "label": f"{date.fromisoformat(key + '-01'):%B %Y}",
             "label_es": (f"{MONTHS_ES[int(key[5:]) - 1]} de {key[:4]}"),
             "pdf": f"gummietech-{key}.pdf",
             "posts": list(reversed(items))}
            for key, items in sorted(found.items(), reverse=True)]


def month_pdfs(found: list[dict], outdir: Path) -> None:
    """Print each month's page to its PDF, through the slides' browser.

    Same degradation as covers(): no browser is not a failed build. The page
    loses its link to the PDF instead of linking to one that is not there.
    """
    for month in found:
        page_dir = outdir / month["key"]
        try:
            from playwright.sync_api import sync_playwright
            with sync_playwright() as p:
                browser = p.chromium.launch()
                try:
                    page = browser.new_page()
                    page.goto((page_dir / "index.html").as_uri(),
                              wait_until="load")
                    page.emulate_media(media="print")
                    page.pdf(path=str(page_dir / month["pdf"]), format="A4",
                             print_background=True,
                             margin={"top": "16mm", "bottom": "16mm",
                                     "left": "14mm", "right": "14mm"})
                finally:
                    browser.close()
            month["has_pdf"] = True
        except Exception as exc:              # noqa: BLE001 — see docstring
            print(f"  warning: no monthly PDFs ({str(exc).splitlines()[0]}). "
                  "The month pages are built without the download.")
            return
    print(f"  wrote {len(found)} monthly PDF{'s' * (len(found) != 1)}")


def build(posts: list[dict], outdir: Path) -> None:
    env = Environment(
        loader=FileSystemLoader(TEMPLATE_DIR),
        autoescape=select_autoescape(["html"]),
    )
    env.globals["t"] = t
    env.globals["site_url"] = SITE_URL
    env.globals["beacon"] = os.environ.get(BEACON_ENV, "").strip()
    env.globals["feed"] = FEED

    # The toggle is only offered where there is something to toggle to.
    # A button that swaps the furniture around unchanged English prose
    # advertises a Spanish edition the archive does not have.
    translated = [p for p in posts if p["es"]]

    # `base` is the path back to the site root: post pages live one
    # directory down. Relative, not root-absolute, because Pages serves
    # this under /gummietechContent/ while a local preview is opened at file://.
    by_month = months(posts)
    (outdir / "index.html").write_text(
        env.get_template("index.html").render(
            posts=posts, months=by_month, base="",
            translated=bool(translated))
    )
    print(f"  wrote index.html ({len(posts)} post{'s' * (len(posts) != 1)})")

    # The one page that is not a post. §6b keeps every page a pure function
    # of the drafting JSON so that publishing costs no prose; this one costs
    # it once, in the template, and does not grow with posts/. It is here
    # because the archive is the only link Instagram makes clickable, so it
    # is the only place a reader can reach anything but the paper.
    about = outdir / "about"
    about.mkdir()
    (about / "index.html").write_text(
        env.get_template("about.html").render(
            base="../", translated=bool(translated))
    )
    print("  wrote about/index.html")

    for post in posts:
        (outdir / post["slug"]).mkdir()
    # Before the pages, which only point at an image that exists.
    covers(posts, outdir)

    post_template = env.get_template("post.html")
    for post in posts:
        page = outdir / post["slug"]
        (page / "index.html").write_text(
            post_template.render(post=post, base="../",
                                 translated=bool(post["es"]))
        )
        print(f"  wrote {post['slug']}/index.html")

    # Self-hosted for the same reason drop.html avoids the CDN: the look
    # should not depend on a third party staying up.
    shutil.copytree(FONTS_DIR, outdir / "fonts")
    print("  wrote fonts/")

    (outdir / FEED).write_text(feed(posts))
    print(f"  wrote {FEED}")

    # Twice: once to have a page to print, then again knowing whether the
    # PDF exists, so the page never links to a download that failed.
    month_template = env.get_template("month.html")

    def write_months() -> None:
        for month in by_month:
            translated_month = any(p["es"] for p in month["posts"])
            (outdir / month["key"]).mkdir(exist_ok=True)
            (outdir / month["key"] / "index.html").write_text(
                month_template.render(month=month, base="../",
                                      translated=translated_month))
    write_months()
    month_pdfs(by_month, outdir)
    write_months()
    print(f"  wrote {len(by_month)} month page{'s' * (len(by_month) != 1)}")
    print(f"  {len(translated)} of {len(posts)} page"
          f"{'s' * (len(posts) != 1)} carry Spanish")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--outdir", default=None, help="where to build the site")
    ap.add_argument("--newsletter", action="store_true",
                    help=f"write the last {NEWSLETTER_DAYS} days as a page to "
                         "copy into the newsletter, and build nothing")
    args = ap.parse_args()

    if args.newsletter:
        # The skip notes would bury the one line that matters.
        with contextlib.redirect_stdout(sys.stderr):
            posts, _ = load_posts()
        today = date.today()
        page = REPO_ROOT / "output" / f"newsletter-{today}.html"
        page.parent.mkdir(exist_ok=True)
        page.write_text(newsletter(posts, today))
        print(f"Wrote {page.relative_to(REPO_ROOT)}. Open it in a browser, "
              "select from the first headline down, copy, and paste into a "
              "new Substack post; the title is at the top.")
        return 0

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
