# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Agent-hire API — general auto-resolve (GH#8487) + company-scoped Haiku tier (GH#8486).

Routes:
  POST /agent-hires                           — create assistant agent, auto-resolves cheap model
  GET  /agent-hires                           — list hire records for the org
  POST /companies/{company_id}/agent-hires    — hire Sonnet or Haiku agent, generates AGENTS.md stub
"""

from __future__ import annotations

import json
import uuid
from typing import Any, Dict, List, Optional, Union

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from api.user_management.dependencies import get_current_user, require_org_context
from autobot_shared.env_utils import env_str
from autobot_shared.logging_manager import get_logger
from llc.adapters import adapter_unavailable_reason, registered_adapter_types
from llc.deps import assert_company_access, service_dep
from llc.services.agent_hire_service import (
    AgentHirePending,
    HirePayload,
    company_requires_hire_approval,
    insert_hired_agent,
    request_hire_approval,
    schedule_hired_agent,
)
from llc.services.approval import ApprovalService
from llc.services.model_tiers import get_model_tier_service
from user_management.database import get_async_session
from user_management.services import TenantContext

logger = get_logger(__name__)

router = APIRouter(tags=["llc-agent-hires"])
_approval_service = service_dep(ApprovalService)

# ---------------------------------------------------------------------------
# Model tier constants (GH#8486)
# ---------------------------------------------------------------------------

SONNET_MODEL = "claude-sonnet-4-6"
HAIKU_MODEL = "claude-haiku-4-5-20251001"

_VALID_MODELS = {SONNET_MODEL, HAIKU_MODEL}

# ---------------------------------------------------------------------------
# Default AGENTS.md templates (GH#8486)
# ---------------------------------------------------------------------------

_SONNET_AGENTS_MD_TEMPLATE = """\
# {agent_name} — Agent Instructions

## Role
{role_description}

## Responsibilities
- Pick up assigned work items from the board.
- Execute tasks, post comments, and mark items done.
- Escalate blockers as comments on the work item.

## Haiku Assistant

You have a Haiku assistant: **{assistant_name}** (agent id: `{assistant_id}`).
Delegate self-contained subtasks via child issues — research, file reading,
boilerplate, config edits, simple fixes, test writing.
Set `parentId` to the current issue.
Handle architectural decisions, complex logic, and security-sensitive work yourself.
Only delegate tasks that would take more than one heartbeat inline.
"""

_SONNET_AGENTS_MD_NO_ASSISTANT = """\
# {agent_name} — Agent Instructions

## Role
{role_description}

## Responsibilities
- Pick up assigned work items from the board.
- Execute tasks, post comments, and mark items done.
- Escalate blockers as comments on the work item.

## Haiku Assistant

No Haiku assistant has been paired yet.  To add one, hire a Haiku-class agent
with `reportsTo` set to this agent's ID and re-run `/agent-hires` with
`assistant_agent_id` pointing to the new assistant.
"""

_HAIKU_AGENTS_MD_TEMPLATE = """\
# {agent_name} — Haiku Assistant Instructions

## Role
Haiku execution assistant for **{reports_to_name}**.

## Scope
Execute self-contained subtasks delegated by the paired Sonnet agent via child
issues.  Do NOT make architectural decisions.  Delegate nothing further.

## Responsibilities
- Execute the child issue as specified.
- Post a brief completion comment.
- Mark the child issue done.
- Do not modify scope without Sonnet approval.
"""

# ---------------------------------------------------------------------------
# GH#8487 — general auto-resolve schemas
# ---------------------------------------------------------------------------


class AgentHireCreate(BaseModel):
    """Request body for POST /agent-hires (GH#8487)."""

    assistant_for: Optional[str] = None
    adapter_config: Optional[Dict[str, Any]] = None
    company_id: Optional[uuid.UUID] = None


class AgentHireRead(BaseModel):
    """Response schema for a created / listed hire (GH#8487)."""

    id: uuid.UUID
    company_id: uuid.UUID
    senior_agent_id: Optional[str]
    assistant_agent_id: str
    resolved_provider: Optional[str]
    resolved_model: Optional[str]
    hire_metadata: Dict[str, Any]


# ---------------------------------------------------------------------------
# GH#8486 — company-scoped Haiku hire schemas
# ---------------------------------------------------------------------------


#: #15907, owner ruling 2026-09-28. A hire that opts into the heartbeat gets a
#: one-minute wake unless it says otherwise.
#:
#: Why a default at all. The scheduler's gate is ``heartbeat_enabled = true AND
#: heartbeat_cron IS NOT NULL`` (``heartbeat_scheduler.py:220-221``), and this
#: field defaulted to ``None``. So an agent hired with ``heartbeat_enabled=true``
#: and no cron was never scheduled: the flag said yes and the column the
#: scheduler actually reads said nothing. Two columns, one of them invisible in
#: every view, is the shape #15907 reported -- and the hire flow reproduced it
#: for any caller who set the flag and not the cron.
#:
#: Why one minute is affordable. #17726's short-circuit returns before creating
#: a run when the agent's queue is empty, so the common wake costs one bounded
#: query and no model invocation. Without that, this default would be 1,440 full
#: agent invocations per agent per day; the ruling made the cadence conditional
#: on the short-circuit landing first, and it is in this same change.
#:
#: ``heartbeat_enabled`` deliberately stays ``False``: opting every hired agent
#: into a cadence is option A from the ruling, which was rejected.
#: ``AUTOBOT_`` prefixed deliberately, against 12 ``LLC_*`` config reads already
#: on main (``llc/config/__init__.py``, three schedulers, the stalled-run sweep,
#: and three in ``heartbeat_scheduler.py`` itself). That family is invisible to
#: the registry's prefix-keyed sweep, which is a real gap -- filed separately
#: rather than fixed here, because renaming twelve live variables is not this
#: change. A new one joins the visible set.
_FALLBACK_HEARTBEAT_CRON = "* * * * *"


def _validated_default_cron() -> str:
    """The configured default cron, or the fallback if it will never fire (#17726 review).

    An unvalidated value here is worse than it looks. It persists into every hire
    that opts into the heartbeat, and the scheduler's repopulate loop answers a
    bad cron with ``logger.warning(...); continue`` -- so the agent is stored
    with ``heartbeat_enabled=true``, is never added to the schedule, and never
    wakes. One warning line per repopulate is the only evidence.

    That is the failure this change exists to remove, inverted: the whole point
    of the idle short-circuit is that a wake which finds nothing still leaves a
    trace. An agent that never wakes at all must not leave less of one.

    So a malformed value is rejected loudly and the operator gets a working
    default rather than silently dead agents. `croniter` absent is a different
    case: it means validation is unavailable, not that the value is bad, so the
    value is accepted and the inability to check is what gets logged.
    """
    raw = env_str("AUTOBOT_LLC_DEFAULT_HEARTBEAT_CRON", _FALLBACK_HEARTBEAT_CRON)
    if raw == _FALLBACK_HEARTBEAT_CRON:
        return raw
    try:
        from croniter import croniter
    except ImportError:
        logger.warning(
            "AUTOBOT_LLC_DEFAULT_HEARTBEAT_CRON=%r accepted unvalidated: croniter is not installed",
            raw,
        )
        return raw
    try:
        # .get_next(), not just the constructor: `0 0 31 2 *` CONSTRUCTS fine and
        # can never fire (February has no 31st). Validation that accepts an
        # unfireable cron leaves exactly the silently-dead agent it was added to
        # prevent -- `get_next()` is what raises CroniterBadDateError.
        croniter(raw).get_next()
    except Exception as exc:
        logger.error(
            "AUTOBOT_LLC_DEFAULT_HEARTBEAT_CRON=%r is not a valid cron (%s); "
            "falling back to %r so hired agents are schedulable",
            raw,
            exc,
            _FALLBACK_HEARTBEAT_CRON,
        )
        return _FALLBACK_HEARTBEAT_CRON
    return raw


DEFAULT_HEARTBEAT_CRON = _validated_default_cron()


class AgentHireRequest(BaseModel):
    """Request body for POST /companies/{company_id}/agent-hires (GH#8486)."""

    agent_name: str = Field(..., description="Human-readable agent name")
    org_role: str = Field("worker", description="Org role: manager | coordinator | specialist | worker")
    title: Optional[str] = Field(None, description="Agent job title")
    capabilities: Optional[str] = Field(None, description="Free-text capability description")
    model: Optional[str] = Field(
        None,
        description=(
            f"Model override. Supported: {SONNET_MODEL!r} (default), {HAIKU_MODEL!r}. "
            "Use Haiku for execution-only assistant agents."
        ),
    )
    reports_to: Optional[str] = Field(None, description="Agent ID of the supervising Sonnet agent")
    assistant_agent_id: Optional[str] = Field(None)
    assistant_name: Optional[str] = Field(None)
    role_description: Optional[str] = Field(None)
    heartbeat_cron: Optional[str] = Field(
        DEFAULT_HEARTBEAT_CRON,
        description="Cron for periodic wake. Defaults to every minute; only used when heartbeat_enabled.",
    )
    heartbeat_enabled: bool = Field(False)
    adapter_type: Optional[str] = Field("claude_code")
    adapter_config: Optional[Dict[str, Any]] = Field(None)


class AgentHireResponse(BaseModel):
    """Response returned when an agent is hired (GH#8486)."""

    agent_id: str
    agent_name: str
    model: str
    org_role: str
    company_id: str
    reports_to: Optional[str]
    instructions_file_path: Optional[str]
    agents_md: str


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


async def _fetch_agent_config(
    session: AsyncSession,
    agent_id: str,
    company_id: str,
) -> Optional[Dict[str, Any]]:
    try:
        result = await session.execute(
            text(
                "SELECT adapter_config FROM agent_org_nodes "
                "WHERE agent_id = :agent_id AND company_id = :company_id LIMIT 1"
            ),
            {"agent_id": agent_id, "company_id": company_id},
        )
        row = result.fetchone()
        if row and row[0]:
            return dict(row[0]) if isinstance(row[0], dict) else {}
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not fetch adapter_config for agent %r: %s", agent_id, exc)
    return None


async def _fetch_company_model_overrides(
    session: AsyncSession,
    company_id: str,
) -> Optional[Dict[str, Any]]:
    try:
        result = await session.execute(
            text("SELECT settings->'model_tier_overrides' FROM organizations " "WHERE id = :company_id LIMIT 1"),
            {"company_id": company_id},
        )
        row = result.fetchone()
        if row and row[0]:
            return dict(row[0]) if isinstance(row[0], dict) else None
    except Exception as exc:  # noqa: BLE001
        logger.debug("Could not fetch company model_tier_overrides for %r: %s", company_id, exc)
    return None


# ---------------------------------------------------------------------------
# GH#8487 — general auto-resolve routes
# ---------------------------------------------------------------------------


@router.post("/agent-hires", response_model=AgentHireRead, status_code=201)
async def create_agent_hire(
    body: AgentHireCreate,
    session: AsyncSession = Depends(get_async_session),
    _current_user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> AgentHireRead:
    """Create an assistant agent with auto-resolved cheap model (GH#8487)."""
    effective_company_id = str(body.company_id) if body.company_id else (str(ctx.org_id) if ctx.org_id else None)
    if not effective_company_id:
        raise HTTPException(status_code=400, detail="company_id is required")
    assert_company_access(ctx, effective_company_id)

    svc = get_model_tier_service()
    senior_adapter_cfg: Optional[Dict[str, Any]] = None
    resolved_provider: Optional[str] = None
    resolved_model: Optional[str] = None

    if body.assistant_for:
        senior_adapter_cfg = await _fetch_agent_config(session, body.assistant_for, effective_company_id)
        if senior_adapter_cfg is None:
            logger.info("Senior agent %r not found in DB; using request body", body.assistant_for)
            senior_adapter_cfg = body.adapter_config or {}

        company_overrides = await _fetch_company_model_overrides(session, effective_company_id)
        resolved_model = svc.resolve_assistant_model(
            senior_agent_adapter_config=senior_adapter_cfg,
            company_overrides=company_overrides,
        )
        if senior_adapter_cfg:
            resolved_provider = svc.detect_provider(senior_adapter_cfg.get("model", ""))

    assistant_adapter_cfg: Dict[str, Any] = dict(senior_adapter_cfg or body.adapter_config or {})
    if resolved_model:
        assistant_adapter_cfg["model"] = resolved_model

    assistant_agent_id = f"assistant-{body.assistant_for or 'standalone'}-{uuid.uuid4().hex[:8]}"
    hire_id = uuid.uuid4()
    hire_metadata: Dict[str, Any] = {
        "adapter_config": assistant_adapter_cfg,
        "creation_strategy": "auto_resolved" if resolved_model else "manual",
    }

    try:
        await session.execute(
            text(
                "INSERT INTO llc_agent_hires "
                "(id, company_id, senior_agent_id, assistant_agent_id, "
                "resolved_provider, resolved_model, hire_metadata) "
                "VALUES (:id, :company_id, :senior_agent_id, :assistant_agent_id, "
                ":resolved_provider, :resolved_model, CAST(:hire_metadata AS jsonb)) "
                "ON CONFLICT DO NOTHING"
            ),
            {
                "id": str(hire_id),
                "company_id": effective_company_id,
                "senior_agent_id": body.assistant_for,
                "assistant_agent_id": assistant_agent_id,
                "resolved_provider": resolved_provider,
                "resolved_model": resolved_model,
                "hire_metadata": json.dumps(hire_metadata),
            },
        )
        await session.commit()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not persist hire record (table may not exist): %s", exc)
        await session.rollback()

    return AgentHireRead(
        id=hire_id,
        company_id=uuid.UUID(effective_company_id),
        senior_agent_id=body.assistant_for,
        assistant_agent_id=assistant_agent_id,
        resolved_provider=resolved_provider,
        resolved_model=resolved_model,
        hire_metadata=hire_metadata,
    )


@router.get("/agent-hires", response_model=List[AgentHireRead])
async def list_agent_hires(
    session: AsyncSession = Depends(get_async_session),
    _current_user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> List[AgentHireRead]:
    """List agent hire records for the caller's org (GH#8487)."""
    if ctx.org_id is None:
        return []
    try:
        result = await session.execute(
            text(
                "SELECT id, company_id, senior_agent_id, assistant_agent_id, "
                "resolved_provider, resolved_model, hire_metadata "
                "FROM llc_agent_hires WHERE company_id = :company_id "
                "ORDER BY created_at DESC LIMIT 200"
            ),
            {"company_id": str(ctx.org_id)},
        )
        rows = result.fetchall()
    except Exception as exc:  # noqa: BLE001
        logger.warning("llc_agent_hires table not available: %s", exc)
        return []

    return [
        AgentHireRead(
            id=uuid.UUID(str(r[0])),
            company_id=uuid.UUID(str(r[1])),
            senior_agent_id=r[2],
            assistant_agent_id=r[3],
            resolved_provider=r[4],
            resolved_model=r[5],
            hire_metadata=dict(r[6]) if r[6] else {},
        )
        for r in rows
    ]


# ---------------------------------------------------------------------------
# GH#8486 — company-scoped Haiku hire route
# ---------------------------------------------------------------------------


def _validate_hire(body: AgentHireRequest) -> str:
    """The hire's resolved model, or a 422 for a model or adapter that cannot run.

    Extracted from ``hire_agent`` (#15907, function length); the checks are unchanged.
    """
    resolved_model = body.model or SONNET_MODEL
    if resolved_model not in _VALID_MODELS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unsupported model {resolved_model!r}. Supported values: {sorted(_VALID_MODELS)}",
        )

    # GH#9008/#9033: reject an unregistered adapter_type at hire time. Without
    # this, an unknown type silently creates an agent whose every heartbeat is
    # skipped (no adapter registered), looking degraded forever.
    resolved_adapter = body.adapter_type or "claude_code"
    if resolved_adapter not in registered_adapter_types():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(f"Unknown adapter_type {resolved_adapter!r}. " f"Registered types: {registered_adapter_types()}"),
        )

    # #12681: registered is not the same as runnable. The check above stops an
    # unknown type, but a known one whose CLI is absent produces the identical
    # symptom it was written to prevent — every heartbeat skipped, the agent
    # looking degraded forever. The availability probe already exists and is
    # already what `GET /adapters` reports; the hire path simply never asked.
    unavailable = adapter_unavailable_reason(resolved_adapter)
    if unavailable:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(f"Adapter {resolved_adapter!r} is registered but cannot run on this " f"deployment: {unavailable}"),
        )
    return resolved_model


def _render_agents_md(body: AgentHireRequest, company_id: uuid.UUID, is_haiku: bool) -> str:
    """The hired agent's AGENTS.md, by tier. Extracted from ``hire_agent`` (#15907)."""
    role_desc = body.role_description or f"{body.agent_name} — LLC agent for company {company_id}."
    if is_haiku:
        reports_to_name = body.reports_to or "the supervising Sonnet agent"
        agents_md = _HAIKU_AGENTS_MD_TEMPLATE.format(
            agent_name=body.agent_name,
            reports_to_name=reports_to_name,
        )
    elif body.assistant_agent_id:
        assistant_name = body.assistant_name or "Haiku Assistant"
        agents_md = _SONNET_AGENTS_MD_TEMPLATE.format(
            agent_name=body.agent_name,
            role_description=role_desc,
            assistant_name=assistant_name,
            assistant_id=body.assistant_agent_id,
        )
    else:
        agents_md = _SONNET_AGENTS_MD_NO_ASSISTANT.format(
            agent_name=body.agent_name,
            role_description=role_desc,
        )
    return agents_md


def _hire_payload(company_id: uuid.UUID, body: AgentHireRequest, resolved_model: str) -> HirePayload:
    """The agent as it will exist: ids fixed now, so the request and the approved hire are the same agent."""
    agent_id = str(uuid.uuid4())
    adapter_cfg: Dict[str, Any] = dict(body.adapter_config or {})
    adapter_cfg["model"] = resolved_model
    return HirePayload(
        agent_id=agent_id,
        agent_name=body.agent_name,
        org_role=body.org_role,
        title=body.title,
        capabilities=body.capabilities,
        reports_to=body.reports_to,
        heartbeat_cron=body.heartbeat_cron,
        heartbeat_enabled=body.heartbeat_enabled,
        adapter_type=body.adapter_type or "claude_code",
        adapter_config=adapter_cfg,
        model=resolved_model,
        instructions_file_path=f"/etc/llc/agents/{company_id}/{agent_id}/AGENTS.md",
    )


def _hire_response(company_id: uuid.UUID, body: AgentHireRequest, hire: HirePayload) -> AgentHireResponse:
    """The 201 answer for a hire that is live now; logs it."""
    logger.info(
        "Hired agent %s (name=%r model=%r company=%s reports_to=%s)",
        hire.agent_id,
        hire.agent_name,
        hire.model,
        company_id,
        hire.reports_to,
    )
    return AgentHireResponse(
        agent_id=hire.agent_id,
        agent_name=hire.agent_name,
        model=hire.model,
        org_role=hire.org_role,
        company_id=str(company_id),
        reports_to=hire.reports_to,
        instructions_file_path=hire.instructions_file_path,
        agents_md=_render_agents_md(body, company_id, hire.model == HAIKU_MODEL),
    )


@router.post(
    "/companies/{company_id}/agent-hires",
    response_model=Union[AgentHireResponse, AgentHirePending],
    status_code=status.HTTP_201_CREATED,
    summary="Hire a new agent (Sonnet or Haiku tier) for a company (GH#8486)",
)
async def hire_agent(
    company_id: uuid.UUID,
    body: AgentHireRequest,
    response: Response,
    session: AsyncSession = Depends(get_async_session),
    svc: ApprovalService = Depends(_approval_service),
    _current_user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> Union[AgentHireResponse, AgentHirePending]:
    """Hire a new LLC agent with explicit model selection and AGENTS.md generation.

    A company with ``require_approval_for_hires`` answers 202 with a pending approval instead:
    the agent is created only when the board approves it (GH#8214).
    """
    assert_company_access(ctx, str(company_id))
    resolved_model = _validate_hire(body)
    hire = _hire_payload(company_id, body, resolved_model)
    if await company_requires_hire_approval(session, company_id):
        if ctx.user_id is None:  # the request must name a verified requester, never the string "None"
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="The hire cannot be attributed to a verified user"
            )
        response.status_code = status.HTTP_202_ACCEPTED
        return await request_hire_approval(session, svc, company_id, hire, ctx.user_id)

    await insert_hired_agent(session, company_id, hire)
    await session.commit()
    # #15907: a hire that opts into the heartbeat wakes without waiting for a restart.
    await schedule_hired_agent(hire)

    return _hire_response(company_id, body, hire)
