# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The systemd units each role of ``role_registry.DEFAULT_ROLES`` runs, read statically (#16025 AC1).

``role_registry.py`` no longer restates a manifest-backed role's units: the manifests under
``autobot-infrastructure`` are their only declaration, and ``role_manifest_shape.systemd_units`` projects them
onto the registry at runtime. A guard that parses the registry source for ``systemd_service`` therefore sees only
the literal fallbacks (a role no manifest names, or whose manifest declares no systemd service). This module is
that guard's reader: it parses the registry and the manifests (neither is imported -- ``role_registry`` needs
``models.database``) and applies the same resolution rule, so a guard checks the units the SLM actually holds.

The rule is ``services/role_manifest_shape.py``'s ``find_role_manifest`` + ``systemd_units``: a manifest whose
``role`` is the canonical spelling of the role owns all its systemd services; otherwise a manifest whose service
lists the role in ``slm_roles`` contributes just those services; a manifest with no systemd service leaves the
registry literal in force. ``autobot-slm-backend/tests/services/test_role_manifest_shape_16025.py`` pins this
reader to the runtime function.
"""

from __future__ import annotations

import ast
from pathlib import Path

import yaml

from tools.lint import _parse_cache as parse_cache

_REGISTRY = Path("autobot-slm-backend") / "services" / "role_registry.py"
_INFRA = Path("autobot-infrastructure")


def _canonical(name: str) -> str:
    if name.startswith("autobot-"):
        return name
    if name.startswith("autobot_"):
        return "autobot-" + name[len("autobot_") :].replace("_", "-")
    return f"autobot-{name}"


def _manifest_services(root: Path) -> dict[str, list[dict]]:
    """``manifest role -> its services`` for every ``autobot-infrastructure/*/manifest.yml``."""
    found = {}
    for path in sorted((root / _INFRA).glob("*/manifest.yml")):
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        found[data.get("role", "")] = data.get("services") or []
    return found


def _units_of(services: list[dict], role: str | None) -> list[str]:
    return [
        s.get("system_service") or s["name"]
        for s in services
        if s.get("type") == "systemd" and (role is None or role in (s.get("slm_roles") or []))
    ]


def manifest_units(role: str, manifests: dict[str, list[dict]]) -> list[str]:
    """The units the manifests give ``role`` (empty when none resolves)."""
    owned = manifests.get(_canonical(role))
    if owned is not None:
        return _units_of(owned, None)
    for services in manifests.values():
        if any(role in (s.get("slm_roles") or []) for s in services):
            return _units_of(services, role)
    return []


def _literal_units(node: ast.expr | None) -> list[str]:
    if isinstance(node, ast.Constant) and node.value:
        return [node.value]
    return [e.value for e in getattr(node, "elts", []) if isinstance(e, ast.Constant) and e.value]


def registry_role_units(root: Path) -> dict[str, list[str]]:
    """``role name -> units`` as ``DEFAULT_ROLES`` holds them: the manifest's, else the registry literal."""
    if not (root / _REGISTRY).is_file():
        return {}
    tree = parse_cache.parse((root / _REGISTRY).read_text(encoding="utf-8"))
    manifests = _manifest_services(root)
    units: dict[str, list[str]] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Dict):
            continue
        fields = {k.value: v for k, v in zip(node.keys, node.values) if isinstance(k, ast.Constant)}
        name = fields.get("name")
        if not isinstance(name, ast.Constant) or not isinstance(name.value, str) or "display_name" not in fields:
            continue
        resolved = manifest_units(name.value, manifests) or _literal_units(fields.get("systemd_service"))
        if resolved:
            units[name.value] = resolved
    return units
