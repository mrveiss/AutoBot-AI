# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The startup requirement gate actually runs, and its lists are true (#13738).

``StartupValidator`` declared the platform's Python floor and had **zero callers
repo-wide** — the one guard meant to catch a sub-floor interpreter never ran.
That floor is load-bearing: ``llc/scheduler/base.py`` calls
``asyncio.Task.cancelling()`` with no fallback, so below it every LLC poll loop
dies after one tick with an ``AttributeError`` nothing retrieves (#13727).

Wiring a dormant check is only half the job — a check nobody ran is also a check
nobody kept true. These tests assert the module lists still import, so the gate
cannot go back to reporting failures that say nothing about the host.
"""

import importlib

import pytest

from startup_validator import (
    StartupValidator,
    enforce_system_requirements,
    validate_system_requirements,
)

# --------------------------------------------------------------- the gate


def test_the_running_interpreter_passes_its_own_floor():
    """The suite runs on a supported interpreter, so the gate must be quiet."""
    assert validate_system_requirements().success


def test_a_sub_floor_interpreter_fails_startup_by_name(monkeypatch):
    """Deliberate failure: below the floor, boot must stop and say why."""
    monkeypatch.setattr("startup_validator.sys.version_info", (3, 10, 0))

    with pytest.raises(RuntimeError) as caught:
        enforce_system_requirements()

    message = str(caught.value)
    assert "3.14" in message, "the error must name the version an operator has to install"
    assert "Python" in message


def test_a_supported_interpreter_boots(monkeypatch):
    """The other half of the deliberate-failure check — at the floor, it passes."""
    monkeypatch.setattr("startup_validator.sys.version_info", (3, 14, 0))

    enforce_system_requirements()  # must not raise


def test_a_full_disk_stops_startup(monkeypatch):
    """The floor is not the only dark check — disk space was unwired too."""
    monkeypatch.setattr("shutil.disk_usage", lambda _path: (100, 100, 0))

    with pytest.raises(RuntimeError, match="disk space"):
        enforce_system_requirements()


def test_low_but_sufficient_disk_warns_without_blocking(monkeypatch, caplog):
    """A warning must not become a boot failure."""
    monkeypatch.setattr("shutil.disk_usage", lambda _path: (100, 100, 3 * 1024**3))

    enforce_system_requirements()  # must not raise

    assert any("Low disk space" in r.getMessage() for r in caplog.records)


# ------------------------------------------------------------ the wiring


def test_the_lifespan_calls_the_gate():
    """AC 1: the gate is invoked on a real startup path, not just importable."""
    import inspect  # noqa: PLC0415

    import initialization.lifespan as lifespan_mod  # noqa: PLC0415

    source = inspect.getsource(lifespan_mod.create_lifespan_manager)
    assert "enforce_system_requirements()" in source


@pytest.mark.asyncio
async def test_the_gate_runs_before_any_service_is_touched(monkeypatch):
    """A sub-floor host must fail before initialization begins, not part-way in.

    If the gate ran after service startup, the operator would get a Redis or
    Ollama error and go looking in the wrong place — which is exactly the
    diagnosis cost #13727 paid.
    """
    from fastapi import FastAPI  # noqa: PLC0415

    import initialization.lifespan as lifespan_mod  # noqa: PLC0415

    touched = []
    monkeypatch.setattr("startup_validator.sys.version_info", (3, 10, 0))
    for name in ("initialize_critical_services", "initialize_background_services"):
        monkeypatch.setattr(lifespan_mod, name, lambda *a, _n=name, **kw: touched.append(_n), raising=False)

    with pytest.raises(RuntimeError):
        async with lifespan_mod.create_lifespan_manager()(FastAPI()):
            pass

    assert touched == [], "startup proceeded past a host that cannot run the platform"


# ------------------------------------------- the lists the gate travels with


@pytest.mark.parametrize("module_name", StartupValidator().critical_imports)
def test_every_declared_critical_import_exists(module_name):
    """``aioredis`` sat here long after the move to ``redis.asyncio`` (#13738)."""
    importlib.import_module(module_name)


@pytest.mark.parametrize("module_name", StartupValidator().autobot_modules)
def test_every_declared_autobot_module_exists(module_name):
    """These read ``src.*`` — a layout the repo has not used in a long time."""
    importlib.import_module(module_name)


@pytest.mark.parametrize("module_name", StartupValidator().optional_modules)
def test_every_declared_optional_module_exists(module_name):
    """Optional means "may be absent by configuration", not "was renamed years ago"."""
    importlib.import_module(module_name)
