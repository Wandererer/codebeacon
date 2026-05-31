"""Regression: CLAUDE.md / AGENTS.md must not leak absolute machine paths.

The "High-Impact Files" section is rendered into the committed CLAUDE.md, so
an absolute path like ``/Users/alice/repo/src/a.py`` would bake one developer's
home directory into the repo and churn diffs. Paths are stored relative to the
project root instead. Mirrors graphify #999.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from codebeacon.contextmap.generator import _relativize_to


@pytest.mark.parametrize("path,root,want", [
    (os.sep + os.path.join("repo", "src", "a.py"), os.sep + "repo", "src/a.py"),
    ("src/a.py", os.sep + "repo", "src/a.py"),                 # already relative
    (os.sep + os.path.join("elsewhere", "x.py"), os.sep + "repo",
     os.sep + os.path.join("elsewhere", "x.py")),             # outside root → unchanged
    ("", os.sep + "repo", ""),                                # empty → unchanged
])
def test_relativize_to(path, root, want):
    assert _relativize_to(path, Path(root)) == want


def test_relativized_path_uses_forward_slashes():
    abs_path = os.sep + os.path.join("repo", "pkg", "mod", "x.py")
    rel = _relativize_to(abs_path, Path(os.sep + "repo"))
    assert rel == "pkg/mod/x.py"
    assert "\\" not in rel  # POSIX separators even on Windows
