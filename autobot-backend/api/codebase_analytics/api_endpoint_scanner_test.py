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
