# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Tests for the Slack/Confluence/Jira/Mock feature-flag gates (Issue #10538).

Since #17138, ``knowledge/connectors/__init__.py`` imports nothing at all —
every connector module, gated ones included, is imported lazily by
``registry.ConnectorRegistry._ensure_loaded``/``_ensure_all_loaded`` on first
use. The ``kb_enterprise_connectors``/``kb_mock_connector`` gates moved with
it: they are now checked at resolve time, in ``registry._FEATURE_GATED_MODULES``
plus the ``is_feature_enabled`` call inside those two methods, rather than at
package-import time. Verified two ways:

1. A static source check that ``registry.py`` still declares all four gated
   types under the right flag (regression guard against someone dropping an
   entry, or moving one into the unconditional ``_LAZY_MODULES`` map).
2. A behavioural check, via a subprocess, that a fresh interpreter with both
   flags left at their default (disabled) never registers "slack",
   "confluence", "jira" or "mock" as connector types.
"""

import os
import subprocess
import sys
from pathlib import Path

_REGISTRY_PY = Path(__file__).parent / "registry.py"


class TestFeatureFlagGateSource:
    """Static check that registry.py gates the three connectors on the flag."""

    def test_gate_covers_all_three_connectors(self) -> None:
        source = _REGISTRY_PY.read_text(encoding="utf-8")
        assert '"confluence": ("knowledge.connectors.confluence", "kb_enterprise_connectors")' in source
        assert '"jira": ("knowledge.connectors.jira", "kb_enterprise_connectors")' in source
        assert '"slack": ("knowledge.connectors.slack", "kb_enterprise_connectors")' in source

    def test_gated_types_not_also_unconditional(self) -> None:
        """The gated types must not also appear in _LAZY_MODULES (unconditional)."""
        import knowledge.connectors.registry as registry_module

        for gated_type in ("slack", "confluence", "jira"):
            assert gated_type not in registry_module._LAZY_MODULES, gated_type


class TestMockConnectorGateSource:
    """Static check that registry.py gates the mock connector on its own flag."""

    def test_gate_covers_mock_connector(self) -> None:
        source = _REGISTRY_PY.read_text(encoding="utf-8")
        assert '"mock": ("knowledge.connectors.mock", "kb_mock_connector")' in source

    def test_gated_type_not_also_unconditional(self) -> None:
        import knowledge.connectors.registry as registry_module

        assert "mock" not in registry_module._LAZY_MODULES


class TestFeatureFlagGateBehaviour:
    """Subprocess check: default-disabled flag keeps the types unregistered."""

    def test_disabled_by_default_no_registration(self) -> None:
        backend_dir = Path(__file__).parents[2]
        project_root = backend_dir.parent
        script = (
            "import sys; "
            "sys.path.insert(0, %r); "
            "sys.path.insert(0, %r); "
            "from knowledge.connectors.registry import ConnectorRegistry; "
            "import knowledge.connectors; "
            "types = ConnectorRegistry.list_types(); "
            "assert 'slack' not in types, types; "
            "assert 'confluence' not in types, types; "
            "assert 'jira' not in types, types; "
            "assert 'mock' not in types, types; "
            "print('OK')"
        ) % (str(project_root), str(backend_dir))
        env = os.environ.copy()
        env.pop("AUTOBOT_FEATURE_KB_ENTERPRISE_CONNECTORS", None)
        env.pop("AUTOBOT_FEATURE_KB_MOCK_CONNECTOR", None)
        result = subprocess.run(
            [sys.executable, "-c", script],
            cwd=str(backend_dir),
            capture_output=True,
            text=True,
            env=env,
            timeout=60,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        assert "OK" in result.stdout

    def test_mock_registers_when_flag_enabled(self) -> None:
        """Enabling AUTOBOT_FEATURE_KB_MOCK_CONNECTOR registers 'mock' only."""
        backend_dir = Path(__file__).parents[2]
        project_root = backend_dir.parent
        script = (
            "import sys; "
            "sys.path.insert(0, %r); "
            "sys.path.insert(0, %r); "
            "from knowledge.connectors.registry import ConnectorRegistry; "
            "import knowledge.connectors; "
            "types = ConnectorRegistry.list_types(); "
            "assert 'mock' in types, types; "
            "assert 'slack' not in types, types; "
            "print('OK')"
        ) % (str(project_root), str(backend_dir))
        env = os.environ.copy()
        env["AUTOBOT_FEATURE_KB_MOCK_CONNECTOR"] = "true"
        env.pop("AUTOBOT_FEATURE_KB_ENTERPRISE_CONNECTORS", None)
        result = subprocess.run(
            [sys.executable, "-c", script],
            cwd=str(backend_dir),
            capture_output=True,
            text=True,
            env=env,
            timeout=60,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        assert "OK" in result.stdout
