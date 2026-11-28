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

import re
from pathlib import Path

from repo_tests._paths import repo_root
from repo_tests._reach import declare
from repo_tests._registry_role_units import registry_role_units

_SLM = "autobot-slm-backend"
_ANSIBLE = Path(_SLM) / "ansible"

#: Units the distro package ships; no role renders them, and that is correct.
PACKAGE_UNITS = frozenset({"postgresql"})


def _registry_units(root: Path) -> list[tuple[str, str]]:
    """(role, unit) pairs DEFAULT_ROLES holds: a manifest's units where one resolves, else the registry literal (#16025)."""
    return [(name, unit) for name, units in registry_role_units(root).items() for unit in units]


REACH = declare(
    "role-registry-installed-units",
    discover=_registry_units,
    what="(role, systemd unit) pairs of services/role_registry.py, manifest units included",
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
