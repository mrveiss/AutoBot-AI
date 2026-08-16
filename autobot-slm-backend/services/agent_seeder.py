# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Agent Seeder Service (Issue #939)

Seeds the agents table on first startup with all 29 AutoBot agents.
Mirrors DEFAULT_AGENT_CONFIGS from autobot-backend/api/agent_config.py
without requiring a cross-codebase import.

Called by main.py lifespan via _seed_default_agents().
"""

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from autobot_shared.ssot_config import config as _ssot_config
from models.database import Agent

logger = logging.getLogger(__name__)

# Default Ollama endpoint used for all seeded agents — resolved from SSOT (AUTOBOT_OLLAMA_ENDPOINT)
_DEFAULT_OLLAMA_ENDPOINT = _ssot_config.llm.ollama_endpoint

# All 29 AutoBot agents — mirrors DEFAULT_AGENT_CONFIGS exactly.
# model/provider/endpoint can be overridden via /agent-config in the SLM UI.
# #14321: the roster lives in models/agent_seed_roster.py so the migration
# runner can read it without importing this package (services/__init__.py
# pulls FastAPI). Re-exported here so existing callers are unchanged and the
# roster stays one definition.
from models.agent_seed_roster import SEED_AGENT_CONFIGS  # noqa: E402


async def seed_default_agents(db: AsyncSession) -> int:
    """Seed agents table with all AutoBot agents if not already present.

    Idempotent: skips agents that already exist by agent_id.

    Args:
        db: Active SQLAlchemy async session.

    Returns:
        Number of agents created.
    """
    created = 0
    for cfg in SEED_AGENT_CONFIGS:
        result = await db.execute(select(Agent).where(Agent.agent_id == cfg["agent_id"]))
        if result.scalar_one_or_none() is not None:
            continue

        agent = Agent(
            agent_id=cfg["agent_id"],
            name=cfg["name"],
            description=cfg["description"],
            llm_provider="ollama",
            llm_endpoint=_DEFAULT_OLLAMA_ENDPOINT,
            llm_model=cfg["llm_model"],
            llm_timeout=30,
            llm_temperature=0.7,
            llm_max_tokens=None,
            is_default=cfg["is_default"],
            is_active=cfg["is_active"],
        )
        db.add(agent)
        created += 1
        logger.debug("Seeding agent: %s (%s)", cfg["agent_id"], cfg["name"])

    if created:
        await db.commit()

    return created
