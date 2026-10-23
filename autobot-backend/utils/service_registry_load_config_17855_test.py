# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
"""#17855: `ServiceRegistry._load_config_file` reads through the shared loader.

A service in the file is added or updated; a missing file changes nothing, raises nothing and is
never created on disk (the behaviour the shared loader exists to guarantee).
"""

import json
import logging

from utils.service_registry import ServiceConfig, ServiceRegistry


def _registry() -> ServiceRegistry:
    registry = ServiceRegistry.__new__(ServiceRegistry)
    registry.services = {
        "web": ServiceConfig(name="web", host="old", port=1, scheme="http", health_endpoint="/h"),
    }
    registry.logger = logging.getLogger("test")
    return registry


def test_a_yaml_file_updates_and_adds_services(tmp_path):
    path = tmp_path / "services.yaml"
    path.write_text("services:\n  web:\n    host: new\n    port: 8080\n  db:\n    host: dbhost\n    port: 5432\n")
    registry = _registry()
    registry._load_config_file(str(path))
    assert (registry.services["web"].host, registry.services["web"].port) == ("new", 8080)
    assert (registry.services["db"].host, registry.services["db"].port) == ("dbhost", 5432)


def test_a_json_file_is_read_as_json(tmp_path):
    path = tmp_path / "services.json"
    path.write_text(json.dumps({"services": {"web": {"host": "jhost"}}}))
    registry = _registry()
    registry._load_config_file(str(path))
    assert registry.services["web"].host == "jhost"


def test_a_missing_file_changes_nothing_and_is_not_created(tmp_path):
    path = tmp_path / "absent.yaml"
    registry = _registry()
    registry._load_config_file(str(path))
    assert registry.services["web"].host == "old" and not path.exists()
