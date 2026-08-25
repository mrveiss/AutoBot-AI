# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""AutoBot Python SDK — typed async client for the AutoBot REST API.

Quick start::

    import asyncio
    from autobot_sdk import AutoBot

    async def main():
        async with AutoBot() as bot:
            sessions = await bot.sessions.list()
            print(sessions.data)

    asyncio.run(main())

Auth: set AUTOBOT_API_TOKEN env var, or pass ``token=`` to AutoBot().

Base URL: AUTOBOT_BASE_URL, else AUTOBOT_BACKEND_HOST/AUTOBOT_BACKEND_PORT.
Resource paths are written without the ``/api`` root; the client adds it.
"""

from .autobot import AutoBot
from .client import API_PREFIX, AutoBotClient, api_path, default_base_url
from .models import (
    AnalyticsPerformance,
    AnalyticsUsage,
    AgentConfig,
    AgentHealth,
    ChatMessage,
    DataResponse,
    KnowledgeAddResult,
    KnowledgeEntry,
    KnowledgeSearchResult,
    KnowledgeStats,
    Session,
    SessionCreate,
    SessionDelete,
    SessionList,
    SessionMessages,
    SessionUpdate,
)

__all__ = [
    "API_PREFIX",
    "AutoBot",
    "AutoBotClient",
    "api_path",
    "default_base_url",
    "AnalyticsPerformance",
    "AnalyticsUsage",
    "AgentConfig",
    "AgentHealth",
    "ChatMessage",
    "DataResponse",
    "KnowledgeAddResult",
    "KnowledgeEntry",
    "KnowledgeSearchResult",
    "KnowledgeStats",
    "Session",
    "SessionCreate",
    "SessionDelete",
    "SessionList",
    "SessionMessages",
    "SessionUpdate",
]
