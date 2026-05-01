# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2026 mrveiss
# Author: mrveiss
"""
Startup-import smoke test (#6540).

Imports every backend module that participates in startup so that any
NameError / ImportError / Pydantic-validation-at-class-body issue surfaces at
PR time instead of at deploy time.

Catches the recurring #6042-migration regression family:
- Missing imports left behind after class moves (#6536, #6569)
- Duplicate class definitions shadowing each other (#6604)
- Required-field defaults dropped at module level (#6609)
- Wrong-arity factory calls in module bodies (#6613)
- Renamed/missing methods on globally constructed singletons

Runs under pytest. Fast (<5s) — pure imports, no Redis or network calls.
"""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest

# Modules that import each other transitively at startup. Listed explicitly so
# a missing entry on the disk side still fails the test (instead of silently
# being skipped).
ALWAYS_IMPORT_AT_BOOT = [
    "main",
    "app_factory",
    "initialization",
    "initialization.lifespan",
    "initialization.routers",
    "initialization.router_registry",
    "initialization.router_registry.core_routers",
    "initialization.router_registry.feature_routers",
]


def _api_modules() -> list[str]:
    """Discover every importable api/*.py module relative to autobot-backend."""
    backend_root = Path(__file__).resolve().parent.parent
    api_dir = backend_root / "api"
    modules = []
    for path in sorted(api_dir.glob("*.py")):
        if path.name == "__init__.py":
            continue
        if path.name.endswith("_test.py"):
            continue
        modules.append(f"api.{path.stem}")
    return modules


def _schema_modules() -> list[str]:
    """Every api/schemas_*.py module — these participate in cross-imports and
    have been the source of every duplicate-class regression so far.
    """
    backend_root = Path(__file__).resolve().parent.parent
    api_dir = backend_root / "api"
    return [f"api.{p.stem}" for p in sorted(api_dir.glob("schemas_*.py"))]


# Known-broken modules at the time this test was added. Each one is silently
# skipped at boot via feature-router graceful-fallback (#281), so the
# affected /api/* endpoints are absent in production. xfail-marking them
# keeps CI green while ensuring the test still catches NEW regressions of the
# same shape. Remove an entry when its tracking issue is closed.
KNOWN_BROKEN_AT_TEST_INTRODUCTION: dict[str, str] = {
    # #6667 — optional deps not guarded (playwright, docker)
    "api.captcha": "#6667",
    "api.sandbox": "#6667",
}


@pytest.mark.parametrize("module_name", ALWAYS_IMPORT_AT_BOOT)
def test_startup_modules_import(module_name: str) -> None:
    """Each module that boot loads must import without error."""
    importlib.import_module(module_name)


def _api_module_params() -> list:
    """Build pytest params with xfail marks for known-broken modules."""
    params = []
    for name in _api_modules():
        if name in KNOWN_BROKEN_AT_TEST_INTRODUCTION:
            params.append(
                pytest.param(
                    name,
                    marks=pytest.mark.xfail(
                        reason=f"tracked in {KNOWN_BROKEN_AT_TEST_INTRODUCTION[name]}",
                        strict=True,
                    ),
                )
            )
        else:
            params.append(pytest.param(name))
    return params


@pytest.mark.parametrize("module_name", _api_module_params())
def test_api_module_imports(module_name: str) -> None:
    """Every autobot-backend/api/*.py must import without error.

    This is the tripwire that catches:
    - NameError from removed imports (#6536, #6569)
    - Pydantic ValidationError raised at class-body time when a required field
      lacks a default and module-level constructor literals are evaluated
      (e.g. SUPPORTED_PROVIDERS dict in #6604)
    """
    importlib.import_module(module_name)


@pytest.mark.parametrize("module_name", _schema_modules())
def test_no_duplicate_class_names_in_schema_module(module_name: str) -> None:
    """Within a single schemas_*.py module, no class name may appear twice.

    Python's last-definition-wins silently shadows the first definition; when
    the two have different field shapes, callers expecting the first crash at
    runtime (#6604, #6606/#6636).
    """
    module = importlib.import_module(module_name)
    backend_root = Path(__file__).resolve().parent.parent
    source = (backend_root / module_name.replace(".", "/")).with_suffix(".py").read_text()
    class_names: list[str] = []
    for line in source.splitlines():
        stripped = line.lstrip()
        if not stripped.startswith("class "):
            continue
        # Extract class name between "class " and the first "(" or ":"
        name_part = stripped[len("class ") :]
        for sep in ("(", ":"):
            idx = name_part.find(sep)
            if idx != -1:
                name_part = name_part[:idx]
                break
        class_names.append(name_part.strip())
    duplicates = sorted({n for n in class_names if class_names.count(n) > 1})
    assert not duplicates, (
        f"Duplicate class names in {module_name}: {duplicates}. "
        f"Python last-definition-wins will silently shadow earlier definitions; "
        f"rename one (see #6604 / #6606 for prior precedent)."
    )
    # Touch the module to silence the unused-import lint
    assert module is not None
