# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A documented ansible invocation must actually run (#13786).

`slm-service-control.yml` used a bare `hosts: target`, which matches nothing
when the caller forgets to pass one — ok=0, changed=0, exit 0. For a
service-control playbook that reads as "the restart succeeded". #13786 changed
it to `hosts: "{{ target }}"` so the same mistake is an undefined-variable
error instead.

That fix turned every documented example into a hard failure: all twelve
invocations across eleven files passed `service=` and `action=` and no
`target=`. The docs were wrong before too — they just failed silently, which is
the direction that hides.

This derives which playbooks need `target` from the **playbooks themselves**, so
a newly templated `hosts:` is covered without anyone remembering to add it here.
A hardcoded list of playbook names would go stale in the silent direction: a
missing entry checks nothing and reports clean.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
PLAYBOOK_DIRS = ["autobot-slm-backend/ansible/playbooks"]
SKIP_DIRS = {".git", ".worktrees", ".claude", "node_modules", "venv", ".venv"}

# `hosts: "{{ target }}"` — a play whose host list comes from a run-time variable.
_TEMPLATED_HOSTS = re.compile(r"^\s*hosts:\s*[\"']?\{\{\s*([a-z_][a-z0-9_]*)\s*\}\}", re.M | re.I)


def _playbooks_requiring_a_variable() -> dict[str, str]:
    """Map playbook filename -> the variable its `hosts:` needs."""
    required: dict[str, str] = {}
    for rel in PLAYBOOK_DIRS:
        for path in sorted((REPO_ROOT / rel).glob("*.yml")):
            match = _TEMPLATED_HOSTS.search(path.read_text(encoding="utf-8"))
            if match:
                required[path.name] = match.group(1)
    return required


def _markdown_files() -> list[Path]:
    return [
        p
        for p in REPO_ROOT.rglob("*.md")
        if not any(part in SKIP_DIRS for part in p.relative_to(REPO_ROOT).parts)
    ]


def _invocations(text: str, playbook: str) -> list[str]:
    """Each `ansible-playbook ... <playbook> ...` command, line continuations joined."""
    joined = re.sub(r"\\\s*\n\s*", " ", text)
    return [ln for ln in joined.split("\n") if "ansible-playbook" in ln and playbook in ln]


def test_the_discovery_found_something() -> None:
    """Guards against the sweep reaching zero playbooks and reporting clean."""
    required = _playbooks_requiring_a_variable()
    assert required, (
        "no playbook with a templated `hosts:` was found — the pattern or the "
        "search path is wrong, and every assertion below would pass vacuously"
    )


@pytest.mark.parametrize("playbook,variable", sorted(_playbooks_requiring_a_variable().items()))
def test_every_documented_invocation_supplies_the_host_variable(playbook: str, variable: str) -> None:
    offenders: list[str] = []
    for path in _markdown_files():
        text = path.read_text(encoding="utf-8")
        if playbook not in text:
            continue
        for command in _invocations(text, playbook):
            if not re.search(rf"\b{re.escape(variable)}\s*=", command):
                offenders.append(f"{path.relative_to(REPO_ROOT)}: {command.strip()[:120]}")

    assert not offenders, (
        f"{playbook} uses `hosts: \"{{{{ {variable} }}}}\"`, so an invocation without "
        f"{variable}= fails with an undefined-variable error. These documented "
        "commands do not pass it:\n  " + "\n  ".join(offenders)
    )
