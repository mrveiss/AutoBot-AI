# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Tests for the Slack/Confluence/Jira/Mock feature-flag gates (Issue #10538).

The framework's ``knowledge/connectors/__init__.py`` only imports (and
therefore registers, via the ``@ConnectorRegistry.register`` decorator) the
Slack/Confluence/Jira connector modules when the ``kb_enterprise_connectors``
subsystem flag is enabled, and the Mock connector module when
``kb_mock_connector`` is enabled. Since import side effects are process-global
and cached by Python, this is verified two ways:

1. A static source check that each gate exists and covers its module(s)
   (regression guard against someone dropping the ``if`` and always
   importing them).
2. A behavioural check, via a subprocess, that a fresh interpreter with both
   flags left at their default (disabled) never registers "slack",
   "confluence", "jira" or "mock" as connector types.
"""

import os
import subprocess
import sys
from pathlib import Path

_CONNECTORS_INIT = Path(__file__).parent / "__init__.py"


class TestFeatureFlagGateSource:
    """Static check that __init__.py gates the three connectors on the flag."""

    def test_gate_covers_all_three_connectors(self) -> None:
        source = _CONNECTORS_INIT.read_text(encoding="utf-8")
        assert 'is_feature_enabled("kb_enterprise_connectors")' in source

        gate_start = source.index('if is_feature_enabled("kb_enterprise_connectors")')
        gated_block = source[gate_start:]
        assert "import knowledge.connectors.slack" in gated_block
        assert "import knowledge.connectors.confluence" in gated_block
        assert "import knowledge.connectors.jira" in gated_block

    def test_gated_imports_not_unconditional(self) -> None:
        """The gated imports must not also appear in the unconditional block above the gate."""
        source = _CONNECTORS_INIT.read_text(encoding="utf-8")
        gate_start = source.index('if is_feature_enabled("kb_enterprise_connectors")')
        unconditional_block = source[:gate_start]
        assert "import knowledge.connectors.slack" not in unconditional_block
        assert "import knowledge.connectors.confluence" not in unconditional_block
        assert "import knowledge.connectors.jira" not in unconditional_block


class TestMockConnectorGateSource:
    """Static check that __init__.py gates the mock connector on its own flag."""

    def test_gate_covers_mock_connector(self) -> None:
        source = _CONNECTORS_INIT.read_text(encoding="utf-8")
        assert 'is_feature_enabled("kb_mock_connector")' in source

        gate_start = source.index('if is_feature_enabled("kb_mock_connector")')
        gated_block = source[gate_start:]
        assert "import knowledge.connectors.mock" in gated_block

    def test_gated_import_not_unconditional(self) -> None:
        source = _CONNECTORS_INIT.read_text(encoding="utf-8")
        gate_start = source.index('if is_feature_enabled("kb_mock_connector")')
        unconditional_block = source[:gate_start]
        assert "import knowledge.connectors.mock" not in unconditional_block


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
