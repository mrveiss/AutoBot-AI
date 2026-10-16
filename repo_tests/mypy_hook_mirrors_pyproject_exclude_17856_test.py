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

_ROOT = repo_root()

#: One path per pyproject pattern, each of which that pattern excludes.
_SAMPLES = [
    "autobot_shared/ssot_config_test.py",
    "autobot-backend/tests/test_x.py",
    "autobot-backend/conftest.py",
    "autobot-backend/code_analysis/src/x.py",
]


def _mypy_hooks() -> list[dict]:
    config = yaml.safe_load((_ROOT / ".pre-commit-config.yaml").read_text(encoding="utf-8"))
    hooks = [h for repo in config["repos"] for h in repo.get("hooks", []) if h.get("id") == "mypy"]
    assert hooks, "no mypy hook found -- the guard would be vacuous"
    return hooks


def _pyproject_excludes() -> list[str]:
    data = tomllib.loads((_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    return data["tool"]["mypy"]["exclude"]


def test_every_sample_is_excluded_by_pyproject():
    """Contrast: the samples really are what the config means to skip."""
    for path in _SAMPLES:
        assert any(re.search(p, path) for p in _pyproject_excludes()), path


@pytest.mark.parametrize("hook", _mypy_hooks(), ids=lambda h: h.get("name", "mypy"))
def test_hook_skips_what_pyproject_skips(hook):
    files, exclude = re.compile(hook["files"]), re.compile(hook.get("exclude", r"(?!)"))
    for path in (p for p in _SAMPLES if files.search(p)):
        assert exclude.search(path), f"{hook['name']} would type-check {path}, which pyproject excludes"
