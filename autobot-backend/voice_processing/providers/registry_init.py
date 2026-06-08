# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Provider Registry Initialization

Register all speech providers on startup.
Part of Issue MVA-2185.
"""

from autobot_shared.logging_manager import get_logger
from voice_processing.providers import get_speech_provider_registry
from voice_processing.providers.generic_provider import GenericProvider
from voice_processing.providers.lv.late_provider import LateProvider
from voice_processing.providers.lv.tilde_provider import TildeProvider

logger = get_logger(__name__)


def initialize_providers():
    """Register all speech providers.

    Priority system:
    - Higher priority = tried first
    - LATE (priority 10) > Tilde (priority 5) for Latvian
    - Generic provider is fallback for all languages (priority 0)
    """
    registry = get_speech_provider_registry()

    # Register Latvian providers
    late = LateProvider()
    registry.register("lv", late, priority=10)  # Primary for Latvian
    registry.register("lat", late, priority=10)  # ISO 639-2 code

    tilde = TildeProvider()
    registry.register("lv", tilde, priority=5)  # Fallback for Latvian
    registry.register("lat", tilde, priority=5)

    # Register generic provider for common languages
    generic = GenericProvider()
    for lang in generic.supported_languages:
        registry.register(lang, generic, priority=0)

    # Also register generic as lowest-priority fallback for Latvian
    # (in case both LATE and Tilde fail)
    registry.register("lv", generic, priority=-10)
    registry.register("lat", generic, priority=-10)

    logger.info("Speech providers initialized: " "LATE (lv), Tilde (lv), Generic (en, de, es, fr, ...)")


# Auto-initialize on import
# This ensures providers are registered when the module is imported
initialize_providers()
