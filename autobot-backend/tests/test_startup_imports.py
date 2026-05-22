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
- Abstract method not implemented on module-level singleton (#6732, #6709)

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
KNOWN_BROKEN_AT_TEST_INTRODUCTION: dict[str, str] = {}


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


def _agents_modules() -> list[str]:
    """Discover every importable agents/*.py module relative to autobot-backend.

    Excludes test files and __init__.py so only production agent code is
    exercised. Each module is imported with importlib so that module-level
    singleton construction (e.g. ``json_formatter = JSONFormatterAgent()``)
    runs under the test harness — TypeError from an unimplemented abstract
    method surfaces here instead of at deploy time (#6732 / #6709).
    """
    backend_root = Path(__file__).resolve().parent.parent
    agents_dir = backend_root / "agents"
    modules = []
    for path in sorted(agents_dir.glob("*.py")):
        if path.name == "__init__.py":
            continue
        if path.name.endswith("_test.py"):
            continue
        modules.append(f"agents.{path.stem}")
    return modules


# Known-broken agent modules at the time this test was added. Remove an entry
# when its tracking issue is closed.
KNOWN_BROKEN_AGENTS: dict[str, str] = {}


def _agents_module_params() -> list:
    """Build pytest params with xfail marks for known-broken agent modules."""
    params = []
    for name in _agents_modules():
        if name in KNOWN_BROKEN_AGENTS:
            params.append(
                pytest.param(
                    name,
                    marks=pytest.mark.xfail(
                        reason=f"tracked in {KNOWN_BROKEN_AGENTS[name]}",
                        strict=True,
                    ),
                )
            )
        else:
            params.append(pytest.param(name))
    return params


@pytest.mark.parametrize("module_name", _agents_module_params())
def test_agents_module_imports(module_name: str) -> None:
    """Every autobot-backend/agents/*.py must import without error.

    Specifically catches TypeError raised when a module-level singleton
    instantiates an Agent subclass that does not implement all abstract methods
    (the regression that surfaced in #6709 and was missed by #6540).
    """
    importlib.import_module(module_name)


def _extract_class_names(source: str) -> list[str]:
    """Extract top-level (column-0) ``class Foo(...):`` names from source text.

    Skips nested class definitions inside functions or other classes — only
    flags module-level shadowing, which is what bites import resolution.
    """
    names: list[str] = []
    for line in source.splitlines():
        if not line.startswith("class "):
            continue
        name_part = line[len("class ") :]
        for sep in ("(", ":"):
            idx = name_part.find(sep)
            if idx != -1:
                name_part = name_part[:idx]
                break
        names.append(name_part.strip())
    return names


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
    class_names = _extract_class_names(source)
    duplicates = sorted({n for n in class_names if class_names.count(n) > 1})
    assert not duplicates, (
        f"Duplicate class names in {module_name}: {duplicates}. "
        f"Python last-definition-wins will silently shadow earlier definitions; "
        f"rename one (see #6604 / #6606 for prior precedent)."
    )
    # Touch the module to silence the unused-import lint
    assert module is not None


def test_no_duplicate_class_names_across_schema_modules() -> None:
    """No class name appears in more than one ``schemas_*.py`` module (#6798).

    A name defined in two schema files is fine until a third file tries to
    import it — last-write-wins on the import path silently substitutes the
    other shape and the request breaks at runtime. The smoke test catches the
    same pattern that caused #6604/#6606 but at cross-module granularity.

    Allowlist below documents intentional shared names (e.g. \"Config\" inner
    classes, generic envelopes). Add a new entry only with explicit
    justification.
    """
    # Names known to legitimately appear in multiple schemas_*.py modules.
    # Add to this set only after verifying the duplicates are intentional and
    # share an identical shape.
    #
    # #6799 cleanup complete: CodeSearchGetResponse (deduped to schemas_code),
    # CodeSearchRequest (KB variant → KbCodeSearchRequest), FilePreviewResponse
    # (KB variant → ConversationFilePreviewResponse). Set returns to empty.
    INTENTIONAL_SHARED: set[str] = set()

    backend_root = Path(__file__).resolve().parent.parent
    seen: dict[str, str] = {}  # class_name -> first source module
    collisions: list[str] = []
    for module_name in _schema_modules():
        source = (backend_root / module_name.replace(".", "/")).with_suffix(".py").read_text()
        for class_name in _extract_class_names(source):
            if class_name in INTENTIONAL_SHARED:
                continue
            if class_name in seen and seen[class_name] != module_name:
                collisions.append(f"{class_name!r}: defined in both " f"{seen[class_name]} and {module_name}")
            else:
                seen[class_name] = module_name
    assert not collisions, (
        "Cross-module class-name collisions detected — same name in two "
        "schemas_*.py files will shadow on whichever import path resolves "
        "last. Rename one or add to INTENTIONAL_SHARED with justification:\n  - " + "\n  - ".join(collisions)
    )


def test_no_new_hardcoded_status_strings_in_agents() -> None:
    """Agent code must not add new 'status': 'success' / 'error' literals (#6703).

    The AgentStatus enum in agents/payloads.py is the canonical source.
    Hardcoded status strings bypass the type system — the structural cause of
    #6648 / #6650.

    This test is a regression guard: it asserts the total violation count across
    all agent modules does not exceed the baseline recorded when agents/payloads.py
    was introduced. The count decreases naturally as more helpers are migrated.

    KNOWN_BASELINE was measured against the codebase at introduction time:
      - 70 violations in non-yet-migrated files
      - 15 violations remaining in partially-migrated files (other helpers)
      = 85 total (payloads.py itself is excluded as the canonical types module)

    If this number increases, a new hardcoded literal was added — fail.
    If it decreases, do not raise the baseline (that would allow regressions).
    """
    import re as _re

    _STATUS_LITERAL = _re.compile(r'"status"\s*:\s*"(success|error|warning|unavailable|rate_limited|disabled)"')

    # Excluded from scan: the canonical types module (any match there is infrastructure).
    EXCLUDED: set[str] = {"agents/payloads.py"}

    # Baseline total violation count at the time payloads.py was introduced (#6703).
    # Should only decrease as files are migrated to AgentStatus. Never increase.
    KNOWN_BASELINE: int = 85

    backend_root = Path(__file__).resolve().parent.parent
    agents_dir = backend_root / "agents"
    violations: list[str] = []

    for path in sorted(agents_dir.glob("*.py")):
        rel = f"agents/{path.name}"
        if rel in EXCLUDED:
            continue
        if path.name.endswith("_test.py") or path.name == "__init__.py":
            continue
        source = path.read_text(encoding="utf-8")
        for lineno, line in enumerate(source.splitlines(), 1):
            if _STATUS_LITERAL.search(line):
                violations.append(f"{rel}:{lineno}: {line.strip()}")

    assert len(violations) <= KNOWN_BASELINE, (
        f"New hardcoded status string(s) added to agent code (#6703). "
        f"Count {len(violations)} > baseline {KNOWN_BASELINE}. "
        f"Use AgentStatus enum from agents/payloads.py instead.\n"
        f"All current violations:\n  " + "\n  ".join(violations)
    )


def test_strict_mode_raises_on_router_import_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    """AUTOBOT_FEATURE_ROUTERS_STRICT=1 raises RuntimeError when any router import fails (#6690).

    Verifies the strict-boot path end-to-end:
    - ImportError injected for the first configured feature-router module.
    - Config patched to strict=1 (default in dev/CI after #6690 fix).
    - load_feature_routers() must raise RuntimeError mentioning AUTOBOT_FEATURE_ROUTERS_STRICT=1.
    """
    import importlib as _importlib
    import importlib.util
    import sys
    import types
    from pathlib import Path

    # initialization/__init__.py transitively imports chat_history which may fail
    # in certain local envs. Pre-populate parent-package stubs with __path__ set
    # so the import machinery can find submodules without running __init__.py.
    _backend_root = Path(__file__).resolve().parent.parent
    _pkg_dirs = {
        "initialization": str(_backend_root / "initialization"),
        "initialization.router_registry": str(_backend_root / "initialization/router_registry"),
    }
    for _pkg, _pkg_dir in _pkg_dirs.items():
        if _pkg not in sys.modules:
            _stub = types.ModuleType(_pkg)
            _stub.__path__ = [_pkg_dir]  # type: ignore[attr-defined]
            _stub.__package__ = _pkg
            monkeypatch.setitem(sys.modules, _pkg, _stub)

    feature_routers = _importlib.import_module("initialization.router_registry.feature_routers")

    # Narrow FEATURE_ROUTER_CONFIGS to one synthetic entry so load_feature_routers()
    # doesn't try to import the entire real router list (many of which have
    # pre-existing Python-version or dependency issues in the local test env).
    _fake_module = "initialization._test_fake_router"
    monkeypatch.setattr(
        feature_routers,
        "FEATURE_ROUTER_CONFIGS",
        [(_fake_module, "/fake", ["fake"], "fake_router")],
    )

    def _failing_import(name: str, *args, **kwargs):
        if name == _fake_module:
            raise ImportError(f"injected failure for {name}")
        return _importlib.import_module(name, *args, **kwargs)

    monkeypatch.setenv("AUTOBOT_FEATURE_ROUTERS_STRICT", "1")
    monkeypatch.setattr(feature_routers.config.misc, "feature_routers_strict", "1")
    _fake_importlib = type("_FakeImportlib", (), {"import_module": staticmethod(_failing_import)})()
    monkeypatch.setattr(feature_routers, "importlib", _fake_importlib)

    with pytest.raises(RuntimeError, match="AUTOBOT_FEATURE_ROUTERS_STRICT=1"):
        feature_routers.load_feature_routers()
