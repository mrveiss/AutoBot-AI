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

from autobot_shared.singleton_factory import lazy_singleton

from .agent_wiki_service import AgentWikiService
from .attachment_service import AttachmentService
from .budget import BudgetService
from .work_item_service import WorkItemService
from .work_product_service import WorkProductService

get_work_item_service = lazy_singleton(WorkItemService)
get_budget_service = lazy_singleton(BudgetService)
get_work_product_service = lazy_singleton(WorkProductService)
get_attachment_service = lazy_singleton(AttachmentService)
get_agent_wiki_service = lazy_singleton(AgentWikiService)
