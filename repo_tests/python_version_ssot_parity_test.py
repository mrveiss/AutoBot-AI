# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The interpreter version has ONE source of truth: `.python-version` (#13842).

Before this, the minor version was declared independently in 8+ places with no
check tying them together. `startup_validator.py` drifted to `(3, 12)` for four
minor versions while everything else said 3.14 (PR #13750) and nothing noticed
because nothing compared them. This guard is that comparison, for every
declaration that still cannot literally *include* `.python-version`:

* `pyproject.toml`'s `[tool.mypy] python_version` -- TOML cannot import a file.
* `docker/backend/Dockerfile` and `docker/slm/Dockerfile` -- both now take an
  `ARG PYTHON_VERSION` (#13842 made backend match slm's existing pattern), and
  a `FROM`/`ARG` default is a Docker syntax literal, not a file read.
* `.github/actions/setup-python-ci/action.yml`'s self-hosted branch, which
  needs the version as a plain string (`python${PY_VERSION}` binary name), not
  a `setup-python`-only `python-version-file:` input.
* `autobot-backend/startup_validator.py`'s `_minimum_python_version` -- this
  one CAN read the file directly (it runs on the deployed host, which gets the
  same checkout), so it is asserted by calling the function, not by regex.

Sites that read `.python-version` directly at run/build time --
`.github/actions/setup-python-suite/action.yml`,
`.github/actions/setup-python-ci/action.yml`'s github-hosted branch (both via
`python-version-file:`), the 14 workflows that call either composite action or
`actions/setup-python` with `python-version-file:` directly, and
`roles/python_interpreter`'s ansible `lookup('file', ...)` -- do not need a
parity check here: they cannot drift, because they never restate the value.
`test_the_workflow_files_carry_no_stray_literal` below is the check that
holds THAT structural property, i.e. that nobody reintroduced a restated
`python-version: 'X.Y'` literal in a workflow.

`[tool.black] target-version` is deliberately excluded -- it controls the
syntax black emits, not the interpreter it runs under, and stays below the
interpreter floor for the NPU worker's older stack (see the comment on that
key in pyproject.toml, #13748, #10877). Nothing here touches it.
"""

from __future__ import annotations

import os
import re
import subprocess  # nosec B404 -- fixed argv, no shell, isolates an import from this process's sys.modules
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
_PYTHON_VERSION_FILE = _REPO_ROOT / ".python-version"
_PYPROJECT = _REPO_ROOT / "pyproject.toml"
_BACKEND_DOCKERFILE = _REPO_ROOT / "docker" / "backend" / "Dockerfile"
_SLM_DOCKERFILE = _REPO_ROOT / "docker" / "slm" / "Dockerfile"
_SETUP_PYTHON_CI = _REPO_ROOT / ".github" / "actions" / "setup-python-ci" / "action.yml"

_ARG_PYTHON_VERSION_RE = re.compile(r"^ARG PYTHON_VERSION=(\S+)\s*$", re.M)


def _ssot_version() -> str:
    """`.python-version`'s content, e.g. "3.14" -- the single literal."""
    version = _PYTHON_VERSION_FILE.read_text(encoding="utf-8").strip()
    assert version, f"{_PYTHON_VERSION_FILE} is empty — this guard is pinned to the wrong file"
    return version


def test_the_ssot_file_parses_to_a_version():
    """A guard over nothing is worth nothing."""
    version = _ssot_version()
    assert re.fullmatch(r"\d+\.\d+", version), f".python-version contains {version!r}, not 'major.minor'"


def test_mypy_python_version_matches_the_ssot():
    """TOML cannot include a file, so this is checked, not derived."""
    if sys.version_info < (3, 11):
        pytest.skip("tomllib is 3.11+; no tomli fallback is declared in this repo")
    import tomllib

    data = tomllib.loads(_PYPROJECT.read_text(encoding="utf-8"))
    mypy_version = data["tool"]["mypy"]["python_version"]
    assert mypy_version == _ssot_version(), (
        f"pyproject.toml [tool.mypy] python_version={mypy_version!r} disagrees with "
        f".python-version={_ssot_version()!r} (#13842)"
    )


@pytest.mark.parametrize("dockerfile", [_BACKEND_DOCKERFILE, _SLM_DOCKERFILE])
def test_dockerfile_arg_default_matches_the_ssot(dockerfile: Path):
    """Both Dockerfiles express the floor as `ARG PYTHON_VERSION=X.Y` (#13842
    made docker/backend match docker/slm's pre-existing pattern) -- a Docker
    build ARG default cannot itself read `.python-version`."""
    text = dockerfile.read_text(encoding="utf-8")
    match = _ARG_PYTHON_VERSION_RE.search(text)
    assert match, f"{dockerfile}: no `ARG PYTHON_VERSION=X.Y` line found — this guard is pinned to the wrong shape"
    assert match.group(1) == _ssot_version(), (
        f"{dockerfile} declares ARG PYTHON_VERSION={match.group(1)!r} while .python-version "
        f"declares {_ssot_version()!r} (#13842)"
    )


def test_setup_python_ci_self_hosted_default_has_no_stray_literal():
    """The composite action's `python-version` input default must stay empty
    (#13842) -- a caller who leaves it unset gets the SSOT via the action's own
    "Resolve Python version" step, not a hardcoded fallback restated here."""
    text = _SETUP_PYTHON_CI.read_text(encoding="utf-8")
    match = re.search(r"^\s*default:\s*'([^']*)'\s*$", text, re.M)
    assert match, f"{_SETUP_PYTHON_CI}: no `default:` line found for the first input — wrong shape"
    assert match.group(1) == "", (
        f"{_SETUP_PYTHON_CI}'s python-version input default is {match.group(1)!r}, not empty — "
        "a non-empty default restates the floor instead of deriving it from .python-version (#13842)"
    )


def test_startup_validator_reads_the_ssot():
    """Calls the real function rather than regexing the source -- this is the
    floor #13842 says a reader trusts because it is the only one a running
    process enforces, and it is the one that silently drifted before (PR #13750).

    Run in a SUBPROCESS, not imported in-process: `startup_validator.py` pulls
    in `config.manager` / `constants.path_constants`, which stub/mock modules
    other test files' own conftests rely on staying unstubbed -- importing it
    here directly trips the repo's sys-modules-leak guard the moment this file
    runs in the same session as one of those. A subprocess's sys.modules dies
    with the subprocess, so there is nothing to leak.
    """
    env = dict(os.environ, PYTHONPATH=f"{_REPO_ROOT}:{_REPO_ROOT / 'autobot-backend'}")
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from startup_validator import _minimum_python_version; "
            "print('%d.%d' % _minimum_python_version())",
        ],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, f"startup_validator import/call failed: {result.stderr}"
    reported = result.stdout.strip()
    assert reported == _ssot_version(), (
        f"startup_validator._minimum_python_version() returned {reported}, "
        f".python-version declares {_ssot_version()!r} (#13842)"
    )


_WORKFLOW_DIR = _REPO_ROOT / ".github" / "workflows"
_ACTIONS_DIR = _REPO_ROOT / ".github" / "actions"
_STRAY_LITERAL_RE = re.compile(r"^\s*python-version:\s*['\"](\d+\.\d+)['\"]\s*$", re.M)


def _workflow_and_action_files() -> list[Path]:
    return sorted(_WORKFLOW_DIR.glob("*.yml")) + sorted(_ACTIONS_DIR.glob("*/action.yml"))


def test_the_scan_reaches_workflow_and_action_files():
    """An empty file list would make the next test vacuous."""
    assert len(_workflow_and_action_files()) >= 10, "the workflow/action glob stopped matching anything"


def test_the_workflow_files_carry_no_stray_literal():
    """No workflow or composite action may restate `python-version: 'X.Y'`.

    #13842 moved every one of these onto `python-version-file: '.python-version'`
    (directly, or via the two composite actions, both of which derive their own
    default from the file). A reintroduced literal -- even one that happens to
    still say 3.14 today -- is exactly the shape that drifted silently before;
    this fails on the literal existing at all, not on its value.
    """
    offenders: list[str] = []
    for path in _workflow_and_action_files():
        text = path.read_text(encoding="utf-8")
        for match in _STRAY_LITERAL_RE.finditer(text):
            offenders.append(f"{path.relative_to(_REPO_ROOT)}: python-version: '{match.group(1)}'")

    assert not offenders, "restated python-version literal(s) found (#13842):\n" + "\n".join(offenders)
