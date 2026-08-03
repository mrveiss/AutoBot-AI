# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Nested-session cover for the sys.modules leak guard (#13361).

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
  ``AUTOBOT_SYSMODULES_GUARD=error`` was a no-op under ``-n``, which is the only
  shape CI uses.

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

_IMPORT_TIME_LEAK = f"""
import sys, types
sys.modules[{_VICTIM!r}] = types.ModuleType({_VICTIM!r})
"""

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


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(text).lstrip(), encoding="utf-8")


@pytest.fixture
def scratch_repo(tmp_path: Path):
    """Build a minimal two-package repo and return a factory for its conftest."""
    _write(tmp_path / "pytest.ini", _PYTEST_INI)
    _write(tmp_path / "conftest.py", _ROOT_CONFTEST)
    _write(tmp_path / _VICTIM / "__init__.py", "REAL = True\n")
    for pkg in ("pkg_a", "pkg_b"):
        _write(tmp_path / pkg / f"test_{pkg}.py", "def test_ok():\n    assert True\n")

    def seed(leak_source: str) -> Path:
        _write(tmp_path / "pkg_a" / "conftest.py", leak_source)
        return tmp_path

    return seed


def _run_pytest(cwd: Path, *args: str, env_extra: dict | None = None) -> subprocess.CompletedProcess:
    """Run a child pytest session in *cwd* and capture everything it printed.

    Plugin autoload is off so the child does not pay for coverage, anyio,
    asyncio and friends on every one of these sessions — it keeps each test
    comfortably inside the suite's per-test budget.  ``xdist`` is re-enabled
    explicitly by the callers that need ``-n``.
    """
    import os

    env = dict(os.environ)
    env.pop("AUTOBOT_SYSMODULES_GUARD", None)
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
            "pkg_a",
            "pkg_b",
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
    correct = f"""
        import sys, types
        import pytest


        @pytest.hookimpl(hookwrapper=True)
        def pytest_make_collect_report(collector):
            prior = sys.modules.get({_VICTIM!r})
            sys.modules[{_VICTIM!r}] = types.ModuleType({_VICTIM!r})
            try:
                yield
            finally:
                if prior is None:
                    sys.modules.pop({_VICTIM!r}, None)
                else:
                    sys.modules[{_VICTIM!r}] = prior
    """
    result = _run_pytest(scratch_repo(correct))

    assert "LEAK:" not in result.stdout, result.stdout
    assert result.returncode == 0


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


def test_error_mode_fails_the_run_under_xdist(scratch_repo):
    """``AUTOBOT_SYSMODULES_GUARD=error`` must gate under ``-n``, not just serially.

    Detection happens in the workers; the exit status and the terminal section
    are decided on the controller.  Without the worker->controller hand-off this
    passed cleanly with no section printed.
    """
    _xdist_or_skip()
    repo = scratch_repo(_IMPORT_TIME_LEAK)
    result = _run_pytest(
        repo, "-p", "xdist", "-n", "2", "--dist", "loadscope", env_extra={"AUTOBOT_SYSMODULES_GUARD": "error"}
    )

    assert "LEAK:" in result.stdout, result.stdout
    assert result.returncode == 1, f"expected a failing exit status, got {result.returncode}"


def test_error_mode_fails_the_run_serially(scratch_repo):
    """The same gate, without xdist — the serial path must keep working."""
    result = _run_pytest(scratch_repo(_IMPORT_TIME_LEAK), env_extra={"AUTOBOT_SYSMODULES_GUARD": "error"})

    assert "LEAK:" in result.stdout, result.stdout
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
