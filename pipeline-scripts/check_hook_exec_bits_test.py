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
    # A synthetic entry, not one drawn from the live baseline. The baseline is
    # empty as of #15750 -- the backlog it tracked is finished -- and a test
    # that seeds itself from it fails the moment the guard succeeds, which
    # would make finishing the work look like a regression.
    dormant = "tools/lint/a_dormant_hook_for_this_test.py"
    monkeypatch.setattr(guard, "_KNOWN_DORMANT", frozenset({dormant}))
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

    # This used to assert against the repository's own dormant baseline. That
    # made the test's fixture the very backlog the guard exists to eliminate:
    # #15750 fixed the last live entry, the baseline emptied, and the assertion
    # failed -- not because the CWD behaviour regressed, but because there was
    # no longer a violation to classify. A guard whose test stops working when
    # the guard succeeds is a guard that punishes finishing the work.
    #
    # The real property is asserted below against a synthetic violation, so it
    # holds whether the repository has a backlog or not. All the run above can
    # honestly claim is that a wrong CWD produces no blocking findings either.
    assert not blocking, "the repository itself should have no blocking findings"


def test_a_cwd_relative_run_loses_a_violation_it_should_have_classified(guard, monkeypatch):
    """The CWD property, on a fixture that does not depend on the backlog.

    ``git ls-files`` run from a subdirectory returns paths relative to *that*
    directory, so a config target like ``tools/lint/x.py`` misses its lookup,
    is read as "a program name on PATH", and is skipped -- the guard prints
    success over a real violation. Anchoring at the repo root is what prevents
    it (#14182).

    Both halves are asserted: the anchored map classifies the violation, and a
    CWD-relative map loses it. Without the second, a ``_split_findings`` that
    classified everything would pass the first and still be broken.
    """
    root = guard._repo_root()
    target = next(
        (
            entry.split()[0]
            for config_path in guard._CONFIG_PATHS
            for _hook_id, entry in guard._local_hook_entries(root / config_path)
            if "/" in entry.split()[0]
        ),
        None,
    )
    assert target, "no local hook entry resolves to a repo path -- fixture is vacuous"

    monkeypatch.setattr(guard, "_KNOWN_DORMANT", frozenset({target}))

    anchored = {target: "100644"}  # the violation: tracked, not executable
    blocking, known = guard._split_findings(anchored, root)
    assert known == [d for d in known if target in d] and known, (
        f"an anchored run must classify {target} as dormant, got known={known!r}"
    )
    assert not blocking, f"{target} is baselined, so it must not block: {blocking!r}"

    # What a subdirectory run actually produces: the same file keyed by a path
    # relative to the subdirectory, so the repo-root-relative lookup misses.
    cwd_relative = {target.rsplit("/", 1)[-1]: "100644"}
    blocking, known = guard._split_findings(cwd_relative, root)
    assert not known and not blocking, (
        "a CWD-relative mode map should lose the violation entirely -- that is the "
        f"failure #14182 documents; got known={known!r} blocking={blocking!r}"
    )


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
    assert targets, "no local hook entries found -- this check would pass vacuously"

    stale = guard._KNOWN_DORMANT - targets
    assert not stale, f"_KNOWN_DORMANT names paths no hook references any more: {sorted(stale)}"


def test_the_staleness_check_would_catch_a_dead_entry(guard, monkeypatch):
    """Contrast case, and the reason it is needed right now.

    ``_KNOWN_DORMANT`` is empty as of #15750, so the check above subtracts an
    empty set and passes no matter what -- true, and vacuous. A reader seeing it
    green would reasonably conclude the baseline is being policed; it is not,
    because there is nothing left to police.

    This pins that the *check* still works, so refilling the baseline later
    restores a real guarantee rather than a green tick. It does not substitute
    for the missing shrink-side check -- that an entry is still an actual
    violation, not merely still some hook's entry -- which is #15762.
    """
    monkeypatch.setattr(guard, "_KNOWN_DORMANT", frozenset({"tools/lint/no_hook_references_this.py"}))

    root = guard._repo_root()
    targets = {
        entry.split()[0]
        for config_path in guard._CONFIG_PATHS
        for _, entry in guard._local_hook_entries(root / config_path)
    }
    assert guard._KNOWN_DORMANT - targets, "a dead baseline entry must be detected as stale"


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
