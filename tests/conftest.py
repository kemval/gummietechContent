"""
Shared fixtures.

`src/` is not a package and its modules import each other by bare name
(`import llm`, `from render import ...`), which is what lets them run as
scripts. Tests put it on the path for the same reason, rather than adding
__init__.py and rewriting every import to suit the tests.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))


@pytest.fixture
def posts_dir(tmp_path):
    """An empty posts/ a test can fill, with a writer that takes a record.

    Returned as (directory, write) so a test reads as the situation it is
    about rather than as JSON plumbing.
    """
    directory = tmp_path / "posts"
    directory.mkdir()

    def write(name: str, **record) -> Path:
        path = directory / name
        path.write_text(json.dumps(record, indent=2) + "\n")
        return path

    return directory, write
