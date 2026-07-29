# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Regression test for Issue #12404 (sibling of #12393/#12398/#12399).

``BackendEndpointScanner``, ``FrontendAPICallScanner`` and
``APIEndpointChecker`` all fall back to ``get_project_root()`` (hardcoded
``parents[4]``) when no ``project_root`` is supplied. In the deployed
standalone rsync layout ``parents[4]`` resolves to ``/opt/autobot`` -- not
the analyzable repo -- so the fallback must instead use
``resolve_project_root()`` (git-walk-up / deployed ``code_source`` probe,
#10730).
"""

import pytest

from unittest.mock import patch

from api.codebase_analytics import api_endpoint_scanner as scanner_mod


class TestProjectRootFallbackUsesResolveProjectRoot:
    """Issue #12404: sibling of #12398/#12399's resolve_project_root fix."""

    def test_backend_scanner_fallback_uses_deployed_layout_aware_root(self, tmp_path):
        deployed_root = tmp_path / "opt_autobot" / "code_source"
        wrong_root = tmp_path / "opt_autobot"

        with patch.object(scanner_mod, "resolve_project_root", return_value=str(deployed_root)):
            backend_scanner = scanner_mod.BackendEndpointScanner(project_root=None)

        assert backend_scanner.project_root == deployed_root
        assert backend_scanner.project_root != wrong_root

    def test_frontend_scanner_fallback_uses_deployed_layout_aware_root(self, tmp_path):
        deployed_root = tmp_path / "opt_autobot" / "code_source"
        wrong_root = tmp_path / "opt_autobot"

        with patch.object(scanner_mod, "resolve_project_root", return_value=str(deployed_root)):
            frontend_scanner = scanner_mod.FrontendAPICallScanner(project_root=None)

        assert frontend_scanner.project_root == deployed_root
        assert frontend_scanner.project_root != wrong_root

    def test_api_endpoint_checker_fallback_uses_deployed_layout_aware_root(self, tmp_path):
        deployed_root = tmp_path / "opt_autobot" / "code_source"
        wrong_root = tmp_path / "opt_autobot"

        with patch.object(scanner_mod, "resolve_project_root", return_value=str(deployed_root)):
            checker = scanner_mod.APIEndpointChecker(project_root=None)

        assert checker.project_root == deployed_root
        assert checker.project_root != wrong_root

    def test_explicit_project_root_is_not_overridden(self, tmp_path):
        """When project_root IS supplied, resolve_project_root() must not
        be consulted at all (the resolved branch is untouched)."""
        explicit_root = tmp_path / "explicit"

        with patch.object(scanner_mod, "resolve_project_root", side_effect=AssertionError("should not be called")):
            backend_scanner = scanner_mod.BackendEndpointScanner(project_root=explicit_root)

        assert backend_scanner.project_root == explicit_root


class TestBackendDirResolution:
    """Issue #12853: the backend is not always directly under the scan root.

    ``project_root / "api"`` found nothing for any layout that nests the
    backend, so the scan reported 0 endpoints against a ~2000-route backend --
    which made every frontend call look like it targeted a missing endpoint.
    """

    @staticmethod
    def _make_backend(root, name):
        """Create a backend package (routes + router registry) under *root*."""
        base = root if name == "." else root / name
        (base / "api").mkdir(parents=True)
        (base / "initialization" / "router_registry").mkdir(parents=True)
        return base

    def test_finds_backend_nested_under_the_scan_root(self, tmp_path):
        backend = self._make_backend(tmp_path, "autobot-backend")

        assert scanner_mod.find_backend_dir(tmp_path) == backend

    def test_finds_backend_directly_at_the_scan_root(self, tmp_path):
        """Callers that already point at the backend keep working."""
        backend = self._make_backend(tmp_path, ".")

        assert scanner_mod.find_backend_dir(tmp_path) == backend

    def test_registry_bearing_candidate_wins_over_a_bare_api_dir(self, tmp_path):
        """A directory that merely contains api/ is not the backend."""
        (tmp_path / "api").mkdir()  # decoy at the root
        backend = self._make_backend(tmp_path, "autobot-backend")

        assert scanner_mod.find_backend_dir(tmp_path) == backend

    def test_unrecognised_layout_falls_back_to_the_scan_root(self, tmp_path):
        assert scanner_mod.find_backend_dir(tmp_path) == tmp_path

    def test_scanner_points_at_the_nested_backend(self, tmp_path):
        backend = self._make_backend(tmp_path, "autobot-backend")
        scanner = scanner_mod.BackendEndpointScanner(project_root=tmp_path)

        assert scanner.backend_path == backend / "api"

    def test_router_registry_is_read_from_the_backend_not_the_scan_root(self, tmp_path):
        """#12853: the registry path was `project_root / "backend" / ...`.

        That exists in no current layout, so no prefix was ever parsed and every
        endpoint was recorded without its router prefix.
        """
        backend = self._make_backend(tmp_path, "autobot-backend")
        registry = backend / "initialization" / "router_registry"
        (registry / "core_routers.py").write_text('("chat", "router", "/chat")\n', encoding="utf-8")

        scanner = scanner_mod.BackendEndpointScanner(project_root=tmp_path)
        scanner._collect_router_prefixes()

        assert (scanner.backend_dir / "initialization" / "router_registry") == registry

    def test_every_router_registry_file_is_parsed(self, tmp_path):
        """A hand-maintained list silently skipped integration_routers.py."""
        backend = self._make_backend(tmp_path, "autobot-backend")
        registry = backend / "initialization" / "router_registry"
        for name in ("analytics_routers.py", "integration_routers.py", "brand_new_routers.py"):
            (registry / name).write_text("ROUTER_CONFIGS = []\n", encoding="utf-8")

        scanner = scanner_mod.BackendEndpointScanner(project_root=tmp_path)
        parsed = []
        with patch.object(scanner, "_parse_config_tuple_registry", side_effect=parsed.append):
            scanner._collect_router_prefixes()

        assert {p.name for p in parsed} == {
            "analytics_routers.py",
            "integration_routers.py",
            "brand_new_routers.py",
        }


class TestRegistryRoutersOutsideApi:
    """Issue #12945: registries mount routers from packages other than api/.

    Those routes were never scanned, so every frontend call to one was reported
    as targeting a missing endpoint.
    """

    @staticmethod
    def _backend_with_registry(root, entries):
        """Build a backend whose registry mounts *entries* (module -> prefix)."""
        backend = root / "autobot-backend"
        (backend / "api").mkdir(parents=True)
        registry = backend / "initialization" / "router_registry"
        registry.mkdir(parents=True)
        lines = [f'    ("{mod}", "{prefix}", ["t"], "{mod.split(".")[-1]}"),' for mod, prefix in entries]
        (registry / "feature_routers.py").write_text(
            "ROUTER_CONFIGS = [\n" + "\n".join(lines) + "\n]\n", encoding="utf-8"
        )
        return backend

    def _scanner_for(self, root, entries):
        scanner = scanner_mod.BackendEndpointScanner(project_root=root)
        scanner._collect_router_prefixes()
        return scanner

    def test_module_outside_api_is_scanned_with_its_registered_prefix(self, tmp_path):
        backend = self._backend_with_registry(tmp_path, [("services.advanced_workflow.routes", "/advanced-workflow")])
        target = backend / "services" / "advanced_workflow"
        target.mkdir(parents=True)
        (target / "routes.py").write_text('@router.get("/templates")\nasync def templates(): ...\n', encoding="utf-8")

        scanner = self._scanner_for(tmp_path, None)
        found = scanner._registry_router_files()

        assert found == {target / "routes.py": "/api/advanced-workflow"}

    def test_registered_prefix_reaches_the_scanned_endpoint_path(self, tmp_path):
        """The stem of routes.py matches nothing, so the prefix must be carried."""
        backend = self._backend_with_registry(tmp_path, [("services.advanced_workflow.routes", "/advanced-workflow")])
        target = backend / "services" / "advanced_workflow"
        target.mkdir(parents=True)
        (target / "routes.py").write_text('@router.get("/templates")\nasync def templates(): ...\n', encoding="utf-8")

        scanner = scanner_mod.BackendEndpointScanner(project_root=tmp_path)
        paths = [e.path for e in scanner.scan_all_endpoints()]

        assert "/api/advanced-workflow/templates" in paths

    def test_api_modules_are_not_duplicated_by_the_external_walk(self, tmp_path):
        """api.* entries are already covered by the api/ walk."""
        self._backend_with_registry(tmp_path, [("api.chat", "/chat")])

        scanner = self._scanner_for(tmp_path, None)

        assert scanner._registry_router_files() == {}

    @staticmethod
    def _make_package(backend, init_body, submodules):
        """Create a registry-mounted package with its own router."""
        pkg = backend / "llc" / "api"
        pkg.mkdir(parents=True)
        (pkg / "__init__.py").write_text(init_body, encoding="utf-8")
        for name, body in submodules.items():
            (pkg / name).write_text(body, encoding="utf-8")
        return pkg

    def test_package_prefix_comes_from_its_own_router(self, tmp_path):
        """#12945: the package router sits between registry and submodule.

        LLC registers as ``("llc.api", "", …)`` -- an empty prefix -- while its
        real paths come from ``APIRouter(prefix="/llc")`` in the package's own
        __init__.py. Using the registry prefix alone yielded ``/api/costs/…``
        instead of ``/api/llc/costs/…``: 182 endpoints of which 4 were real.
        """
        backend = self._backend_with_registry(tmp_path, [("llc.api", "")])
        pkg = self._make_package(
            backend,
            'router = APIRouter(prefix="/llc")\nrouter.include_router(costs_router)\n',
            {"costs.py": 'router = APIRouter(prefix="/costs")\n@router.get("/by-agent")\ndef c(): ...\n'},
        )

        found = self._scanner_for(tmp_path, None)._registry_router_files()

        assert found == {pkg / "costs.py": "/api/llc"}

    def test_package_submodule_route_gets_the_full_served_path(self, tmp_path):
        """/api + /llc (package) + /costs (submodule) + route."""
        backend = self._backend_with_registry(tmp_path, [("llc.api", "")])
        self._make_package(
            backend,
            'router = APIRouter(prefix="/llc")\nrouter.include_router(costs_router)\n',
            {"costs.py": 'router = APIRouter(prefix="/costs")\n@router.get("/by-agent")\ndef c(): ...\n'},
        )

        paths = [e.path for e in scanner_mod.BackendEndpointScanner(project_root=tmp_path).scan_all_endpoints()]

        assert "/api/llc/costs/by-agent" in paths

    def test_package_helper_modules_without_a_router_are_skipped(self, tmp_path):
        """A module that defines no router serves nothing -- guessing invents endpoints."""
        backend = self._backend_with_registry(tmp_path, [("llc.api", "")])
        pkg = self._make_package(
            backend,
            'router = APIRouter(prefix="/llc")\nrouter.include_router(costs_router)\n',
            {
                "costs.py": 'router = APIRouter(prefix="/costs")\n@router.get("/x")\ndef c(): ...\n',
                "helpers.py": "def compute(): return 1\n",
            },
        )

        found = self._scanner_for(tmp_path, None)._registry_router_files()

        assert pkg / "helpers.py" not in found
        assert pkg / "costs.py" in found

    def test_package_that_mounts_nothing_is_skipped(self, tmp_path):
        """No include_router means the entry is not a router package."""
        backend = self._backend_with_registry(tmp_path, [("llc.api", "")])
        self._make_package(
            backend,
            'VERSION = "1"\n',
            {"costs.py": 'router = APIRouter(prefix="/costs")\n@router.get("/x")\ndef c(): ...\n'},
        )

        assert self._scanner_for(tmp_path, None)._registry_router_files() == {}

    def test_missing_module_file_is_ignored(self, tmp_path):
        """A registry entry whose module is absent must not break the scan."""
        self._backend_with_registry(tmp_path, [("services.gone.routes", "/gone")])

        scanner = self._scanner_for(tmp_path, None)

        assert scanner._registry_router_files() == {}


class TestTestFilesAreNotEndpoints:
    """#12953: a route defined in a test is not a served endpoint.

    Counting one pollutes the report in both directions -- it becomes a backend
    endpoint no frontend calls (a phantom "orphaned" finding telling someone to
    wire or delete something that does not exist) and a scanned path absent
    from app.openapi().
    """

    @pytest.mark.parametrize(
        "name",
        ["marketplace_422_test.py", "test_tenant_context_resolution.py"],
    )
    def test_test_modules_are_excluded(self, tmp_path, name):
        backend = tmp_path / "autobot-backend"
        (backend / "api").mkdir(parents=True)
        (backend / "initialization" / "router_registry").mkdir(parents=True)
        (backend / "api" / name).write_text(
            '@router.get("/catalog")\ndef c(): ...\n', encoding="utf-8"
        )

        paths = [e.path for e in scanner_mod.BackendEndpointScanner(project_root=tmp_path).scan_all_endpoints()]

        assert paths == []

    def test_tests_directory_is_excluded(self, tmp_path):
        backend = tmp_path / "autobot-backend"
        (backend / "api" / "tests").mkdir(parents=True)
        (backend / "initialization" / "router_registry").mkdir(parents=True)
        (backend / "api" / "tests" / "helper.py").write_text(
            '@router.get("/x")\ndef c(): ...\n', encoding="utf-8"
        )

        paths = [e.path for e in scanner_mod.BackendEndpointScanner(project_root=tmp_path).scan_all_endpoints()]

        assert paths == []

    def test_real_modules_are_still_scanned(self, tmp_path):
        """The exclusion must not swallow modules that merely mention tests."""
        backend = tmp_path / "autobot-backend"
        (backend / "api").mkdir(parents=True)
        (backend / "initialization" / "router_registry").mkdir(parents=True)
        (backend / "api" / "latest_results.py").write_text(
            '@router.get("/results")\ndef c(): ...\n', encoding="utf-8"
        )

        paths = [e.path for e in scanner_mod.BackendEndpointScanner(project_root=tmp_path).scan_all_endpoints()]

        assert "/api/results" in paths
