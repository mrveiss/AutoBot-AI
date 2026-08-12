# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Tests for the hook exec-bit guard (#14171).

The guard's whole job is to fail on a state that looks fine locally, so the
tests drive its real decision function against synthetic mode maps rather than
mutating the repository's own index.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_MODULE_PATH = Path(__file__).with_name("check_hook_exec_bits.py")


def _load():
    spec = importlib.util.spec_from_file_location("check_hook_exec_bits", _MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def guard():
    return _load()


def _config(tmp_path: Path, body: str) -> Path:
    path = tmp_path / ".pre-commit-config.yaml"
    path.write_text(body, encoding="utf-8")
    return path


def test_a_bare_path_entry_tracked_100644_fails(guard, tmp_path, monkeypatch):
    """The defect: an entry pre-commit executes directly, without the exec bit."""
    config = _config(
        tmp_path,
        "repos:\n  - repo: local\n    hooks:\n      - id: my-hook\n        entry: tools/lint/my_hook.py\n",
    )
    monkeypatch.setattr(guard, "_CONFIG_PATHS", (config,))

    blocking, known = guard._split_findings({"tools/lint/my_hook.py": "100644"})

    assert not known
    assert len(blocking) == 1
    assert "my-hook" in blocking[0]
    assert "100644" in blocking[0]


def test_the_same_entry_tracked_100755_passes(guard, tmp_path, monkeypatch):
    config = _config(
        tmp_path,
        "repos:\n  - repo: local\n    hooks:\n      - id: my-hook\n        entry: tools/lint/my_hook.py\n",
    )
    monkeypatch.setattr(guard, "_CONFIG_PATHS", (config,))

    blocking, known = guard._split_findings({"tools/lint/my_hook.py": "100755"})

    assert not blocking and not known


@pytest.mark.parametrize(
    "entry",
    [
        "bash autobot-infrastructure/shared/tests/some_test.sh",
        "python -m black",
        "npx eslint",
        "poetry run mypy",
    ],
)
def test_an_interpreter_prefixed_entry_is_not_flagged(guard, tmp_path, monkeypatch, entry):
    """Only the first token is executed; a script passed as an argument is not.

    Without this the guard would demand the exec bit on every file any hook
    merely mentions, which is how a guard becomes noise and then gets disabled.
    """
    config = _config(
        tmp_path,
        f"repos:\n  - repo: local\n    hooks:\n      - id: my-hook\n        entry: {entry}\n",
    )
    monkeypatch.setattr(guard, "_CONFIG_PATHS", (config,))

    # Only the *arguments* are tracked repo paths. The first token is an
    # interpreter on PATH and is deliberately absent from the mode map --
    # a tracked file literally named `bash` is not a shape git ever emits,
    # and feeding one would have tested a world that does not exist.
    modes = {token: "100644" for token in entry.split()[1:]}
    blocking, known = guard._split_findings(modes)

    assert not blocking and not known


def test_a_known_dormant_entry_is_reported_but_not_blocking(guard, tmp_path, monkeypatch):
    """The baseline records; it must not hide.

    A dormant hook stays visible in every run under #14181 rather than being
    filtered out — the difference between a tracked backlog and a silent one.
    """
    dormant = next(iter(guard._KNOWN_DORMANT))
    config = _config(
        tmp_path,
        f"repos:\n  - repo: local\n    hooks:\n      - id: dormant\n        entry: {dormant}\n",
    )
    monkeypatch.setattr(guard, "_CONFIG_PATHS", (config,))

    blocking, known = guard._split_findings({dormant: "100644"})

    assert not blocking, "a baselined hook must not fail the build"
    assert len(known) == 1 and dormant in known[0], "a baselined hook must still be reported"


def test_a_missing_config_file_is_not_a_pass(guard, tmp_path, monkeypatch):
    """A second config that does not exist contributes nothing and errors nothing.

    Both config copies are checked; only one exists in some trees. This pins
    that the absent one is skipped rather than crashing the guard, which would
    take the present one's findings down with it.
    """
    present = _config(
        tmp_path,
        "repos:\n  - repo: local\n    hooks:\n      - id: my-hook\n        entry: tools/lint/my_hook.py\n",
    )
    monkeypatch.setattr(guard, "_CONFIG_PATHS", (present, tmp_path / "nope" / ".pre-commit-config.yaml"))

    blocking, _ = guard._split_findings({"tools/lint/my_hook.py": "100644"})

    assert len(blocking) == 1


def test_an_empty_git_listing_is_fatal_not_clean(guard, monkeypatch):
    """`git ls-files` returning nothing means the scope was never scanned.

    An empty mode map makes every lookup miss, and every miss is treated as "a
    program name on PATH" — so the guard would report a clean bill of health on
    a tree it never looked at. That is the exact failure this hook family
    exists to remove, so it exits instead.
    """

    class _Result:
        returncode = 0
        stdout = ""
        stderr = ""

    monkeypatch.setattr(guard.subprocess, "run", lambda *a, **k: _Result())

    with pytest.raises(SystemExit) as excinfo:
        guard._tracked_modes(Path('.'))

    assert "refusing to report clean" in str(excinfo.value)


def test_a_failed_git_listing_is_fatal(guard, monkeypatch):
    class _Result:
        returncode = 128
        stdout = ""
        stderr = "fatal: not a git repository"

    monkeypatch.setattr(guard.subprocess, "run", lambda *a, **k: _Result())

    with pytest.raises(SystemExit) as excinfo:
        guard._tracked_modes(Path('.'))

    assert "git ls-files failed" in str(excinfo.value)


def test_the_repository_itself_passes_the_guard(guard):
    """End-to-end against the real config and the real index.

    The unit tests above all use synthetic inputs, which cannot notice a config
    key being renamed or a real entry drifting. This one runs the guard exactly
    as CI does.
    """
    assert guard.main([]) == 0


def test_running_from_a_subdirectory_does_not_report_clean(guard, tmp_path):
    """A wrong CWD must not turn 16 violations into a clean bill of health.

    Review finding on #14182. `git ls-files` run from a subdirectory returns
    paths relative to *that* directory, so the mode map is non-empty -- the
    empty-map guard never fires -- and every config target misses its lookup.
    Every miss is read as "a program name on PATH", so the guard printed
    success over every real violation. Not reachable through `pre-commit`
    itself, which chdirs to the repo root first, but reachable through any
    direct invocation, including the end-to-end test below.
    """
    import os

    root = guard._repo_root()
    subdir = root / "tools" / "lint"
    if not subdir.is_dir():  # pragma: no cover - layout changed
        pytest.skip("tools/lint no longer exists")

    cwd = os.getcwd()
    try:
        os.chdir(subdir)
        modes = guard._tracked_modes(guard._repo_root())
        blocking, known = guard._split_findings(modes, guard._repo_root())
    finally:
        os.chdir(cwd)

    # The repository's own baseline is non-empty, so a correct run from a
    # subdirectory still classifies it. A CWD-relative run loses all of it and
    # reports nothing at all -- which is indistinguishable from "clean".
    assert known, "running from a subdirectory lost the dormant baseline entirely"
    assert not blocking, "the repository itself should have no blocking findings"


def test_the_dormant_baseline_has_no_stale_entries(guard):
    """Every baselined path must still be some hook's entry.

    Without this the "only ever shrinks" rule in the source is a comment
    rather than a property: a rename that updates the config but not the
    literal leaves permanently dead weight in the list, and nothing notices.
    """
    root = guard._repo_root()
    targets = {
        entry.split()[0]
        for config_path in guard._CONFIG_PATHS
        for _, entry in guard._local_hook_entries(root / config_path)
    }
    stale = guard._KNOWN_DORMANT - targets
    assert not stale, f"_KNOWN_DORMANT names paths no hook references any more: {sorted(stale)}"


def test_a_slashless_entry_is_left_to_pre_commits_path_search(guard, tmp_path, monkeypatch):
    """`entry: myhook.py` is resolved through $PATH, not as a repo file.

    pre-commit only treats `cmd[0]` as a repo file when it contains a path
    separator (`parse_shebang.normexe`). `git ls-files` lists top-level files
    unprefixed, so without the separator test the guard would demand the exec
    bit on a name real pre-commit never inspects the mode of -- a false
    positive that blocks an otherwise-fine PR.
    """
    config = _config(
        tmp_path,
        "repos:\n  - repo: local\n    hooks:\n      - id: my-hook\n        entry: myhook.py\n",
    )
    monkeypatch.setattr(guard, "_CONFIG_PATHS", (config,))

    blocking, known = guard._split_findings({"myhook.py": "100644"})

    assert not blocking and not known
