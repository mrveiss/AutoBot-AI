# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""High-level AutoBot entry point combining all resource clients."""

from __future__ import annotations

from .client import AutoBotClient
from .resources.agents import AgentsResource
from .resources.analytics import AnalyticsResource
from .resources.knowledge import KnowledgeResource
from .resources.sessions import SessionsResource


class AutoBot(AutoBotClient):
    """Top-level SDK client with resource namespaces.

    Inherits from AutoBotClient and wires up resource sub-clients::

        async with AutoBot(base_url="http://localhost:8000") as bot:
            s = await bot.sessions.list()
            stats = await bot.knowledge.stats()
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.sessions: SessionsResource = SessionsResource(self)
        self.agents: AgentsResource = AgentsResource(self)
        self.knowledge: KnowledgeResource = KnowledgeResource(self)
        self.analytics: AnalyticsResource = AnalyticsResource(self)
