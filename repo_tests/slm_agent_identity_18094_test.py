# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""SLM agent identity and key-name hygiene (#18094)."""

from __future__ import annotations

import ast

import pytest
from repo_tests._paths import repo_root

_ROOT = repo_root()
_AGENT = _ROOT / "autobot-slm-backend" / "slm" / "agent" / "agent.py"
_KEY_NAME = "AUTOBOT_INTERNAL_API_KEY"


# The Ansible mirror and the standalone/upgrade copies are gone (#18548, #19040); the role deploys
# this one file, and slm_agent_single_definition_19040_test fails if a copy reappears.
@pytest.mark.parametrize("path", [_AGENT], ids=["canonical"])
def test_agent_reads_the_key_through_the_one_reader(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imported = {
        a.name
        for n in ast.walk(tree)
        if isinstance(n, ast.ImportFrom) and n.module == "autobot_shared"
        for a in n.names
    }
    literals = [n for n in ast.walk(tree) if isinstance(n, ast.Constant) and n.value == _KEY_NAME]
    reader_calls = [
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "internal_api_key"
    ]
    env_name = [n for n in ast.walk(tree) if isinstance(n, ast.Attribute) and n.attr == "INTERNAL_KEY_ENV"]

    assert "node_proxy" in imported
    assert reader_calls, "the agent must call node_proxy.internal_api_key() (#17856 row 13a)"
    assert env_name == [] and literals == [], "the agent must not read the key's env var itself"
