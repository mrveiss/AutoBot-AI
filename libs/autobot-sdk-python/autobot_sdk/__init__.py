# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
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
"""

from .autobot import AutoBot
from .client import AutoBotClient
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
    "AutoBot",
    "AutoBotClient",
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
