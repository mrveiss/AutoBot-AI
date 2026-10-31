# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""What the activity log must hold for each scenario step, and who must be recorded as the actor (#19253).

Event names are the ActivityEventType values in llc/models/enums.py. ``writer`` says whether any
code writes that event on the path the step takes, found by reading llc/services (no writer means
the log cannot hold it today, which is #20101's subject). ``owner`` is the open issue that explains
the row's absence; a row missing WITHOUT an owner is a new failure and fails the test red.

An action of None means "some record about this entity by this actor": for a step whose event type
does not exist yet (a goal, a project, a budget change), inventing a name would assert a contract
nobody has made.
"""

from __future__ import annotations

from dataclasses import dataclass

AUDIT = "#20101"


@dataclass(frozen=True)
class Expected:
    step: str
    action: str | None
    actor_type: str
    entity: str  # key into the scenario's ids ("company", "goal", ...) or agents ("agent:a")
    owner: str | None
    writer: str  # where the event is written on this path, or "none"
    after: str | None = None  # key of a timestamp in scenario.ids: only rows at or after it count


EXPECTED: tuple[Expected, ...] = (
    Expected("1", "company.created", "user", "company", AUDIT, "none"),
    Expected("2", "agent.hired", "user", "agent:ceo", AUDIT, "none"),
    Expected("2", "agent.hired", "user", "agent:a", AUDIT, "none"),
    Expected("2", "agent.hired", "user", "agent:b", AUDIT, "none"),
    Expected("3", None, "user", "goal", AUDIT, "no goal event type exists"),
    Expected("3", None, "user", "project", AUDIT, "no project event type exists"),
    Expected("3", "work_item.created", "user", "epic", AUDIT, "none"),
    Expected("3", "work_item.created", "user", "task", AUDIT, "none"),
    Expected(
        "4", "work_item.assigned", "user", "task", AUDIT, "work_item_service.claim_human only (a person claiming)"
    ),
    Expected(
        "5", "heartbeat.started", "system", "agent:a", AUDIT, "none (liveness_monitor writes heartbeat.failed only)"
    ),
    Expected("5", "heartbeat.completed", "system", "agent:a", AUDIT, "none"),
    Expected("6", None, "user", "agent:a", AUDIT, "no budget event type exists", after="t_budget"),
    Expected("7", "control.agent_paused", "user", "agent:b", None, "controls_service.pause_agent"),
    Expected("7", "control.agent_resumed", "user", "agent:b", None, "controls_service.resume_agent"),
    Expected("8", "approval.requested", "user", "approval", AUDIT, "none (sprint_autoclose only)"),
    Expected("8", "approval.approved", "user", "approval", AUDIT, "none"),
)
