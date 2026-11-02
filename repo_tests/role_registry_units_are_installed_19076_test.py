# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Every unit the role registry names is one a role actually installs (#19076 review).

Since #19076 the agent reports a role as installed only when systemd knows one of its
units. A registry unit no role renders therefore turns a deployed role into
"not_installed": `vnc` named `tigervncserver`, while roles/vnc installs `vnc-server.service`
(the package ships only the template `tigervncserver@`).
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

from repo_tests._paths import repo_root
from repo_tests._reach import declare

_SLM = "autobot-slm-backend"
_REGISTRY = Path(_SLM) / "services" / "role_registry.py"
_ANSIBLE = Path(_SLM) / "ansible"

#: Units the distro package ships; no role renders them, and that is correct.
PACKAGE_UNITS = frozenset({"postgresql"})


def _registry_units(root: Path) -> list[tuple[str, str]]:
    if not (root / _REGISTRY).is_file():
        return []  # an empty tree is an empty result; the floor below refuses it
    tree = ast.parse((root / _REGISTRY).read_text(encoding="utf-8"))
    pairs: list[tuple[str, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Dict):
            continue
        fields = {k.value: v for k, v in zip(node.keys, node.values) if isinstance(k, ast.Constant)}
        name, unit = fields.get("name"), fields.get("systemd_service")
        if not isinstance(name, ast.Constant) or unit is None:
            continue
        values = [unit] if isinstance(unit, ast.Constant) else list(getattr(unit, "elts", []))
        pairs += [(name.value, v.value) for v in values if isinstance(v, ast.Constant) and v.value]
    return pairs


REACH = declare(
    "role-registry-installed-units",
    discover=_registry_units,
    floor=19,
    what="(role, systemd unit) pairs declared in services/role_registry.py",
)


def _ansible_text(root: Path) -> str:
    parts = []
    for path in sorted((root / _ANSIBLE).rglob("*")):
        if path.is_file() and path.suffix in {".yml", ".yaml", ".j2"}:
            parts += [path.name, path.read_text(encoding="utf-8", errors="replace")]
    return "\n".join(parts)


def _installed_by_a_role(unit: str, text: str) -> bool:
    """Rendered to /etc/systemd/system/<unit>.service, from <unit>.service.j2, or set as a *_service_name."""
    escaped = re.escape(unit)
    return bool(
        re.search(rf"/etc/systemd/system/{escaped}\.service\b", text)
        or re.search(rf"^{escaped}\.service\.j2$", text, re.MULTILINE)
        or re.search(rf"^\s*\w+_service_name:\s*['\"]?{escaped}['\"]?\s*$", text, re.MULTILINE)
    )


def test_every_registry_unit_is_installed_by_a_role() -> None:
    root = repo_root()
    pairs = _registry_units(root)
    REACH.completed(pairs, root)
    text = _ansible_text(root)
    missing = [(r, u) for r, u in pairs if u not in PACKAGE_UNITS and not _installed_by_a_role(u, text)]
    assert not missing, f"registry units no role installs (the agent would report these roles not_installed): {missing}"


def test_the_matcher_tells_an_installed_unit_from_a_template_only_name() -> None:
    text = "vnc_service_name: vnc-server\ndest: /etc/systemd/system/autobot-vnc.service\ntigervncserver@.service\n"
    assert _installed_by_a_role("vnc-server", text)
    assert _installed_by_a_role("autobot-vnc", text)
    assert not _installed_by_a_role("tigervncserver", text)


def test_the_reach_floor_holds() -> None:
    REACH.verify_floor(repo_root())
