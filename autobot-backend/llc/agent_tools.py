# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""LLC work-object tools for the chat agent (#11501 T1).

Exposes the board/CEO-chat operations — create_task, update_goal,
request_approval, record_decision — as chat-agent tools so the shared chat
pipeline (chat_workflow) can resolve a board message into a real work object
via tool-calling, replacing the bespoke phi3 intent-classifier that always
fell back to "clarify" (KeyError('"intent"'), a double-.format of the JSON
schema prompt).

Each tool is company-scoped: the dispatcher takes the company_id resolved from
the chat request context (LLMIterationContext.context["company_id"]) and opens
its own DB session via the shared async_sessionmaker, so it works outside a
FastAPI request. Reuses the existing llc/services — no duplicated persistence.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, Dict

logger = logging.getLogger(__name__)


# --- Tool schemas advertised to the LLM (function parameters) ---------------

CREATE_TASK_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "title": {"type": "string", "description": "Short imperative title of the work item."},
        "description": {"type": "string", "description": "Optional details / context."},
        "type": {
            "type": "string",
            "enum": ["epic", "feature", "pbi", "task", "bug"],
            "description": "Work item type. Default 'task'.",
        },
        "priority": {
            "type": "string",
            "enum": ["critical", "high", "medium", "low"],
            "description": "Priority. Default 'medium'.",
        },
    },
    "required": ["title"],
}

UPDATE_GOAL_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "goal_id": {"type": "string", "description": "UUID of the goal to update."},
        "title": {"type": "string"},
        "description": {"type": "string"},
        "status": {"type": "string", "description": "New goal status."},
        "due_date": {"type": "string", "description": "ISO-8601 date/datetime."},
    },
    "required": ["goal_id"],
}

REQUEST_APPROVAL_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "gate_type": {
            "type": "string",
            "enum": ["hire", "strategy", "budget_override", "sprint_close", "project_disposal", "finding_promotion"],
            "description": "The approval gate. Default 'strategy'.",
        },
        "summary": {"type": "string", "description": "What is being requested and why."},
    },
    "required": ["summary"],
}

RECORD_DECISION_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "decision": {"type": "string", "description": "The decision being recorded."},
        "rationale": {"type": "string", "description": "Optional rationale / context."},
    },
    "required": ["decision"],
}

LLC_TOOL_SCHEMAS: Dict[str, dict] = {
    "create_task": CREATE_TASK_SCHEMA,
    "update_goal": UPDATE_GOAL_SCHEMA,
    "request_approval": REQUEST_APPROVAL_SCHEMA,
    "record_decision": RECORD_DECISION_SCHEMA,
}

LLC_TOOL_NAMES = frozenset(LLC_TOOL_SCHEMAS)


class LLCToolError(RuntimeError):
    """Raised when an LLC tool cannot be dispatched (bad context/args)."""


def _session_factory():
    """Return the shared async_sessionmaker (lazily, to avoid import cycles)."""
    from user_management.database import get_async_session_factory

    return get_async_session_factory()


def _enum_or_error(enum_cls, value, field: str):
    """Coerce *value* to *enum_cls*, raising LLCToolError (not ValueError) on a
    bad LLM-supplied value so it surfaces as a tool error, not a crash."""
    try:
        return enum_cls(value)
    except ValueError:
        raise LLCToolError(f"invalid {field}: {value!r}") from None


async def _create_task(session, company_id: str, user_id: str | None, params: Dict[str, Any]) -> Dict[str, Any]:
    from .models.enums import WorkItemPriority, WorkItemType
    from .services.work_item_service import WorkItemService

    title = (params.get("title") or "").strip()
    if not title:
        raise LLCToolError("create_task requires a non-empty 'title'")
    item = await WorkItemService().create(
        session,
        company_id=company_id,
        type=_enum_or_error(WorkItemType, params.get("type", "task"), "type"),
        title=title,
        description=params.get("description"),
        priority=_enum_or_error(WorkItemPriority, params.get("priority", "medium"), "priority"),
        # #11501 review: audit actor comes from the authenticated session, never
        # from LLM-supplied params.
        created_by_user_id=user_id,
    )
    return {"entity_type": "work_item", "entity_id": str(item.id), "title": title}


async def _update_goal(session, company_id: str, user_id: str | None, params: Dict[str, Any]) -> Dict[str, Any]:
    from .services.goal import GoalService

    goal_id = params.get("goal_id")
    if not goal_id:
        raise LLCToolError("update_goal requires 'goal_id'")
    svc = GoalService()
    # #11501 review (cross-tenant IDOR): the goal_id is LLM-supplied — verify the
    # goal belongs to THIS company before mutating it, else a board message in
    # one company could edit another company's goal.
    existing = await svc.get(session, uuid.UUID(str(goal_id)))
    if existing is None:
        raise LLCToolError(f"goal {goal_id} not found")
    if str(existing.company_id) != str(company_id):
        raise LLCToolError("goal does not belong to this company")
    fields = {k: v for k, v in params.items() if k != "goal_id" and v is not None}
    goal = await svc.update(session, goal_id=uuid.UUID(str(goal_id)), **fields)
    if goal is None:
        raise LLCToolError(f"goal {goal_id} not found")
    return {"entity_type": "goal", "entity_id": str(goal_id), "updated": sorted(fields)}


async def _request_approval(session, company_id: str, user_id: str | None, params: Dict[str, Any]) -> Dict[str, Any]:
    from .models.enums import ApprovalType
    from .services.approval import ApprovalService

    summary = (params.get("summary") or "").strip()
    if not summary:
        raise LLCToolError("request_approval requires a 'summary'")
    # #11501 review (audit spoofing): requested_by is the AUTHENTICATED user from
    # the chat session — never an LLM-supplied param. No authed user → refuse
    # rather than attribute the request to an arbitrary/forged id.
    if not user_id:
        raise LLCToolError("request_approval requires an authenticated user in the chat context")
    appr = await ApprovalService().request_approval(
        session,
        company_id=uuid.UUID(str(company_id)),
        gate_type=_enum_or_error(ApprovalType, params.get("gate_type", "strategy"), "gate_type"),
        payload={"summary": summary},
        requested_by=uuid.UUID(str(user_id)),
    )
    return {"entity_type": "approval", "entity_id": str(appr.id), "summary": summary}


async def _record_decision(session, company_id: str, user_id: str | None, params: Dict[str, Any]) -> Dict[str, Any]:
    # A decision has no dedicated entity — the CEO-chat thread / decisions KB is
    # the record (T2 persists it). Echo it back so the agent can confirm.
    decision = (params.get("decision") or "").strip()
    if not decision:
        raise LLCToolError("record_decision requires 'decision'")
    return {"entity_type": "decision", "entity_id": None, "decision": decision}


_HANDLERS = {
    "create_task": _create_task,
    "update_goal": _update_goal,
    "request_approval": _request_approval,
    "record_decision": _record_decision,
}


async def dispatch_llc_tool(
    tool_name: str,
    params: Dict[str, Any],
    company_id: str | None,
    user_id: str | None = None,
) -> Dict[str, Any]:
    """Execute an LLC work-object tool company-scoped. Returns a result dict.

    Opens its own DB session (shared async_sessionmaker) so the chat tool
    dispatch path can call it without a FastAPI request. *company_id* and
    *user_id* come from the authenticated chat context — NEVER from LLM params
    (audit/tenant integrity, #11501 review). Raises LLCToolError on invalid
    context/args (the caller surfaces it as a tool error to the LLM).
    """
    if tool_name not in _HANDLERS:
        raise LLCToolError(f"unknown LLC tool '{tool_name}'")
    if not company_id:
        raise LLCToolError(f"{tool_name} requires a company context (no company_id in the chat request)")
    handler = _HANDLERS[tool_name]
    async with _session_factory()() as session:
        async with session.begin():
            result = await handler(session, company_id, user_id, params or {})
    logger.info("LLC tool %s → %s (company=%s)", tool_name, result.get("entity_type"), company_id)
    return {"status": "success", **result}
