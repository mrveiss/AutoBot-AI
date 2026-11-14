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

from typing import Optional

from llc.deps import service_singleton

from .agent_wiki_service import AgentWikiService
from .attachment_service import AttachmentService
from .budget import BudgetService
from .handoff import HandoffService
from .review_gate import ReviewGatePolicyService
from .work_item_gated_done import DoneGate
from .work_item_service import WorkItemService
from .work_product_service import WorkProductService

get_work_item_service = service_singleton(WorkItemService)
get_budget_service = service_singleton(BudgetService)
get_work_product_service = service_singleton(WorkProductService)
get_attachment_service = service_singleton(AttachmentService)
get_agent_wiki_service = service_singleton(AgentWikiService)
get_handoff_service = service_singleton(HandoffService)
get_review_gate_service = service_singleton(ReviewGatePolicyService)


def done_gate_for(agent_id: Optional[str] = None) -> DoneGate:
    """The review gate for a move to done: the shared gate and handoff services, and the agent node finishing it.

    Pass the agent's node id when the credential is a known agent; leave it ``None`` for any other caller.
    """
    return DoneGate(get_review_gate_service(), get_handoff_service(), agent_id)
