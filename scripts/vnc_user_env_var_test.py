# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#14314 guard: the vnc role and the fix-vnc-*.sh scripts must resolve the
VNC account from the SAME environment variable, checked in the SAME priority
order.

Before this fix the canonical role
(``autobot-slm-backend/ansible/roles/vnc``) read only ``VNC_USER`` while
``autobot-infrastructure/shared/scripts/utilities/fix-vnc-desktop.sh`` and
``fix-vnc-wsl.sh`` read only ``AUTOBOT_VNC_USER``. Setting one silently did
nothing on the other path — neither errors, so the failure only shows up
later as a service that cannot read its own password file.

This test parses out the ordered list of env vars each implementation
consults and fails if they ever diverge again: a different spelling, a
different priority order, or a dropped alias.
"""

from __future__ import annotations

import re
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]

_ROLE_DEFAULTS = _REPO_ROOT / "autobot-slm-backend/ansible/roles/vnc/defaults/main.yml"
_SCRIPTS = (
    _REPO_ROOT / "autobot-infrastructure/shared/scripts/utilities/fix-vnc-desktop.sh",
    _REPO_ROOT / "autobot-infrastructure/shared/scripts/utilities/fix-vnc-wsl.sh",
)

# VNC_USER is canonical (#14314); AUTOBOT_VNC_USER is a deprecated alias kept
# working for one release, because an existing host may already have only it
# set.
_CANONICAL_VAR = "VNC_USER"
_DEPRECATED_ALIAS = "AUTOBOT_VNC_USER"

# Ordered `lookup('env', 'NAME')` calls on the role's `vnc_user:` line.
_ROLE_LOOKUP = re.compile(r"lookup\(\s*'env'\s*,\s*'([A-Z_]+)'\s*\)")

# Ordered `-n "${NAME:-}"` guards in the scripts' resolution block.
_SCRIPT_GUARD = re.compile(r'-n\s+"\$\{([A-Z_]+):-\}"')


def _role_env_priority() -> list[str]:
    text = _ROLE_DEFAULTS.read_text(encoding="utf-8")
    line = next(candidate for candidate in text.splitlines() if candidate.strip().startswith("vnc_user:"))
    return _ROLE_LOOKUP.findall(line)


def _script_env_priority(script: Path) -> list[str]:
    text = script.read_text(encoding="utf-8")
    return _SCRIPT_GUARD.findall(text)


def test_the_scan_finds_what_it_is_meant_to_guard():
    """An empty scan reads exactly like a clean one — if either pattern stops
    matching, every rule below passes over nothing and reports success."""
    assert _ROLE_DEFAULTS.is_file(), f"{_ROLE_DEFAULTS} is gone — this test names a file that no longer exists"
    assert _role_env_priority(), (
        f"{_ROLE_DEFAULTS.relative_to(_REPO_ROOT)}: no env-var lookup() found for vnc_user — "
        "the scan pattern is stale, not the repo"
    )
    for script in _SCRIPTS:
        assert script.is_file(), f"{script} is gone — this test names a file that no longer exists"
        assert _script_env_priority(script), (
            f"{script.relative_to(_REPO_ROOT)}: no '-n \"${{NAME:-}}\"' env-var guard found — "
            "the scan pattern is stale, not the repo"
        )


def test_every_implementation_checks_the_canonical_var_first():
    """The role is canonical (#14314) — every implementation must resolve
    VNC_USER before falling back to the deprecated AUTOBOT_VNC_USER alias."""
    role_priority = _role_env_priority()
    assert role_priority and role_priority[0] == _CANONICAL_VAR, (
        f"{_ROLE_DEFAULTS.relative_to(_REPO_ROOT)} resolves vnc_user from {role_priority or 'nothing'} — "
        f"{_CANONICAL_VAR} must be checked first"
    )
    for script in _SCRIPTS:
        priority = _script_env_priority(script)
        assert priority and priority[0] == _CANONICAL_VAR, (
            f"{script.relative_to(_REPO_ROOT)} resolves its VNC user from {priority or 'nothing'} — "
            f"{_CANONICAL_VAR} must be checked first, or this silently diverges from the vnc role "
            "again (#14314)"
        )


def test_every_implementation_reads_the_same_canonical_variable():
    """Assert the invariant, not today's spelling: whatever the role and the
    scripts agree on, they must agree on the SAME name."""
    role_priority = set(_role_env_priority())
    script_priorities = [set(_script_env_priority(script)) for script in _SCRIPTS]
    for script, priority in zip(_SCRIPTS, script_priorities):
        assert priority & role_priority, (
            f"{script.relative_to(_REPO_ROOT)} reads {priority or 'nothing'} while "
            f"{_ROLE_DEFAULTS.relative_to(_REPO_ROOT)} reads {role_priority or 'nothing'} — "
            "no variable name is shared, so setting one does nothing on the other path (#14314)"
        )


def test_the_deprecated_alias_still_works_everywhere_for_one_release():
    """AUTOBOT_VNC_USER must keep working as a fallback (#14314) — a host
    that only set it must not silently start using the 'autobot' default."""
    assert _DEPRECATED_ALIAS in _role_env_priority(), (
        f"{_ROLE_DEFAULTS.relative_to(_REPO_ROOT)} dropped the {_DEPRECATED_ALIAS} deprecated alias"
    )
    for script in _SCRIPTS:
        assert _DEPRECATED_ALIAS in _script_env_priority(script), (
            f"{script.relative_to(_REPO_ROOT)} dropped the {_DEPRECATED_ALIAS} deprecated alias"
        )
