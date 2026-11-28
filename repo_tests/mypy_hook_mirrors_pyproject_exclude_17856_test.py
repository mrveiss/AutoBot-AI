# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The pre-commit mypy hooks skip what ``[tool.mypy].exclude`` skips (#17856).

mypy applies ``exclude`` only to files it discovers, never to files named on the
command line -- and pre-commit names every changed file. So touching
``autobot_shared/ssot_config_test.py`` ran strict mypy over a file the config
excludes and failed on 36 pre-existing ``_env_file`` call-arg errors. Each hook's
own ``exclude`` must therefore match every file the pyproject patterns exclude.
"""

from __future__ import annotations

import re
import tomllib

import pytest
import yaml
from repo_tests._paths import repo_root

from tools.lint._scan_helpers import tracked_paths

_ROOT = repo_root()


def _mypy_hooks() -> list[dict]:
    config = yaml.safe_load((_ROOT / ".pre-commit-config.yaml").read_text(encoding="utf-8"))
    hooks = [h for repo in config["repos"] for h in repo.get("hooks", []) if h.get("id") == "mypy"]
    assert hooks, "no mypy hook found -- the guard would be vacuous"
    return hooks


def _pyproject_excludes() -> list[str]:
    data = tomllib.loads((_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    return data["tool"]["mypy"]["exclude"]


def _excluded_tracked_files() -> dict[str, list[str]]:
    """Every tracked .py file each pyproject pattern excludes -- real files, not samples."""
    files = tracked_paths(_ROOT, "*.py")
    return {p: [f for f in files if re.search(p, f)] for p in _pyproject_excludes()}


def test_every_pyproject_pattern_excludes_a_real_file() -> None:
    """A pattern matching nothing tracked is checked against nothing -- say so instead."""
    for pattern, matched in _excluded_tracked_files().items():
        assert (
            matched
        ), f"{pattern!r} excludes no tracked .py file: retire it from pyproject or this guard checks nothing for it"


@pytest.mark.parametrize("hook", _mypy_hooks(), ids=lambda h: h.get("name", "mypy"))
def test_hook_skips_every_tracked_file_pyproject_skips(hook):
    files, exclude = re.compile(hook["files"]), re.compile(hook.get("exclude", r"(?!)"))
    for pattern, matched in _excluded_tracked_files().items():
        leaked = [f for f in matched if files.search(f) and not exclude.search(f)]
        assert not leaked, f"{hook['name']} would type-check {leaked[:3]}, which pyproject excludes via {pattern!r}"
