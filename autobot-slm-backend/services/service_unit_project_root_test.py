# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Python service units must be able to resolve the project root (#14624).

A deployed SLM backend crash-looped because `resolve_project_root` raises rather
than guessing (#14544) and its systemd unit — two months stale — carried no
`AUTOBOT_PROJECT_ROOT`. Recovery needed an operator on the box, because the
endpoints that deploy a fix live in the service that would not start.

Auditing the templates during that incident turned up the real scope: of the 13
unit templates that run Python, only two set the override. The other eleven
depend entirely on the resolver recognising the install layout, which is what
the first commit in this stack restores.

That dependency is fine, but it should be deliberate and visible rather than
accidental. This records which templates set the override explicitly and fails
if that set ever SHRINKS, and fails if a template is added that neither sets it
nor is recorded as relying on layout resolution.

The list only shrinks by design: converting a template moves it from the second
group to the first, and the guard tightens on its own.
"""

from __future__ import annotations

import re
from pathlib import Path

_ANSIBLE = Path(__file__).resolve().parent.parent / "ansible"
_ROLES = _ANSIBLE / "roles"

#: Templates that set AUTOBOT_PROJECT_ROOT themselves. This set may only grow.
_SETS_OVERRIDE_EXPLICITLY = {
    "slm_agent/slm-agent.service.j2",
    "slm_manager/autobot-slm-backend.service.j2",
}

#: Templates that rely on the resolver recognising the deployed install layout
#: (`is_install_root`, #14624). Recorded so the reliance is a decision rather
#: than an oversight. Converting one to an explicit override is a strict
#: improvement -- move it to the set above.
_RELIES_ON_LAYOUT_RESOLUTION = {
    "agent_config/autobot-agent.service.j2",
    "ai-stack/autobot-ai-stack.service.j2",
    "ai-stack/autobot-chromadb.service.j2",
    "backend/autobot-backend.service.j2",
    "backend/autobot-celery-beat.service.j2",
    "backend/autobot-celery.service.j2",
    "backend/autobot-mcp-bridge@.service.j2",
    "distributed_setup/autobot-coordinator.service.j2",
    "npu-worker/autobot-npu-worker.service.j2",
    "redis/autobot-chromadb.service.j2",
    "tts-worker/autobot-tts-worker.service.j2",
}

_PYTHON_EXEC = re.compile(r"ExecStart=.*(venv/bin|python)")


def _python_service_templates() -> dict:
    """{relative name: text} for every unit template that launches Python."""
    found = {}
    for path in sorted(_ROLES.rglob("templates/*.service.j2")):
        text = path.read_text(encoding="utf-8")
        if not _PYTHON_EXEC.search(text):
            continue
        rel = f"{path.parent.parent.name}/{path.name}"
        found[rel] = text
    return found


def test_the_scan_finds_the_templates():
    """An empty scan reads exactly like a clean one."""
    templates = _python_service_templates()

    assert templates, "no Python service unit templates found — this rule is pinned to the wrong path"
    assert (
        "slm_manager/autobot-slm-backend.service.j2" in templates
    ), "the SLM backend unit is not being scanned, and it is the one that crash-looped"


def test_every_python_unit_is_accounted_for():
    """A new template must make a choice, not inherit one silently."""
    templates = set(_python_service_templates())
    known = _SETS_OVERRIDE_EXPLICITLY | _RELIES_ON_LAYOUT_RESOLUTION

    unaccounted = sorted(templates - known)

    assert not unaccounted, (
        f"unit template(s) run Python but are in neither group: {unaccounted}. "
        "Either set AUTOBOT_PROJECT_ROOT in the template, or record the reliance on "
        "install-layout resolution (#14624)"
    )


def test_the_explicit_set_never_shrinks():
    """Removing an override is a regression toward the outage."""
    templates = _python_service_templates()

    lost = sorted(name for name in _SETS_OVERRIDE_EXPLICITLY if "AUTOBOT_PROJECT_ROOT" not in templates.get(name, ""))

    assert not lost, f"template(s) stopped setting AUTOBOT_PROJECT_ROOT: {lost}"


def test_a_converted_template_is_moved_not_duplicated():
    """Keeps the two groups honest.

    If a template starts setting the override, it belongs in the explicit set —
    otherwise the layout-reliance list overstates how much rests on inference.
    """
    templates = _python_service_templates()

    misfiled = sorted(
        name for name in _RELIES_ON_LAYOUT_RESOLUTION if "AUTOBOT_PROJECT_ROOT" in templates.get(name, "")
    )

    assert not misfiled, (
        f"template(s) now set AUTOBOT_PROJECT_ROOT but are still listed as relying on layout "
        f"resolution — move them to _SETS_OVERRIDE_EXPLICITLY: {misfiled}"
    )
