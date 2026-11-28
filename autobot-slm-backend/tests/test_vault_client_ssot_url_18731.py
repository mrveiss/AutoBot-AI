# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""vault_client resolves the backend URL through config's one SSOT lookup (#18731).

Source-level on purpose: this suite stubs ``config`` and the vault client in
``sys.modules``, so an identity check on the imported objects would compare mocks.
"""

import ast
from pathlib import Path

_SOURCE = Path(__file__).resolve().parents[1] / "user_management" / "services" / "vault_client.py"


def _tree() -> ast.Module:
    return ast.parse(_SOURCE.read_text(encoding="utf-8"))


def test_vault_client_imports_the_config_ssot_backend_url():
    imported = {
        (node.module, alias.name)
        for node in ast.walk(_tree())
        if isinstance(node, ast.ImportFrom)
        for alias in node.names
    }
    assert ("config", "_get_ssot_backend_url") in imported


def test_vault_client_has_no_private_copy_of_the_lookup():
    defined = {node.name for node in ast.walk(_tree()) if isinstance(node, ast.FunctionDef)}
    assert "_ssot_backend_url" not in defined
    assert "_get_ssot_backend_url" not in defined
