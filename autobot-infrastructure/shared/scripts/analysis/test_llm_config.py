#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Check LLM configuration to see what models are being used
"""

import logging
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

logger = logging.getLogger(__name__)

# #14518: the path insert here pointed at a ``src`` directory that does not
# exist beside this script, and ``llm_interface`` is a pre-restructure module
# name. The canonical entry point is services.llm_service.get_llm_service (#18552). Add
# autobot-backend the way the other operator entry points in this tree do
# (#14129).
# A backend tool (#18289): it also puts the repository root on the path (for `autobot_shared`), so it
# runs from any directory with no PYTHONPATH.
_REPO_ROOT = Path(__file__).resolve().parents[4]
for _root in (_REPO_ROOT / "autobot-backend", _REPO_ROOT):
    if str(_root) not in sys.path:
        sys.path.insert(0, str(_root))

import config as config  # noqa: E402
from services.llm_service import get_llm_service  # noqa: E402


def check_llm_config():
    """Check LLM configuration"""
    logger.info("🔧 Checking LLM Configuration...")

    try:
        # Get config
        global_config = config.config

        # Print relevant config sections
        logger.info("\n📋 Global LLM Config:")
        llm_config = global_config.get_nested("llm_config", {})
        for key, value in llm_config.items():
            logger.info("   %s: %s", key, value)

        # Check unified LLM config
        logger.info("\n🔗 Unified LLM Config:")
        unified_config = global_config.get_nested("unified_llm_config", {})
        for key, value in unified_config.items():
            logger.info("   %s: %s", key, value)

        # Create LLM interface and check its settings
        logger.info("\n🤖 LLM Service Settings:")
        stats = get_llm_service().get_stats()

        for key, value in stats.items():
            logger.info("   %s: %s", key, value)

        return True

    except Exception as e:
        logger.error("❌ Config check failed: %s", e)
        import traceback

        traceback.print_exc()
        return False


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    check_llm_config()
