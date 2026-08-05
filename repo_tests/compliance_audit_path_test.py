# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Regression tests for compliance audit-path resolution (#13658).

`ComplianceManager` had no tests at all. These cover the specific defect rather
than the class as a whole: `compliance.yaml` carried a shell placeholder that
`yaml.safe_load` never expands, so `mkdir(parents=True)` created a directory
literally named ``${AUTOBOT_PROJECT_ROOT:-`` relative to the working directory,
and the audit key plus PII access logs were written into it.

Deliberately does not instantiate the manager: construction reaches for Fernet
keys, Redis and the config manager, none of which this defect involves. It lives
in ``repo_tests`` rather than beside ``compliance_manager.py`` for the same
reason — importing that package pulls the whole enterprise-security dependency
chain in, which this file-level guard has no need of.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

_CONFIG = (
    Path(__file__).resolve().parents[1]
    / "autobot-infrastructure"
    / "shared"
    / "config"
    / "security"
    / "compliance.yaml"
)


def _walk(node):
    """Yield every scalar string in a nested YAML structure."""
    if isinstance(node, dict):
        for key, value in node.items():
            yield from _walk(key)
            yield from _walk(value)
    elif isinstance(node, list):
        for item in node:
            yield from _walk(item)
    elif isinstance(node, str):
        yield node


@pytest.fixture(scope="module")
def config() -> dict:
    if not _CONFIG.exists():
        pytest.skip(f"compliance.yaml not found at {_CONFIG}")
    return yaml.safe_load(_CONFIG.read_text(encoding="utf-8"))


def test_no_value_carries_an_unexpandable_placeholder(config) -> None:
    """No string may contain ``${``.

    This file is read with ``yaml.safe_load`` and nothing routes it through
    ``expandvars``, so a shell placeholder here is a literal path component, not
    a variable. Reintroducing one silently recreates #13658.
    """
    offenders = [value for value in _walk(config) if "${" in value]

    assert not offenders, (
        "compliance.yaml is loaded with yaml.safe_load, which does not expand "
        f"variables — these values would be used literally: {offenders}"
    )


def test_audit_base_path_is_omitted_so_the_resolved_default_applies(config) -> None:
    """``base_path`` stays absent unless someone sets an absolute path.

    ``.get(key, default)`` only falls back when the key is *missing*. While the
    broken value was present the correct default could never fire, which is why
    removing the key — rather than editing it — is the fix.
    """
    audit_storage = config.get("audit_storage", {})
    base_path = audit_storage.get("base_path")

    if base_path is not None:
        assert Path(base_path).is_absolute(), (
            "audit_storage.base_path must be absolute: it is consumed directly by "
            "Path(...).mkdir(parents=True), so a relative value creates a junk tree "
            "under the current working directory"
        )
        assert "${" not in base_path

    # The siblings that make the section meaningful must survive the removal.
    for key in ("encrypt_sensitive", "integrity_monitoring", "backup_enabled"):
        assert key in audit_storage, f"audit_storage lost {key}"
