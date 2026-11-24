# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Shared setup for the ``role_manifest_*_test.py`` files (#16025, #22032, #22067).

The real manifests, the role registry's AST, and the placeholder map are read the same way by every file that pins
the manifest-derived role shape; they are declared here once.
"""

import ast
from pathlib import Path

from services.manifest_loader import ManifestLoader

REPO_ROOT = Path(__file__).resolve().parents[3]
REGISTRY_SOURCE = REPO_ROOT / "autobot-slm-backend" / "services" / "role_registry.py"

#: The real manifests' sync targets carry these tokens; ``sync_from_manifest`` refuses an unknown one.
PLACEHOLDERS = {"base_dir": "/b", "agent_dir": "/a"}


def real_manifests():
    """Every manifest under ``autobot-infrastructure``, loaded the way the SLM loads them."""
    return ManifestLoader(infra_base=REPO_ROOT / "autobot-infrastructure").load_all()


def registry_role_fields() -> dict[str, set[str]]:
    """``role name -> the field names`` of every role literal in ``role_registry.py``."""
    tree = ast.parse(REGISTRY_SOURCE.read_text(encoding="utf-8"))
    roles = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Dict):
            fields = {k.value: v for k, v in zip(node.keys, node.values) if isinstance(k, ast.Constant)}
            name = fields.get("name")
            if isinstance(name, ast.Constant) and "display_name" in fields:
                roles[name.value] = set(fields)
    return roles
