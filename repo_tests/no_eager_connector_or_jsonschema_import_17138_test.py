# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Guard: two specific eager-import regressions #17138 fixed must not return.

``knowledge/connectors/__init__.py`` used to import every concrete connector
module at package-import time, and ``autobot_shared/plugin_sdk/loader.py``
used to bind ``jsonschema.Draft202012Validator`` at module level. Both landed
third-party dependencies (``aiohttp``, ``defusedxml``, ``jsonschema``) on
every caller of a SIBLING module with no connector/plugin dependency of its
own -- discovered as a recurring red on the migration-gate job's minimal pip
list across #16444, #17134 and #17138 itself.

AST-based, not a substring check: a substring scan for ``"import jsonschema"``
would flag this file's own docstring, and would not catch a re-added import
disguised as ``import knowledge.connectors.gdrive as _gdrive``. Parses each
file once and inspects only module-level (unindented) Import/ImportFrom
nodes -- a deferred import inside a function body is exactly the fix, not a
violation of it.
"""

from __future__ import annotations

import ast

from repo_tests._paths import repo_root

_CONNECTORS_INIT = repo_root() / "autobot-backend" / "knowledge" / "connectors" / "__init__.py"
_PLUGIN_LOADER = repo_root() / "autobot_shared" / "plugin_sdk" / "loader.py"

# Every concrete connector module __init__.py must never import at module
# level (base/models/registry are the lightweight, always-needed exception).
_CONCRETE_CONNECTOR_NAMES = frozenset(
    {
        "database",
        "external_adapter",
        "file_server",
        "gdrive",
        "gitlab",
        "nextcloud",
        "notion",
        "onedrive",
        "web_crawler",
        "confluence",
        "jira",
        "slack",
        "mock",
        "oauth_flow",
    }
)


def _module_level_import_targets(path) -> set[str]:
    """Dotted module names named by top-level Import/ImportFrom nodes only."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    targets: set[str] = set()
    for node in tree.body:  # tree.body only -- module level, not nested in a def/if/try
        if isinstance(node, ast.Import):
            targets.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            targets.add(node.module)
            # `from knowledge.connectors import gdrive` names the submodule as
            # an imported NAME, not as part of `module`, so check those too.
            if node.module.endswith("knowledge.connectors") or node.module == "knowledge.connectors":
                targets.update(f"knowledge.connectors.{alias.name}" for alias in node.names)
    return targets


def test_connectors_init_imports_no_concrete_connector_at_module_level() -> None:
    targets = _module_level_import_targets(_CONNECTORS_INIT)
    offenders = {
        t
        for t in targets
        if t.startswith("knowledge.connectors.") and t.rsplit(".", 1)[-1] in _CONCRETE_CONNECTOR_NAMES
    }
    assert not offenders, (
        f"knowledge/connectors/__init__.py eagerly imports {sorted(offenders)} again -- "
        "this is the #17138 regression (a third-party dep landing on every caller of ANY "
        "module in this package). Register it in registry.py's _LAZY_MODULES/"
        "_FEATURE_GATED_MODULES instead."
    )


def test_plugin_loader_does_not_import_jsonschema_at_module_level() -> None:
    targets = _module_level_import_targets(_PLUGIN_LOADER)
    assert "jsonschema" not in targets, (
        "autobot_shared/plugin_sdk/loader.py imports jsonschema at module level again -- "
        "this is the #17138 regression (reached from middleware/__init__.py -> "
        "plugin_sdk/__init__.py -> loader.py, landing on every caller of ANYTHING in "
        "middleware). Move the import inside the function that uses it."
    )
