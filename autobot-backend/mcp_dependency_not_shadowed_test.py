# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""``import mcp`` must resolve to the installed SDK, never a repo package (#16449).

``autobot-backend/mcp/`` used to shadow the real ``mcp`` PyPI package
(``requirements.txt``'s ``mcp>=2.1.1``) for every module with
``autobot-backend/`` on ``sys.path`` — every ``from mcp.X import Y`` anywhere
in the tree resolved to that local package's own submodules
(``mcp.autobot_server``, ``mcp.auth_throttle``), and the installed SDK was
unreachable by its own name. Renamed to ``mcp_server`` to free the name; this
is the regression guard.

AC3 wants this generic, not ``mcp``-specific: a guard that fails if a FUTURE
top-level package under ``autobot-backend/`` reuses a name this repo also
declares as a PyPI dependency, not just a pinned check on the one name that
already collided. Reuses ``production_requirement_names``/``_normalize`` from
``tools/lint/check_requirements_ci_drift.py`` (loaded the same way
``repo_tests/requirements_ci_drift_test.py`` does) rather than a second
requirements parser, so there is one definition of "declared dependency".
"""

from __future__ import annotations

import importlib
import importlib.util
import sys

from repo_tests._paths import repo_root

REPO_ROOT = repo_root()
_CHECKER_PATH = REPO_ROOT / "tools" / "lint" / "check_requirements_ci_drift.py"


def _load_checker():
    spec = importlib.util.spec_from_file_location("check_requirements_ci_drift", _CHECKER_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


checker = _load_checker()


def _top_level_backend_package_names() -> dict[str, str]:
    """{normalized_name: actual_dir_name} for every top-level dir under autobot-backend/."""
    backend = REPO_ROOT / "autobot-backend"
    return {
        checker._normalize(p.name): p.name
        for p in backend.iterdir()
        if p.is_dir() and not p.name.startswith(".") and p.name != "__pycache__"
    }


def test_no_top_level_backend_package_shadows_a_declared_dependency() -> None:
    """AC3: generic across every top-level autobot-backend/ package, not one name.

    The mcp/ -> mcp_server rename fixed one instance of this defect class;
    this is what catches the next one, whatever it is named.
    """
    declared = checker.production_requirement_names(REPO_ROOT)
    backend_dirs = _top_level_backend_package_names()
    collisions = set(backend_dirs) & set(declared)
    offenders = sorted(
        f"autobot-backend/{backend_dirs[name]}/ shadows declared dependency {declared[name]!r}" for name in collisions
    )
    assert not offenders, (
        f"top-level autobot-backend/ package(s) reuse a name this repo also declares "
        f"as a PyPI dependency (#16449): {offenders}"
    )


def test_import_mcp_resolves_to_the_installed_sdk_not_a_repo_package() -> None:
    sys.modules.pop("mcp", None)
    mcp = importlib.import_module("mcp")
    path = getattr(mcp, "__file__", "") or ""
    assert "site-packages" in path or "dist-packages" in path, (
        f"import mcp resolved to {path!r}, not an installed package — a repo-local "
        "package is shadowing the mcp PyPI SDK again"
    )
    assert "/autobot-backend/" not in path.replace("\\", "/"), (
        f"import mcp resolved to {path!r}, inside autobot-backend/ -- a local " "package is shadowing the mcp PyPI SDK"
    )


def test_the_renamed_package_is_importable_under_its_new_name() -> None:
    mcp_server = importlib.import_module("mcp_server")
    assert "autobot-backend" in (getattr(mcp_server, "__file__", "") or "")
