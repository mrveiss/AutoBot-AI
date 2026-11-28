# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The one provider the chat route's registry requests name (#21023, #20846).

``llm_failover`` and ``planner_client`` both build registry requests for the turn's selected model. They
read the provider from the SSOT (``config.llm.provider``, ``AUTOBOT_LLM_PROVIDER``) here, so neither
hardcodes one and a deployment that switches provider switches both.
"""

from __future__ import annotations

from autobot_shared.ssot_config import config
from llm_shared.types import ProviderType


def configured_provider() -> ProviderType:
    """The SSOT provider as a ``ProviderType``; a name the registry does not know raises ``ValueError``."""
    return ProviderType(str(config.llm.provider).strip().lower())
