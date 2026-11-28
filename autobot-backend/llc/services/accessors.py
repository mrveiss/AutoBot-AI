# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Process-wide singleton accessors for LLC services (#20889).

``lazy_singleton(X)`` returns a *factory*. Each factory is built once, here;
route code calls ``get_*()`` and never wraps the class inline (an inline
``lazy_singleton(X)()`` builds a fresh factory, hence a fresh instance, per
call, so nothing is ever shared).
"""

from typing import TYPE_CHECKING, Optional

from llc.deps import service_singleton

from .agent_wiki_service import AgentWikiService
from .attachment_service import AttachmentService
from .budget import BudgetService
from .review_gate import ReviewGatePolicyService
from .work_item_gated_done import DoneGate
from .work_item_service import WorkItemService
from .work_product_service import WorkProductService

if TYPE_CHECKING:
    from .handoff import HandoffService

get_work_item_service = service_singleton(WorkItemService)
get_budget_service = service_singleton(BudgetService)
get_work_product_service = service_singleton(WorkProductService)
get_attachment_service = service_singleton(AttachmentService)
get_agent_wiki_service = service_singleton(AgentWikiService)
get_review_gate_service = service_singleton(ReviewGatePolicyService)


def get_handoff_service() -> "HandoffService":
    """The shared handoff service. Imported on first use: its module pulls in ``llc.kb`` (#13057)."""

    from .handoff import HandoffService

    return service_singleton(HandoffService)()


def done_gate_for(
    agent_id: Optional[str] = None, *, is_agent: bool = False, local_person: Optional[str] = None
) -> DoneGate:
    """The review gate for a move to done: the shared gate and handoff services, and who is finishing it.

    *agent_id* is the node of a known agent; *is_agent* says the credential names an agent even without a node;
    *local_person* names the single local user when authentication is disabled. All unset: any other caller.
    """
    return DoneGate(get_review_gate_service(), get_handoff_service(), agent_id, is_agent, local_person)
