# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Inventory-wide ansible vars, flattened for a text-substitution resolver (#15632).

Split out of ``ansible_manifest_resolution`` because that module sits against
the 600-line limit and this is a self-contained concern: turning
``inventory/group_vars`` into the dotted names a template actually writes.

It takes its documents as an argument rather than reading the tree itself, so
the caller keeps one parse and this stays a pure function of it.
"""

def inventory_globals(documents: tuple, inventory_prefix: str) -> dict[str, str]:
    """Inventory-wide vars, flattened to the dotted names a template writes.

    `inventory/group_vars/all.yml` holds `autobot: {base_dir: ...}`, and a role
    default referring to it writes `{{ autobot.base_dir }}` -- so the scope needs
    the dotted key, not the mapping. Ansible resolves these for every play; a
    scope built only from a role's own defaults does not, which is how a role
    default deriving from the SSOT (#15632) made its manifests unresolvable.
    """
    flat: dict[str, str] = {}
    for path, document in documents:
        if not path.startswith(f"{inventory_prefix}/") or not isinstance(document, dict):
            continue
        for key, value in document.items():
            if not isinstance(key, str):
                continue
            if isinstance(value, str):
                flat.setdefault(key, value)
            elif isinstance(value, dict):
                for inner, inner_value in value.items():
                    if isinstance(inner, str) and isinstance(inner_value, str):
                        flat.setdefault(f"{key}.{inner}", inner_value)
    return flat
