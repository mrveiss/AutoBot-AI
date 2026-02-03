#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Agent Seed Migration Script (Issue #760 Phase 3)

Seeds the SLM agents table with DEFAULT_AGENT_CONFIGS from the backend.
Run this once to populate SLM with existing agent configurations.

Usage:
    cd /home/kali/Desktop/AutoBot
    python slm-server/migrations/seed_agents.py
"""

import asyncio
import logging
import sys
from pathlib import Path

# Add parent directories to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

# Default Ollama endpoint
DEFAULT_OLLAMA_ENDPOINT = "http://127.0.0.1:11434"


async def seed_agents():
    """Seed agents from backend DEFAULT_AGENT_CONFIGS."""
    # Import here to avoid circular imports
    from sqlalchemy import select

    from config import settings  # noqa: F401
    from models.database import Agent
    from services.database import db_service

    # Initialize database
    await db_service.initialize()

    try:
        # Import backend agent configs
        from backend.api.agent_config import DEFAULT_AGENT_CONFIGS
    except ImportError as e:
        logger.error("Failed to import backend agent configs: %s", e)
        logger.info("Make sure you're running from the AutoBot root directory")
        return False

    async with db_service.session() as db:
        created_count = 0
        skipped_count = 0

        for agent_id, config in DEFAULT_AGENT_CONFIGS.items():
            # Check if agent already exists
            result = await db.execute(select(Agent).where(Agent.agent_id == agent_id))
            if result.scalar_one_or_none():
                logger.debug("Agent %s already exists, skipping", agent_id)
                skipped_count += 1
                continue

            # Determine model from config
            default_model = config.get("default_model", "mistral:7b-instruct")

            # Create agent
            agent = Agent(
                agent_id=agent_id,
                name=config["name"],
                description=config.get("description", ""),
                llm_provider=config.get("provider", "ollama"),
                llm_endpoint=DEFAULT_OLLAMA_ENDPOINT,
                llm_model=default_model,
                llm_timeout=30,
                llm_temperature=0.7,
                llm_max_tokens=None,
                is_default=(agent_id == "orchestrator"),
                is_active=config.get("enabled", True),
            )
            db.add(agent)
            created_count += 1
            logger.info("Created agent: %s (%s)", agent_id, config["name"])

        await db.commit()
        logger.info(
            "Seed complete: %d created, %d skipped", created_count, skipped_count
        )

    await db_service.close()
    return True


if __name__ == "__main__":
    success = asyncio.run(seed_agents())
    sys.exit(0 if success else 1)
