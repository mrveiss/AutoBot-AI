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

import pathlib
from pathlib import Path

import pytest
import yaml

_REPO_ROOT = Path(__file__).resolve().parents[1]

_CONFIG = (
    _REPO_ROOT
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


#: The exact literal `compliance.yaml` used to carry. The guard in
#: ``compliance_manager`` must reconstruct this, and the brace placement is the
#: whole difficulty — see the test below.
_PLACEHOLDER = "${AUTOBOT_PROJECT_ROOT:-/opt/autobot/code_source}/logs/audit"


def test_the_placeholder_path_survives_a_round_trip(tmp_path, monkeypatch) -> None:
    """A guard for the legacy store must use the literal, not hand-split parts.

    ``mkdir(parents=True)`` on the unexpanded value creates a directory whose
    fourth component is ``code_source}`` — the closing brace belongs to it.
    Rebuilding the path as ``Path("${AUTOBOT_PROJECT_ROOT:-") / "opt" / ... /
    "code_source" / ...`` silently drops that brace and yields a path that never
    matches, so a guard written that way can never fire. This pins the round
    trip: what the bug creates is what the literal finds.
    """
    monkeypatch.chdir(tmp_path)

    (tmp_path / _PLACEHOLDER).mkdir(parents=True)
    (tmp_path / _PLACEHOLDER / ".audit_key").write_text("k\n", encoding="utf-8")

    found = pathlib.Path.cwd() / pathlib.Path(_PLACEHOLDER)
    assert found.exists(), "the literal must locate the tree mkdir() created"
    assert (found / ".audit_key").exists()

    hand_split = (
        pathlib.Path.cwd()
        / "${AUTOBOT_PROJECT_ROOT:-"
        / "opt"
        / "autobot"
        / "code_source"
        / "logs"
        / "audit"
    )
    assert not hand_split.exists(), "hand-splitting drops the brace — this must NOT match"


def test_the_guard_constant_matches_that_literal() -> None:
    """``compliance_manager._LEGACY_AUDIT_ROOT`` must equal the literal.

    Read from source rather than imported: importing that module pulls the whole
    enterprise-security dependency chain, and an ``importorskip`` here would be
    order-dependent — a partially-initialised module left in ``sys.modules`` by
    an earlier skip makes a later import appear to succeed.
    """
    src = (
        _REPO_ROOT / "autobot-backend" / "security" / "enterprise" / "compliance_manager.py"
    )
    if not src.exists():
        pytest.skip(f"compliance_manager.py not found at {src}")

    text = src.read_text(encoding="utf-8")
    assert f'_LEGACY_AUDIT_ROOT = Path("{_PLACEHOLDER}")' in text, (
        "the guard constant must be the raw literal; hand-split components drop "
        "the closing brace and the guard silently never fires"
    )
