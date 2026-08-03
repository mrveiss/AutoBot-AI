# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Nested-session cover for the sys.modules leak guard (#13361, #13398).

The unit tests next door drive ``_LeakGuard`` directly.  That is fast and
precise, but it cannot see any of the three defects review found in the first
cut of this plugin, because every one of them lives in the *plumbing* rather
than the classifier:

* the warning class lied about its ``__module__``, so xdist's controller-side
  ``unserialize_warning_message`` blew up and took the whole session down with
  ``INTERNALERROR`` — the exact #13320 failure mode the guard exists to prevent;
* the collect hookwrapper was not ``tryfirst``, so a *hook-installed* stub —
  the very pattern #13361 tells implementers to adopt — was already in place
  when the baseline snapshot was taken, and the guard reported nothing;
* detection runs in xdist workers while reporting runs on the controller, so
  the exit-status gate was a no-op under ``-n``, which is the only shape CI uses.

The baseline ratchet (#13398) is covered here for exactly the same reason: its
three transitions are decided in ``pytest_sessionfinish`` from records that,
under xdist, were produced in another process entirely.

So these tests run real pytest sessions against a scratch repo.  Each builds a
two-package tree — ``pkg_a`` leaks, ``pkg_b`` is the innocent importer — and
asserts on the child session's own output.  Kept small deliberately: every test
here finishes in a couple of seconds.
"""

from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

_GUARD_MODULE = "repo_tests.sys_modules_leak_guard"
_REPO_ROOT = Path(__file__).resolve().parents[1]
_TIMEOUT = 120

_ROOT_CONFTEST = f"""
import sys
sys.path.insert(0, {str(_REPO_ROOT)!r})
pytest_plugins = ["{_GUARD_MODULE}"]
"""

_PYTEST_INI = """
[pytest]
python_files = test_*.py
addopts = -p no:randomly
"""

# The name the leaking conftest shadows. A real package of this name is written
# into the scratch repo so the guard's "does this shadow anything?" probe says
# yes — see _resolves_on_disk.
_VICTIM = "victim"

_BASELINE_FILE = "baseline.txt"


def _import_time_leak(victim: str) -> str:
    """A conftest that stubs *victim* at import time and never puts it back."""
    return f"import sys, types\nsys.modules[{victim!r}] = types.ModuleType({victim!r})\n"


def _restoring_hookwrapper(victim: str) -> str:
    """The correct pattern: install and restore *victim* in one try/finally."""
    return f"""
        import sys, types
        import pytest


        @pytest.hookimpl(hookwrapper=True)
        def pytest_make_collect_report(collector):
            prior = sys.modules.get({victim!r})
            sys.modules[{victim!r}] = types.ModuleType({victim!r})
            try:
                yield
            finally:
                if prior is None:
                    sys.modules.pop({victim!r}, None)
                else:
                    sys.modules[{victim!r}] = prior
    """


_IMPORT_TIME_LEAK = _import_time_leak(_VICTIM)

# The shape #13361 mandates: install and restore from a hookwrapper. This one
# is deliberately buggy — it installs but never restores — which is precisely
# the regression the guard has to be able to see.
_HOOK_INSTALLED_LEAK = f"""
import sys, types
import pytest


@pytest.hookimpl(hookwrapper=True)
def pytest_make_collect_report(collector):
    sys.modules[{_VICTIM!r}] = types.ModuleType({_VICTIM!r})
    yield
"""


# An ini that silences one PytestWarning subclass. The guard appends its own
# entry to "filterwarnings" and the last matching entry wins, so a guard filter
# written against a base class would override this and un-silence it.
_PYTEST_INI_WITH_IGNORE = """
[pytest]
python_files = test_*.py
addopts = -p no:randomly
filterwarnings =
    ignore::pytest.PytestUnknownMarkWarning
"""

_UNKNOWN_MARK_TEST = """
import pytest


@pytest.mark.a_marker_nobody_registered
def test_ok():
    assert True
"""


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(text).lstrip(), encoding="utf-8")


def _baseline(repo: Path, *owners: Path) -> None:
    """Write the scratch repo's allowlist of owners that are allowed to leak.

    Entries are absolute here only because the guard displays paths relative to
    the *real* repo root, which a ``tmp_path`` scratch repo is outside of; the
    checked-in baseline is a list of short repo-relative paths.
    """
    body = "".join(f"{owner.resolve()}\n" for owner in owners)
    (repo / _BASELINE_FILE).write_text(f"# scratch-repo baseline\n\n{body}", encoding="utf-8")


def _owners_on(stdout: str, marker: str) -> str:
    """The owner each *marker* line blames, joined — one assertion target.

    All three verdicts print inside one section, so "does pkg_a appear in the
    output" is not a question worth asking.  Nor is "is pkg_a on a ``LEAK:``
    line": that line also carries where the stub was first *seen*, which is a
    sibling package by definition, so a whole-line substring test passes for
    the innocent party too.  Every line puts the owner first, so the token
    after the marker is the subject and nothing else is.
    """
    subjects = (line.split(marker, 1)[1] for line in stdout.splitlines() if marker in line)
    return "\n".join(subject.strip().split(" ")[0] for subject in subjects)


@pytest.fixture
def scratch_repo(tmp_path: Path):
    """Build a minimal two-package repo and return a factory for its conftests."""
    _write(tmp_path / "pytest.ini", _PYTEST_INI)
    _write(tmp_path / "conftest.py", _ROOT_CONFTEST)
    _write(tmp_path / _VICTIM / "__init__.py", "REAL = True\n")
    for pkg in ("pkg_a", "pkg_b"):
        _write(tmp_path / pkg / f"test_{pkg}.py", "def test_ok():\n    assert True\n")

    def seed(leak_source: str, **extra_packages: str) -> Path:
        """Write ``pkg_a``'s conftest, plus one package per ``name=source``.

        Each extra package gets its own victim (``victim_pkg_c`` and friends):
        two conftests stubbing the same key would both be attributed to
        whichever installed it last, and the multi-owner tests need them told
        apart.
        """
        _write(tmp_path / "pkg_a" / "conftest.py", leak_source)
        for pkg, source in extra_packages.items():
            _write(tmp_path / pkg / f"test_{pkg}.py", "def test_ok():\n    assert True\n")
            _write(tmp_path / pkg / "conftest.py", source)
            _write(tmp_path / f"victim_{pkg}" / "__init__.py", "REAL = True\n")
        return tmp_path

    return seed


def _run_pytest(
    cwd: Path,
    *args: str,
    env_extra: dict | None = None,
    targets: tuple[str, ...] = ("pkg_a", "pkg_b"),
) -> subprocess.CompletedProcess:
    """Run a child pytest session in *cwd* and capture everything it printed.

    Plugin autoload is off so the child does not pay for coverage, anyio,
    asyncio and friends on every one of these sessions — it keeps each test
    comfortably inside the suite's per-test budget.  ``xdist`` is re-enabled
    explicitly by the callers that need ``-n``.

    The baseline is pointed at the scratch repo rather than left to default: a
    child reading the checked-in one would be judging ``tmp_path`` owners
    against ``autobot-backend`` entries.  The file is absent unless the test
    wrote one, and an absent baseline allows nothing.
    """
    import os

    env = dict(os.environ)
    env.pop("AUTOBOT_SYSMODULES_GUARD", None)
    env["AUTOBOT_SYSMODULES_BASELINE"] = str(cwd / _BASELINE_FILE)
    env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    env.update(env_extra or {})
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "--no-header",
            "-p",
            "no:cacheprovider",
            *targets,
            *args,
        ],
        cwd=str(cwd),
        env=env,
        capture_output=True,
        text=True,
        timeout=_TIMEOUT,
        check=False,
    )


# ---------------------------------------------------------------------------
# G2 — the guard must see the pattern it tells everyone to adopt
# ---------------------------------------------------------------------------


def test_reports_an_import_time_leak(scratch_repo):
    """The original shape: a conftest mutating sys.modules at import."""
    result = _run_pytest(scratch_repo(_IMPORT_TIME_LEAK))

    assert "LEAK:" in result.stdout, result.stdout
    assert _VICTIM in result.stdout


def test_reports_a_hook_installed_leak_that_never_restores(scratch_repo):
    """A hookwrapper that installs but forgets to restore must still be caught.

    This is the regression shape for every conftest converted to the pattern
    #13361 mandates.  Before ``tryfirst``, the leaking wrapper ran outside the
    guard's, its stub landed in the baseline, and this produced zero LEAK lines.
    """
    result = _run_pytest(scratch_repo(_HOOK_INSTALLED_LEAK))

    assert "LEAK:" in result.stdout, result.stdout
    assert _VICTIM in result.stdout


def test_stays_silent_when_the_hookwrapper_restores_properly(scratch_repo):
    """The correct pattern must not be reported — a noisy guard gets disabled."""
    result = _run_pytest(scratch_repo(_restoring_hookwrapper(_VICTIM)))

    assert "LEAK:" not in result.stdout, result.stdout
    assert result.returncode == 0


def test_stays_silent_when_the_leaking_package_is_the_whole_session(scratch_repo):
    """A leak that reaches nobody is not a leak — not even the rootdir node.

    ``pkg_a`` leaks at import time, but the session collects nothing else, so
    the stub never reaches a sibling and there is nothing to report.  Pytest
    still builds a ``Dir`` collector for every level from the rootdir down,
    including ``.``, and that node used to count as "outside ``pkg_a``/" —
    which made every clean session fail the gate and, because the ancestor node
    always wins the per-``(key, owner)`` dedupe, replaced the ``first seen at``
    sibling with the meaningless ``the collection of .``.
    """
    result = _run_pytest(scratch_repo(_IMPORT_TIME_LEAK), targets=("pkg_a",))

    assert "LEAK:" not in result.stdout, result.stdout
    assert result.returncode == 0, result.stdout


def test_the_first_sighting_names_the_sibling_not_the_rootdir(scratch_repo):
    """``first seen at`` is the actionable half of the report — it must be real.

    The rootdir ``Dir`` node is collected before any sibling, so while it
    counted as an escape it always claimed this slot and pointed every
    offender at ``.`` instead of at the package that inherited the stub.
    """
    result = _run_pytest(scratch_repo(_IMPORT_TIME_LEAK))

    assert "LEAK:" in result.stdout, result.stdout
    assert "first seen at the collection of ." not in result.stdout, result.stdout
    assert "pkg_b" in result.stdout, result.stdout


def test_the_guard_does_not_widen_other_pytest_warnings(scratch_repo):
    """The guard must not change warning behaviour for the rest of the suite.

    ``addinivalue_line`` appends to ``filterwarnings`` and the last matching
    entry wins, so an entry written against ``pytest.PytestWarning`` silently
    overrode any ini-level ``ignore`` of *any* subclass of it and flipped
    every pytest warning from "once per location" to "always".  The guard's
    entry names only its own warning class, so this repo's
    ``ignore::pytest.PytestUnknownMarkWarning`` still holds.
    """
    repo = scratch_repo(_IMPORT_TIME_LEAK)
    _write(repo / "pytest.ini", _PYTEST_INI_WITH_IGNORE)
    _write(repo / "pkg_b" / "test_pkg_b.py", _UNKNOWN_MARK_TEST)

    result = _run_pytest(repo)

    assert "PytestUnknownMarkWarning" not in result.stdout, result.stdout
    assert "LEAK:" in result.stdout, result.stdout  # the guard is still active


# ---------------------------------------------------------------------------
# #13398 — the shrink-only baseline: new fails, listed passes, fixed delists
# ---------------------------------------------------------------------------


def test_an_unlisted_leak_fails_the_run(scratch_repo):
    """Transition 1: a leak nobody has signed off on is a regression.

    This is the case the guard exists for and the one its predecessor could not
    gate: ``report`` exited 0 on it, and ``error`` — which would have caught it
    — could not be switched on while the known offenders stood.
    """
    repo = scratch_repo(_IMPORT_TIME_LEAK)
    _baseline(repo)  # nothing is allowed to leak

    result = _run_pytest(repo)

    assert "pkg_a/conftest.py" in _owners_on(result.stdout, "LEAK:"), result.stdout
    assert "NOT on" in result.stdout, result.stdout
    assert result.returncode == 1, f"an unlisted leak must fail the run, got {result.returncode}"


def test_a_listed_leak_is_reported_without_failing(scratch_repo):
    """Transition 2: known debt stays green, and stays visible.

    Failing on it would mean the gate could not be switched on until the last
    of #13361's owners was fixed, which is how the previous design stalled.
    Dressing it up as a regression is the other failure mode: a red block per
    shard for something nobody is required to act on is how a guard becomes
    wallpaper.
    """
    repo = scratch_repo(_IMPORT_TIME_LEAK)
    _baseline(repo, repo / "pkg_a" / "conftest.py")

    result = _run_pytest(repo)

    assert "pkg_a/conftest.py" in _owners_on(result.stdout, "known: "), result.stdout
    assert "LEAK:" not in result.stdout, "known debt must not be reported as a regression"
    assert result.returncode == 0, result.stdout


def test_a_listed_owner_that_no_longer_leaks_must_be_delisted(scratch_repo):
    """Transition 3: the list only shrinks, so a fixed entry has to go.

    ``pkg_a`` installs and restores properly here while still being listed.
    Without this rule the baseline decays into a permanent allowlist and each
    fix lands with nothing to show for it; with it, every fix comes with a
    one-line deletion that proves the leak is gone.
    """
    repo = scratch_repo(_restoring_hookwrapper(_VICTIM))
    _baseline(repo, repo / "pkg_a" / "conftest.py")

    result = _run_pytest(repo)

    assert "pkg_a/conftest.py" in _owners_on(result.stdout, "FIXED:"), result.stdout
    assert "remove it from" in result.stdout, result.stdout
    assert result.returncode == 1, f"a stale baseline entry must fail the run, got {result.returncode}"


def test_a_listed_owner_is_not_delisted_by_a_run_that_never_leaves_it(scratch_repo):
    """Silence only counts once the session gave the stub somewhere to escape to.

    ``pytest pkg_a`` collects nothing outside ``pkg_a``, so the leak it still
    has is invisible — and concluding "fixed" from that would fail every narrow
    run in the tree.
    """
    repo = scratch_repo(_IMPORT_TIME_LEAK)
    _baseline(repo, repo / "pkg_a" / "conftest.py")

    result = _run_pytest(repo, targets=("pkg_a",))

    assert "FIXED:" not in result.stdout, result.stdout
    assert result.returncode == 0, result.stdout


def test_a_run_phase_entry_is_never_asked_to_be_delisted(scratch_repo):
    """A ``run-phase`` entry is exempt from the removal check, and must stay so.

    Such an owner installs its stub while its own tests run, so the eleven CI
    shards that collect the module without running any of it see nothing at
    all.  Reading that silence as "fixed" would fail eleven shards over a leak
    that is still there, so the annotation opts the entry out.  Modelled here
    with a listed package that never leaks in this session.
    """
    repo = scratch_repo(_restoring_hookwrapper(_VICTIM))
    owner = (repo / "pkg_a" / "conftest.py").resolve()
    (repo / _BASELINE_FILE).write_text(f"{owner} run-phase\n", encoding="utf-8")

    result = _run_pytest(repo)

    assert "FIXED:" not in result.stdout, result.stdout
    assert result.returncode == 0, result.stdout


def test_an_unlisted_leak_still_fails_when_another_owner_is_listed(scratch_repo):
    """One listed owner must not buy silence for an unlisted one."""
    repo = scratch_repo(_IMPORT_TIME_LEAK, pkg_c=_import_time_leak("victim_pkg_c"))
    _baseline(repo, repo / "pkg_a" / "conftest.py")

    result = _run_pytest(repo, targets=("pkg_a", "pkg_b", "pkg_c"))

    blamed = _owners_on(result.stdout, "LEAK:")
    assert "pkg_c/conftest.py" in blamed, result.stdout
    assert "pkg_a" not in blamed, result.stdout
    assert result.returncode == 1


# ---------------------------------------------------------------------------
# G1 / G3 — the guard must survive xdist, and gate under it
# ---------------------------------------------------------------------------


def _xdist_or_skip() -> None:
    pytest.importorskip("xdist", reason="pytest-xdist is required for the controller tests")


def test_a_leak_warning_does_not_crash_the_xdist_controller(scratch_repo):
    """The warning must round-trip worker -> controller.

    xdist rebuilds worker warnings on the controller by importing the module
    the worker named.  A dishonest ``__module__`` makes that ``getattr`` fail,
    the node goes down, and the entire session is lost to ``INTERNALERROR`` —
    losing every result, which is #13320 all over again.
    """
    _xdist_or_skip()
    result = _run_pytest(scratch_repo(_IMPORT_TIME_LEAK), "-p", "xdist", "-n", "2", "--dist", "loadscope")

    assert "INTERNALERROR" not in result.stdout + result.stderr, result.stdout + result.stderr
    assert "_SysModulesLeakWarning" not in result.stderr
    assert result.returncode != 3, "exit 3 means the session died before reporting"


def test_an_unlisted_leak_fails_the_run_under_xdist(scratch_repo):
    """The gate must hold under ``-n``, not just serially.

    Detection happens in the workers; the exit status and the terminal section
    are decided on the controller.  Without the worker->controller hand-off this
    passed cleanly with no section printed.
    """
    _xdist_or_skip()
    repo = scratch_repo(_IMPORT_TIME_LEAK)
    _baseline(repo)

    result = _run_pytest(repo, "-p", "xdist", "-n", "2", "--dist", "loadscope")

    assert "LEAK:" in result.stdout, result.stdout
    assert result.returncode == 1, f"expected a failing exit status, got {result.returncode}"


def test_all_three_verdicts_hold_under_xdist(scratch_repo):
    """The full three-way split in one ``-n 2 --dist loadscope`` session.

    Every input arrives from another process here, and ``FIXED`` is the
    delicate one: it is the *absence* of a record, so it can only be concluded
    once the last worker has reported both what it saw and which listed owners
    it took outside their own directory.
    """
    _xdist_or_skip()
    repo = scratch_repo(
        _IMPORT_TIME_LEAK,
        pkg_c=_import_time_leak("victim_pkg_c"),
        pkg_d=_restoring_hookwrapper("victim_pkg_d"),
    )
    _baseline(repo, repo / "pkg_a" / "conftest.py", repo / "pkg_d" / "conftest.py")

    result = _run_pytest(
        repo,
        "-p",
        "xdist",
        "-n",
        "2",
        "--dist",
        "loadscope",
        targets=("pkg_a", "pkg_b", "pkg_c", "pkg_d"),
    )

    assert "pkg_c/conftest.py" in _owners_on(result.stdout, "LEAK:"), result.stdout
    assert "pkg_a" not in _owners_on(result.stdout, "LEAK:"), result.stdout
    assert "pkg_a/conftest.py" in _owners_on(result.stdout, "known: "), result.stdout
    assert "pkg_d/conftest.py" in _owners_on(result.stdout, "FIXED:"), result.stdout
    assert result.returncode == 1


def test_survives_a_session_without_pytest_xdist(scratch_repo):
    """The guard must not take down a run that has no xdist at all.

    ``pytest_testnodedown`` is an xdist hookspec.  Declared without
    ``optionalhook``, pluggy's ``check_pending()`` rejects it as an unknown
    hook and kills the session at collection with ``PluginValidationError`` —
    on every CI job that installs bare pytest.  These child sessions run with
    plugin autoload disabled and no ``-p xdist``, which is exactly that shape.
    """
    result = _run_pytest(scratch_repo(_IMPORT_TIME_LEAK))

    assert "PluginValidationError" not in result.stdout, result.stdout
    assert "INTERNALERROR" not in result.stdout
    assert "LEAK:" in result.stdout


def test_off_mode_disables_everything(scratch_repo):
    """The escape hatch has to actually escape."""
    result = _run_pytest(scratch_repo(_IMPORT_TIME_LEAK), env_extra={"AUTOBOT_SYSMODULES_GUARD": "off"})

    assert "LEAK:" not in result.stdout
    assert result.returncode == 0
