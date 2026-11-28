# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The SSOT value at a ``section.field`` key, readable when a sibling setting is unusable (#19232, #19325)."""

from functools import reduce
from typing import Any

from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)


def ssot_value(key: str) -> str:
    """The value at *key* in the process SSOT config, as a string.

    One unusable setting elsewhere in the environment (a bad ``REDIS_PORT`` in the misc
    section, a bad TLS port, an undeterminable project root) fails the whole ``AutoBotConfig``.
    The value is then read from its own section, which that setting does not touch, so a port
    stays answerable and a Redis client can still fall through to its next tier.
    """
    from autobot_shared.ssot_config import AutoBotConfig, get_config

    try:
        return str(reduce(getattr, key.split("."), get_config()))
    except Exception as exc:  # a pydantic ValidationError or ProjectRootUndeterminable from a sibling section
        logger.warning("SSOT config unusable (%s); reading %s from its own section", type(exc).__name__, key)
        section, field = key.split(".")
        section_type: Any = AutoBotConfig.model_fields[section].annotation
        return str(getattr(section_type(), field))
