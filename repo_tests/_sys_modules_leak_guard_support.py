# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Fixture bodies and helpers shared by the sys.modules leak guard's unit tests.

Each test module registers them with ``make_guard = pytest.fixture(guard_factory, name="make_guard")``
and ``guard = pytest.fixture(fresh_guard, name="guard")``: the bodies are defined once, here, and
no fixture is imported under its own name (which flake8 reports as F811 at every use).
"""

from __future__ import annotations

import sys
import warnings
from pathlib import Path

from repo_tests.sys_modules_leak_guard import _DISK_CACHE, _LeakGuard

ROOT = Path("/repo")
LLC_CONFTEST = ROOT / "backend" / "llc" / "tests" / "conftest.py"
OTHER_MODULE = ROOT / "backend" / "initialization" / "lifespan_test.py"


def guard_factory(monkeypatch):
    """Build guards over an isolated ``sys.modules`` copy.

    ``_DISK_CACHE`` is pre-seeded so the tests never depend on what happens to
    be installed on the machine running them.
    """
    monkeypatch.setattr(sys, "modules", dict(sys.modules))
    monkeypatch.setattr(
        "repo_tests.sys_modules_leak_guard._DISK_CACHE",
        dict(
            _DISK_CACHE,
            agents=True,
            autobot_shared=True,
            celery=True,
            knowledge=True,
            _sodium=False,
        ),
    )

    def build(removal_candidates: frozenset[str] = frozenset(), root: Path = ROOT) -> _LeakGuard:
        instance = _LeakGuard(root, removal_candidates)
        instance.snapshot()
        return instance

    return build


def fresh_guard(make_guard):
    """A guard with an empty baseline: nothing is listed, every leak is new."""
    return make_guard()


def install_module(name: str, module: object) -> None:
    sys.modules[name] = module  # type: ignore[assignment]


def leaks_for(guard: _LeakGuard, path: Path) -> list[str]:
    """Run a check with warnings suppressed and return the leaked keys."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        guard.check(path, f"the import of {path.name}")
    return [leak.mutation.key for leak in guard.leaks]
