#!/usr/bin/env python3
"""
Put a different one of a draft's cover lines on its cover.

    python src/hook.py posts/2026-09-29-some-story.json 2

draft.py asks the model for three hooks — the finding plainly, the belief it
corrects, what it changes for the reader — and renders the first. The gate
message lists all three; hook.yml runs this, re-translates, commits, and sends
the post back through review.yml, because a new hook is a new claim and gets
its own fact-check.

It only ever copies a line the draft already holds. Nothing here writes
prose, and a post already on Instagram is refused: its cover is fixed there,
and changing the JSON would make the archive disagree with the account.

Standard library only; it runs before `translate.py` in the same job.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def swap(post: dict, choice: int) -> bool:
    """Set the hook to choice N (1-based). True if anything changed."""
    if post.get("published_at"):
        sys.exit("Refusing: this post is already published, so its cover is "
                 "fixed on Instagram. Changing the hook here would make the "
                 "archive disagree with the account.")
    hooks = post.get("hooks")
    if not isinstance(hooks, list) or len(hooks) < 2:
        sys.exit("This post has no alternative hooks to choose from — it was "
                 "drafted before draft.py wrote them, or by hand. Edit "
                 "`hook` in the JSON directly.")
    if not 1 <= choice <= len(hooks):
        sys.exit(f"There is no hook {choice}. This post has {len(hooks)}: "
                 f"pick 1 to {len(hooks)}.")
    wanted = hooks[choice - 1]
    if post.get("hook") == wanted:
        return False
    post["hook"] = wanted
    return True


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("post", type=Path, help="path to the post JSON")
    ap.add_argument("choice", type=int, help="which hook, counting from 1")
    args = ap.parse_args()

    try:
        post = json.loads(args.post.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        sys.exit(f"Cannot read {args.post}: {exc}")

    if not swap(post, args.choice):
        print(f"Already hook {args.choice}: {post['hook']!r} — nothing to do.")
        return 0

    # The shape draft.py and telegram.write_post() write, so the diff is the
    # one line that changed.
    args.post.write_text(json.dumps(post, indent=2, ensure_ascii=False) + "\n")
    print(f"Hook {args.choice} is now the cover: {post['hook']!r}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
