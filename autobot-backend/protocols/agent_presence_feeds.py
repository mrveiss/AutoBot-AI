#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Feed the presence registry (#16947) from each kind's authoritative source.

Design (#16946 §2): registration is gated by each kind's own authoritative
source, never a caller-declared blob. These are pull adapters, not new
storage -- each reads the live source directly and reports what it finds.
For a source with no independent notion of "which process is reporting"
(a DB row, a singleton in-memory registry keyed by role), the entity's own
name doubles as `instance_id`: the source itself is what guarantees there is
only ever one, so there is nothing else to disambiguate. An entry a caller
stops syncing simply falls out of `list_live()` once the registry's TTL
passes -- no explicit prune step is needed here.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from llc.models.enums import LLCRunStatus
from llc.services.agent_presence_queries import agent_org_nodes_with_latest_heartbeat
from protocols.agent_kind import AgentKind
from protocols.agent_presence import UNKNOWN_TENANT, AgentPresenceRegistry

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from agents.agent_client import AgentHealthRegistry
    from chat_workflow.manager import ChatWorkflowManager
    from services.agent_terminal.session_manager import SessionManager


async def sync_company_os_presence(registry: AgentPresenceRegistry, session: "AsyncSession", company_id: str) -> None:
    """Report every Company OS agent in *company_id*, busy iff a heartbeat run is `running`."""
    result = await session.execute(agent_org_nodes_with_latest_heartbeat(company_id))
    for node, run in result.all():
        registry.report(
            kind=AgentKind.COMPANY_OS,
            # A null company_id is unresolved tenancy, not shared infrastructure --
            # UNKNOWN_TENANT so it fails closed instead of leaking into every tenant's view.
            tenant_id=str(node.company_id) if node.company_id else UNKNOWN_TENANT,
            name=node.agent_id,
            instance_id=node.agent_id,
            busy=run is not None and run.status == LLCRunStatus.RUNNING.value,
            detail=node.org_role,
        )


async def sync_ai_stack_presence(
    registry: AgentPresenceRegistry,
    health_registry: "AgentHealthRegistry",
    chat_workflow_manager: "ChatWorkflowManager | None" = None,
) -> None:
    """Report every AI-stack role agent as present.

    busy is `chat_workflow_manager.is_processing()` for the whole registry --
    `AgentHealthRegistry` has no per-role concurrency, and neither does
    `ChatWorkflowManager` (one shared singleton serves every role), so "any
    stream in flight" is the honest signal, not one attributed to a single
    role. A richer per-role signal exists in
    `DistributedAgentManager.distributed_agents[...].active_tasks` for agents
    registered there; wiring that in is left for a follow-up. Omitting
    *chat_workflow_manager* reports every role idle rather than guessing.
    """
    busy = chat_workflow_manager.is_processing() if chat_workflow_manager is not None else False
    for agent_type in health_registry.list_agents():
        registry.report(
            kind=AgentKind.AI_STACK,
            tenant_id=None,
            name=agent_type,
            instance_id=agent_type,
            busy=busy,
        )


async def sync_session_presence(registry: AgentPresenceRegistry, session_manager: "SessionManager") -> None:
    """Report every live agent-terminal session; busy iff it has a running command.

    tenant_id (#16975) is `AgentTerminalSession.tenant_id`, captured at
    creation from the creating principal's JWT `org_id` claim -- it cannot be
    recovered afterwards (see that field's own docstring), so a session
    created before #16975 or via a path with no authenticated context falls
    back to UNKNOWN_TENANT here rather than guessing.
    """
    for session_id, session in list(session_manager.sessions.items()):
        registry.report(
            kind=AgentKind.SESSION,
            tenant_id=session.tenant_id or UNKNOWN_TENANT,
            name=session_id,
            instance_id=session_id,
            busy=session.has_running_task(),
            detail=session.agent_id,
        )
