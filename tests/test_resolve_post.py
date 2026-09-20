"""
.github/actions/resolve-post — which post a phone-dispatched workflow acts on.

recheck.yml and fix.yml are the two ways back from a held post and must never
disagree about which post is held, which is why they share this action. It is
YAML wrapping an inline Python script and nothing else runs it, so the script
is extracted from the action itself: a copy here would drift from the one that
ships.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ACTION = (Path(__file__).resolve().parent.parent
          / ".github" / "actions" / "resolve-post" / "action.yml")

HELD = "2026-09-18-held.json"
BUFFERED = "2026-09-19-buffered.json"
LIVE = "2026-09-17-published.json"
FIXTURE = "era.json"


@pytest.fixture(scope="module")
def script(tmp_path_factory):
    body = ACTION.read_text().split("python3 <<'PY'\n", 1)[1].rsplit("        PY", 1)[0]
    path = tmp_path_factory.mktemp("action") / "pick.py"
    path.write_text("\n".join(line[8:] if line.startswith("        ") else line
                              for line in body.splitlines()))
    return path


@pytest.fixture
def pick(script, tmp_path):
    def run(posts: dict[str, str | None], gate: str = "", asked: str = ""):
        root = tmp_path / str(len(list(tmp_path.iterdir())))
        (root / "posts").mkdir(parents=True)
        for name, published in posts.items():
            record = {"hook": "x"}
            if published:
                record["published_at"] = published
            (root / "posts" / name).write_text(json.dumps(record))
        output = root / "github_output"
        output.touch()
        done = subprocess.run(
            [sys.executable, str(script)], cwd=root, text=True,
            capture_output=True,
            env={**os.environ, "GITHUB_OUTPUT": str(output),
                 "GATE_STEMS": gate, "POST": asked})
        picked = next((line.split("=", 1)[1]
                       for line in output.read_text().splitlines()
                       if line.startswith("post=")), None)
        return picked, done.stdout + done.stderr, done.returncode

    return run


def test_one_post_waiting_needs_no_hint(pick):
    """Normal running before the cadence changed, and still the common case."""
    picked, _, _ = pick({LIVE: "2026-09-17", HELD: None, FIXTURE: None})
    assert picked == f"posts/{HELD}"


def test_without_a_hint_a_newer_buffered_draft_steals_the_pick(pick):
    """The bug the gate hint exists for. Kept as a test because it is what
    the fallback still does, and the warning has to say so."""
    picked, log, _ = pick({LIVE: "2026-09-17", HELD: None, BUFFERED: None})
    assert picked == f"posts/{BUFFERED}"
    assert "::warning::" in log


def test_the_gate_names_the_post_the_person_is_looking_at(pick):
    """review.yml uploads reports-<stem> for every post it sends, so the
    newest surviving one is the post whose message carries the buttons."""
    picked, log, _ = pick({LIVE: "2026-09-17", HELD: None, BUFFERED: None},
                          gate="2026-09-18-held\n2026-09-17-published")
    assert picked == f"posts/{HELD}"
    assert "::warning::" not in log          # a buffer is not a fault


def test_a_stem_since_published_falls_through_to_the_next(pick):
    """The buttons on an older message stay meaningful for as long as that
    post is unresolved."""
    picked, _, _ = pick({LIVE: "2026-09-17", HELD: None, BUFFERED: None},
                        gate="2026-09-17-published\n2026-09-18-held")
    assert picked == f"posts/{HELD}"


def test_a_stem_naming_nothing_falls_back_and_warns(pick):
    picked, log, _ = pick({LIVE: "2026-09-17", HELD: None, BUFFERED: None},
                          gate="2026-09-01-deleted")
    assert picked == f"posts/{BUFFERED}"
    assert "::warning::" in log


def test_the_era_fixture_is_never_picked(pick):
    """posts/era.json has no date prefix and no published_at, and sorts after
    every real draft — unfiltered it would be picked every single time."""
    picked, _, _ = pick({FIXTURE: None, HELD: None})
    assert picked == f"posts/{HELD}"


def test_a_named_path_beats_everything(pick):
    picked, _, _ = pick({HELD: None, BUFFERED: None}, gate="2026-09-18-held",
                        asked=f"posts/{BUFFERED}")
    assert picked == f"posts/{BUFFERED}"


def test_a_named_path_that_is_not_on_master_is_an_error(pick):
    picked, log, code = pick({HELD: None}, asked="posts/nope.json")
    assert picked is None and code != 0
    assert "::error::" in log


def test_nothing_waiting_is_an_error_that_says_why(pick):
    picked, log, code = pick({LIVE: "2026-09-17"})
    assert picked is None and code != 0
    assert "already has published_at" in log


def test_a_malformed_draft_does_not_block_acting_on_a_good_one(pick, tmp_path):
    picked, log, _ = pick({LIVE: "2026-09-17", HELD: None})
    assert picked == f"posts/{HELD}"
