# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""HealthStatus carries CIRCUIT_OPEN and the backend registry status aliases it (#12771).

`monitor_services.py` imports are pinned in `deploy_scripts_standalone_18132_test.py`.
"""

from __future__ import annotations

import ast

from repo_tests._paths import repo_root

from autobot_shared.status_enums import HealthStatus

_ROOT = repo_root()
_REGISTRY = _ROOT / "autobot-backend/utils/service_registry.py"


# The registry's former private enum, member by member: what the CLI printed via `.value`.
_FORMER_REGISTRY_MEMBERS = {
    "HEALTHY": "healthy",
    "UNHEALTHY": "unhealthy",
    "UNKNOWN": "unknown",
    "CIRCUIT_OPEN": "circuit_open",
}


def test_circuit_open_member_is_canonical() -> None:
    assert HealthStatus.CIRCUIT_OPEN.value == "circuit_open"


def test_four_registry_members_keep_name_and_value() -> None:
    """CLI/consumers see identical values before and after (#12771 decision 2)."""
    assert {n: HealthStatus[n].value for n in _FORMER_REGISTRY_MEMBERS} == _FORMER_REGISTRY_MEMBERS


def test_registry_status_is_an_alias_not_a_class() -> None:
    tree = ast.parse(_REGISTRY.read_text(encoding="utf-8"))
    classes = [n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "RegistryServiceStatus"]
    aliases = [
        n.value.id
        for n in tree.body
        if isinstance(n, ast.Assign)
        and isinstance(n.value, ast.Name)
        and any(isinstance(t, ast.Name) and t.id == "RegistryServiceStatus" for t in n.targets)
    ]
    assert not classes and aliases == ["HealthStatus"], (len(classes), aliases)
