# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Developer-mode error helpers match concrete paths against route templates (#22280)."""

import inspect
import unittest

from api.developer import allowed_methods_for_path

_ENDPOINTS = [
    {"path": "/items/{id}", "method": "GET"},
    {"path": "/items/{id}", "method": "DELETE"},
    {"path": "/health", "method": "GET"},
]


def test_a_concrete_path_matches_its_route_template():
    assert allowed_methods_for_path(_ENDPOINTS, "/items/42") == ["GET", "DELETE"]


def test_a_literal_route_matches_only_itself():
    assert allowed_methods_for_path(_ENDPOINTS, "/health") == ["GET"]
    assert allowed_methods_for_path(_ENDPOINTS, "/health/extra") == []


def test_a_path_no_route_matches_has_no_methods():
    assert allowed_methods_for_path(_ENDPOINTS, "/nothing") == []


class TestBatch139DeveloperCOMPLETE(unittest.TestCase):
    """Batch 139 migration: developer.py complete (4 endpoints, 100%).

    Moved out of api_endpoint_migrations_test.py (#22280) so that file stays under its size ceiling; the
    registry assertions follow #22274 (endpoints are discovered from the served app, not a registry).
    """

    def test_batch_139_get_api_endpoints_simple_pattern(self):
        """Verify get_api_endpoints endpoint uses Simple Pattern"""
        from api import developer

        source = inspect.getsource(developer.get_api_endpoints)
        self.assertIn("@with_error_handling", source)
        self.assertIn("category=ErrorCategory.SERVER_ERROR", source)
        self.assertIn('operation="get_api_endpoints"', source)
        self.assertIn('error_code_prefix="DEVELOPER"', source)

    def test_batch_139_get_developer_config_simple_pattern(self):
        """Verify get_developer_config endpoint uses Simple Pattern"""
        from api import developer

        source = inspect.getsource(developer.get_developer_config)
        self.assertIn("@with_error_handling", source)
        self.assertIn("category=ErrorCategory.SERVER_ERROR", source)
        self.assertIn('operation="get_developer_config"', source)
        self.assertIn('error_code_prefix="DEVELOPER"', source)

    def test_batch_139_update_developer_config_simple_pattern(self):
        """Verify update_developer_config endpoint uses Simple Pattern"""
        from api import developer

        source = inspect.getsource(developer.update_developer_config)
        self.assertIn("@with_error_handling", source)
        self.assertIn("category=ErrorCategory.SERVER_ERROR", source)
        self.assertIn('operation="update_developer_config"', source)
        self.assertIn('error_code_prefix="DEVELOPER"', source)

    def test_batch_139_get_system_info_simple_pattern(self):
        """Verify get_system_info endpoint uses Simple Pattern"""
        from api import developer

        source = inspect.getsource(developer.get_system_info)
        self.assertIn("@with_error_handling", source)
        self.assertIn("category=ErrorCategory.SERVER_ERROR", source)
        self.assertIn('operation="get_system_info"', source)
        self.assertIn('error_code_prefix="DEVELOPER"', source)

    def test_batch_139_all_developer_endpoints_have_decorator(self):
        """Verify all developer endpoints have @with_error_handling decorator"""
        from api import developer

        endpoint_functions = [
            developer.get_api_endpoints,
            developer.get_developer_config,
            developer.update_developer_config,
            developer.get_system_info,
        ]

        for func in endpoint_functions:
            source = inspect.getsource(func)
            self.assertIn(
                "@with_error_handling",
                source,
                f"Endpoint {func.__name__} missing @with_error_handling decorator",
            )

    def test_batch_139_developer_100_percent_milestone(self):
        """Verify developer.py has reached 100% migration"""
        from api import developer

        endpoint_functions = [
            developer.get_api_endpoints,
            developer.get_developer_config,
            developer.update_developer_config,
            developer.get_system_info,
        ]

        migrated_count = sum(1 for func in endpoint_functions if "@with_error_handling" in inspect.getsource(func))

        total_endpoints = 4
        self.assertEqual(
            migrated_count,
            total_endpoints,
            f"Expected {total_endpoints} migrated endpoints, but found {migrated_count}",
        )
        progress_percentage = (migrated_count / total_endpoints) * 100
        self.assertEqual(progress_percentage, 100.0)

    def test_batch_139_migration_preserves_api_registry(self):
        """Verify migration preserves API registry functionality"""
        from api import developer

        source = inspect.getsource(developer.get_api_endpoints)
        self.assertIn("runtime_endpoint_view(request.app)", source)  # #22274: discovered routes
        self.assertNotIn("api_registry", source)  # #22274: the retired registry stays gone
        self.assertIn("developer_mode", source)
        self.assertIn("Developer mode is not enabled", source)

    def test_batch_139_migration_preserves_config_retrieval(self):
        """Verify migration preserves config retrieval"""
        from api import developer

        source = inspect.getsource(developer.get_developer_config)
        self.assertIn("config_manager.get_nested", source)
        self.assertIn("enabled", source)
        self.assertIn("enhanced_errors", source)
        self.assertIn("endpoint_suggestions", source)
        self.assertIn("debug_logging", source)

    def test_batch_139_migration_preserves_config_update(self):
        """Verify migration preserves config update with cache clear"""
        from api import developer

        source = inspect.getsource(developer.update_developer_config)
        self.assertIn("merge_nested_and_save(config_manager", source)
        self.assertIn("ConfigService.clear_cache()", source)
        self.assertIn("Developer configuration updated", source)

    def test_batch_139_migration_preserves_system_info_retrieval(self):
        """Verify migration preserves system info retrieval"""
        from api import developer

        source = inspect.getsource(developer.get_system_info)
        self.assertIn("developer_mode", source)
        self.assertIn("get_backend_config()", source)
        self.assertIn("get_redis_config()", source)
        self.assertIn("llm_config", source)
        self.assertIn("available_routers", source)

    def test_batch_139_migration_preserves_developer_mode_check(self):
        """Verify migration preserves developer mode permission checks"""
        from api import developer

        # Check get_api_endpoints
        source_endpoints = inspect.getsource(developer.get_api_endpoints)
        self.assertIn('config_manager.get_nested("developer.enabled"', source_endpoints)
        self.assertIn("HTTPException(status_code=403", source_endpoints)

        # Check get_system_info
        source_info = inspect.getsource(developer.get_system_info)
        self.assertIn('config_manager.get_nested("developer.enabled"', source_info)
        self.assertIn("HTTPException(status_code=403", source_info)
