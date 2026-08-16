#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Agent Seed Migration (Issue #760 Phase 3, #14321)

Seeds the SLM `agents` table with the canonical AutoBot agent roster from
services/agent_seeder.py -- the same SEED_AGENT_CONFIGS list main.py's
startup lifespan seeds with on every boot (see main.py::_seed_default_agents),
so this migration and the runtime seeder can never drift apart.

#14321: this used to define its own seed logic around an async
`seed_agents()` function that imported `backend.api.agent_config` -- a
cross-codebase module path that was never resolvable from this package (the
top-level directory is `autobot-backend`, not `backend`) -- and, because the
migrations runner only invokes a module-level `migrate()`/`run()`, that
function was never even called. The runner recorded `seed_agents` as
applied anyway, so the seeding never happened via this path. This exposes
the `migrate(db_url)` entry point the runner looks for and reuses the
already-canonical roster instead of forking a second copy of it.

Usage:
    cd <autobot-root>/autobot-slm-backend
    python -m migrations.seed_agents
"""

import logging
import sys

from migrations import utils as _migration_utils
from migrations.utils import get_connection, table_exists

logger = logging.getLogger(__name__)


def migrate(db_url: str) -> None:
    """Seed `agents` from SEED_AGENT_CONFIGS (#14321).

    Idempotent: ON CONFLICT (agent_id) DO NOTHING skips agents that already
    exist, matching services.agent_seeder.seed_default_agents (the async
    version main.py runs on every startup).
    """
    from autobot_shared.ssot_config import config as _ssot_config

    # #14321: read the roster from its leaf module, NOT via
    # services.agent_seeder — services/__init__.py eagerly imports .auth /
    # .deployment / .reconciler, so that route drags FastAPI into the
    # migration runner and fails the gate with No module named 'fastapi'.
    from models.agent_seed_roster import SEED_AGENT_CONFIGS

    ollama_endpoint = _ssot_config.llm.ollama_endpoint

    conn = get_connection(db_url)
    cursor = conn.cursor()

    try:
        if not table_exists(cursor, "agents"):
            # add_agents (immediately before this entry in runner.MIGRATIONS)
            # always creates this table first; defer rather than crash so a
            # future run retries if that invariant is ever violated (#14300).
            _migration_utils.defer("agents")
            logger.warning("Deferring seed_agents: agents table does not exist yet")
            return

        created = 0
        for cfg in SEED_AGENT_CONFIGS:
            cursor.execute(
                """
                INSERT INTO agents (
                    agent_id, name, description, llm_provider, llm_endpoint,
                    llm_model, llm_timeout, llm_temperature, llm_max_tokens,
                    is_default, is_active
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (agent_id) DO NOTHING
                """,
                (
                    cfg["agent_id"],
                    cfg["name"],
                    cfg["description"],
                    "ollama",
                    ollama_endpoint,
                    cfg["llm_model"],
                    30,
                    0.7,
                    None,
                    cfg["is_default"],
                    cfg["is_active"],
                ),
            )
            if cursor.rowcount:
                created += 1

        conn.commit()
        logger.info(
            "seed_agents: %d agent(s) created, %d already present",
            created,
            len(SEED_AGENT_CONFIGS) - created,
        )
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    from migrations.runner import get_db_url

    migrate(sys.argv[1] if len(sys.argv) > 1 else get_db_url())
    sys.exit(0)
