# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Skill trigger dispatcher (#14406).

Seven builtin skills declare ``triggers=[...]`` in their manifests.  Before
this module the field was written once and read only into serialization dicts
(``registry.list_skills``, ``registry.get_skill_detail``, ``BaseSkill.get_health``)
and rendered in the dashboard.  Nothing resolved an event name to a skill and
nothing invoked one, so the manifest advertised a capability that could not fire.

This module is the missing sink.  ``emit_skill_trigger`` takes a declared event
name, resolves every *enabled* skill whose manifest declares it, maps the event
to that skill's own action via :meth:`BaseSkill.get_trigger_actions`, and
invokes it through :meth:`SkillManager.execute_skill` — the canonical execution
path, so trigger-driven invocations are metered exactly like API-driven ones.

Two sets below make the declaration/emitter relationship checkable rather than
assumed.  ``EMITTED_TRIGGERS`` names the events a live code path actually
produces; ``PENDING_EMITTER_TRIGGERS`` names the declared events that still have
no producer, each with the reason.  ``trigger_dispatcher_test.py`` asserts the
two sets partition the set of triggers declared across all registered manifests
exactly, so a manifest can neither declare a trigger that nothing can produce
nor leave a stale entry behind once a producer lands.
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

from autobot_shared.logging_manager import get_logger
from skills.base_skill import DeclarativeSkill
from skills.manager import get_skill_manager
from skills.registry import get_skill_registry

logger = get_logger(__name__)

#: Declared triggers that a live production code path emits today.  Every name
#: here is proved by a test that starts at the *emitting* function — never at
#: this module's own input — and asserts the declaring skill's handler ran.
EMITTED_TRIGGERS: frozenset[str] = frozenset(
    {
        "agent_capability_gap",
        "explicit_gap_signal",
        "document_uploaded",
    }
)

#: Declared triggers with no producer yet, mapped to the reason.  Tracked as
#: #14483; entries leave this dict only when a real emitter lands, at which
#: point the name moves into ``EMITTED_TRIGGERS`` above.
PENDING_EMITTER_TRIGGERS: Dict[str, str] = {
    "audio_received": "#14483 — ingest points exist but VoiceTranscriptionSkill._transcribe queues nothing",
    "video_received": "#14483 — no video ingest door; media/video/pipeline.py has no production caller",
    "note_requested": "#14483 — no general note API and no note intent",
    "schedule_requested": "#14483 — no calendar API exists",
    "pull_request_opened": "#14483 — webhook carries no diff and CodeReviewSkill handlers are stubs",
    "code_pushed": "#14483 — the GitHub webhook receiver rejects every non-pull_request event",
    "scheduled": "#14483 — Celery Beat has no community-growth job",
    "github_release": "#14483 — no release payload handling anywhere",
}


def resolve_trigger_targets(event: str) -> List[Tuple[str, str]]:
    """Return ``(skill_name, action)`` for every skill dispatchable on *event*.

    A skill is dispatchable when it is registered, enabled, declares *event* in
    ``manifest.triggers``, and binds *event* to one of its own actions.  A
    declared-but-unbound trigger is logged and skipped rather than silently
    dropped — an unbound declaration is the bug this module exists to surface.
    """
    registry = get_skill_registry()
    targets: List[Tuple[str, str]] = []
    for info in registry.list_skills():
        if event not in info.get("triggers", []) or not info.get("enabled"):
            continue
        skill = registry.get(info["name"])
        if skill is None:
            continue
        action = skill.get_trigger_actions().get(event)
        if not action:
            logger.warning(
                "Skill '%s' declares trigger '%s' but binds no action to it",
                info["name"],
                event,
            )
            continue
        targets.append((info["name"], action))
    return targets


async def emit_skill_trigger(event: str, params: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Dispatch *event* to every skill declaring it, returning each result.

    Returns an empty list when no enabled skill declares *event* — a trigger
    with no listener is a normal steady state, not an error.  A failing skill
    comes back as the usual ``{"success": False, ...}`` result dict, because
    :meth:`SkillManager.execute_skill` converts its exceptions; an emitter still
    guards its own call, since that conversion is the callee's promise, not this
    function's.
    """
    targets = resolve_trigger_targets(event)
    if not targets:
        logger.debug("No enabled skill is dispatchable on trigger '%s'", event)
        return []

    manager = get_skill_manager()
    results: List[Dict[str, Any]] = []
    for skill_name, action in targets:
        logger.info("Trigger '%s' dispatching to %s.%s", event, skill_name, action)
        results.append(await manager.execute_skill(skill_name, action, params))
    return results


def declared_event_triggers() -> set[str]:
    """Return every *event-name* trigger declared across registered manifests.

    ``DeclarativeSkill`` manifests are excluded on purpose.  SKILL.md
    front-matter uses ``triggers`` for natural-language routing phrases
    ("fetch URL", "read RSS feed"), not event names, so the two semantics share
    a field but not a contract.  That overload — and the fact the routing index
    never reads the phrases either — is tracked separately as #14483.
    """
    registry = get_skill_registry()
    declared: set[str] = set()
    for info in registry.list_skills():
        skill = registry.get(info["name"])
        if skill is None or isinstance(skill, DeclarativeSkill):
            continue
        declared.update(info.get("triggers", []))
    return declared
