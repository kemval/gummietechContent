"""
redraft.yml's guard — the only thing between a phone tap and a push to master.

Like resolve-post, it is shell inside YAML and nothing else runs it, so the
step is read out of the workflow rather than copied: a copy here would pass
while the one that ships drifted. It runs in a throwaway git repository
holding exactly the change redraft.yml makes.
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest
import yaml

WORKFLOW = (Path(__file__).resolve().parent.parent
            / ".github" / "workflows" / "redraft.yml")
STEP = "Check it changed those posts and nothing else"


@pytest.fixture(scope="module")
def guard() -> str:
    steps = yaml.safe_load(WORKFLOW.read_text())["jobs"]["redraft"]["steps"]
    return next(s["run"] for s in steps if s.get("name") == STEP)


def git(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path, guard):
    """A repo whose last commit holds the waiting draft, and a runner for the
    guard over whatever the test changes next."""
    (tmp_path / "posts").mkdir()
    old = "posts/2026-09-30-old.json"
    (tmp_path / old).write_text(json.dumps({"hook": "old"}))
    git(tmp_path, "init", "-q")
    git(tmp_path, "-c", "user.email=t@t", "-c", "user.name=t",
        "add", "-A")
    git(tmp_path, "-c", "user.email=t@t", "-c", "user.name=t",
        "commit", "-qm", "draft")

    def write(path: str, **record) -> None:
        (tmp_path / path).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / path).write_text(json.dumps(record))

    def reject() -> str:
        moved = "posts/rejected/2026-09-30-old.json"
        write(moved, hook="old", rejected={"at": "2026-09-30"})
        (tmp_path / old).unlink()
        return moved

    def run(new: str) -> subprocess.CompletedProcess:
        return subprocess.run(["bash", "-e", "-c", guard], cwd=tmp_path,
                              text=True, capture_output=True,
                              env={**os.environ, "OLD": old, "NEW": new})

    return write, reject, run


def test_a_rejected_drop_and_its_replacement_pass(repo):
    write, reject, run = repo
    reject()
    write("posts/2026-09-30-new.json", hook="new")
    assert run("posts/2026-09-30-new.json").returncode == 0


def test_a_signal_redrafted_the_same_day_lands_on_its_own_name(repo, guard):
    """A Signal is named by its week, so the new one is written where the
    rejected one was, and git sees a modification, not a delete and an add.
    Without sort -u the guard counted the path twice and refused."""
    write, reject, run = repo
    reject()
    write("posts/2026-09-30-old.json", hook="new")
    assert run("posts/2026-09-30-old.json").returncode == 0


def test_anything_else_changed_is_refused(repo):
    write, reject, run = repo
    reject()
    write("posts/2026-09-30-new.json", hook="new")
    write("posts/2026-09-12-live.json", hook="touched")
    done = run("posts/2026-09-30-new.json")
    assert done.returncode != 0
    assert "Nothing has been committed" in done.stderr


def test_a_dated_draft_is_refused(repo):
    """Nothing but a tap in the chat may date a post."""
    write, reject, run = repo
    reject()
    write("posts/2026-09-30-new.json", hook="new", published_at="2026-09-30")
    assert run("posts/2026-09-30-new.json").returncode != 0
