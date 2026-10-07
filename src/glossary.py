#!/usr/bin/env python3
"""
The Tuesday glossary term: what glossary.yml decides in code, around the one
step a model does.

docs §1 puts a Glossary term out every Tuesday. Since 2026-10-06 Claude
writes it in glossary.yml rather than a person at a laptop. A free-tier
model was ruled out because a definition is exactly where a model invents a
confident one, and a glossary exists to be saved. Everything that can be
decided without a model is decided here, before and after it writes:

    python src/glossary.py due            # exit 0 if this week still owes a term
    python src/glossary.py brief          # what the writer may pick from
    python src/glossary.py finish <draft> # refuse a bad term, or file it in posts/

The credit is never the model's. A term's example is a post this account
already published (render.example_post() refuses anything else), and its
source, DOI, authors and preprint flag are that post's, copied here. A
retyped credit is the one way a correct definition can still go out wrong.

Standard library and formats.py only: `due` runs in the gate job, before
anything is installed.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import date, timedelta
from pathlib import Path

from formats import FORMATS

REPO_ROOT = Path(__file__).resolve().parent.parent
POSTS_DIR = REPO_ROOT / "posts"
REJECTED_DIR = POSTS_DIR / "rejected"

# This week's glossary slot is filled by either; docs §1 has the Cheat Sheet
# replace the Tuesday term every sixth week.
GLOSSARY_TYPES = ("term", "sheet")

# The credit fields a term takes from its example post. The model's draft
# never supplies them; finish() overwrites whatever it wrote.
CREDIT = ("source_url", "doi", "attribution", "peer_reviewed")

# Post types that cannot be an example. A Signal has five sources and no one
# credit to inherit. A term or sheet as the example of a term is circular.
NOT_AN_EXAMPLE = ("signal", "term", "sheet")


def read(path: Path) -> dict | None:
    try:
        post = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        print(f"  skipped {path.name}: {exc}", file=sys.stderr)
        return None
    return post if isinstance(post, dict) else None


def posts(directory: Path) -> list[tuple[Path, dict]]:
    return [(path, post) for path in sorted(directory.glob("*.json"))
            if (post := read(path)) is not None]


def due(today: date, directory: Path = POSTS_DIR) -> list[Path]:
    """This week's term or sheet, if there is one. Empty means still owed.

    Asked by filename date from Monday, the same window watch.check_by_hand()
    uses, so the gate and the watcher agree about which week a post fills.
    """
    monday = today - timedelta(days=today.weekday())
    found = []
    for path, post in posts(directory):
        try:
            drafted = date.fromisoformat(path.name[:10])
        except ValueError:
            continue
        if monday <= drafted <= today and post.get("post_type") in GLOSSARY_TYPES:
            found.append(path)
    return found


def defined_terms(directory: Path = POSTS_DIR) -> list[str]:
    """Every term already written, including ones turned down at the gate.

    posts/rejected/ counts for the reason it does for draft.covered_papers():
    a term rejected once should not come back next Tuesday unchanged.
    """
    terms = []
    for folder in (directory, directory / "rejected"):
        for _, post in posts(folder):
            if post.get("post_type") == "term" and post.get("term"):
                terms.append(str(post["term"]).strip())
    return terms


def examples(directory: Path = POSTS_DIR) -> list[tuple[str, dict]]:
    """Published posts a new term may point to, newest first.

    A post already used as some term's example is left out, so the glossary
    walks across the archive instead of defining five words from one paper.
    """
    used = {str(post.get("example_post", "")).strip()
            for folder in (directory, directory / "rejected")
            for _, post in posts(folder) if post.get("post_type") == "term"}
    return [(path.stem, post) for path, post in reversed(posts(directory))
            if post.get("published_at")
            and post.get("post_type") not in NOT_AN_EXAMPLE
            and path.stem not in used]


def brief(directory: Path = POSTS_DIR) -> str:
    """The writer's menu: what it may define and what it must not repeat."""
    lines = ["Terms already defined (do not define these again):"]
    lines += [f"  - {t}" for t in defined_terms(directory)] or ["  (none)"]
    lines += ["", "Published posts you may use as example_post (stem, then hook):"]
    lines += [f"  - {stem}  —  {post.get('hook', '')}"
              for stem, post in examples(directory)] or ["  (none)"]
    return "\n".join(lines)


def problems(post: dict, directory: Path = POSTS_DIR) -> list[str]:
    """Why this draft is not a term glossary.yml may commit. Empty means fine."""
    found = []
    if post.get("post_type") != "term":
        found.append(f"post_type is {post.get('post_type')!r}, not 'term'")
    if post.get("published_at"):
        found.append("it carries published_at — only the human gate adds that")
    if "es" in post:
        found.append("it carries an es block — translate.py writes that")
    required = [*FORMATS["term"].record,
                *(s.field for s in FORMATS["term"].sections),
                "domain", "colorway", "caption"]
    missing = [f for f in required
               if f not in CREDIT and not str(post.get(f, "")).strip()]
    if missing:
        found.append(f"missing {', '.join(missing)}")
    term = str(post.get("term", "")).strip().lower()
    if term and term in {t.lower() for t in defined_terms(directory)}:
        found.append(f"{post['term']!r} is already defined")
    stem = str(post.get("example_post", "")).strip()
    if stem and stem not in {s for s, _ in examples(directory)}:
        found.append(f"example_post {stem!r} is not one of the published posts "
                     f"brief offered (unpublished, a Signal, or already used)")
    return found


def slug(term: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", term.lower()).strip("-")[:40] or "term"


def finish(draft: Path, today: date, directory: Path = POSTS_DIR) -> int:
    """Refuse a bad draft, or stamp its credit and file it in posts/.

    The writer drafts outside the repo and this names the file, so the model
    never chooses a path in posts/ and the commit has one file to add.
    """
    post = read(draft)
    if post is None:
        print(f"{draft} is not a JSON object. Nothing has been committed; read "
              f"the writer's output in this log.", file=sys.stderr)
        return 1
    if bad := problems(post, directory):
        print(f"Refusing {draft.name}:", file=sys.stderr)
        for line in bad:
            print(f"  - {line}", file=sys.stderr)
        print("Nothing has been committed. Dispatch glossary.yml with force to "
              "write another.", file=sys.stderr)
        return 1
    example = read(directory / f"{post['example_post']}.json") or {}
    for field in CREDIT:
        if field in example:
            post[field] = example[field]
        else:
            post.pop(field, None)
    path = directory / f"{today.isoformat()}-glossary-{slug(post['term'])}.json"
    path.write_text(json.dumps(post, indent=2, ensure_ascii=False) + "\n")
    print(f"{post['term']!r}, example {post['example_post']}, credit "
          f"{post.get('attribution')!r} copied from it.")
    print(f"Wrote {path.relative_to(REPO_ROOT)}")
    return 0


def main(argv: list[str]) -> int:
    command = argv[1] if len(argv) > 1 else ""
    if command == "due":
        found = due(date.today())
        if found:
            print(f"This week already has one: {', '.join(p.name for p in found)}")
            return 1
        print("This week has no term or sheet yet.")
        return 0
    if command == "brief":
        print(brief())
        return 0
    if command == "finish" and len(argv) == 3:
        return finish(Path(argv[2]), date.today())
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
