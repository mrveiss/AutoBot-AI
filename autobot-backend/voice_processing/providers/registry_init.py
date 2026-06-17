# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Provider Registry Initialization

Register all speech providers on startup.
Part of Issue MVA-2185, Issue #10147.
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
    - Cloud providers (priority 20) override local when selected + configured
    - LATE (priority 10) > Tilde (priority 5) for Latvian
    - Generic provider is fallback for all languages (priority 0)

    Cloud providers are credential-gated: only registered when API key present.
    Never crashes startup — each cloud registration is wrapped in try/except.
    """
    registry = get_speech_provider_registry()

    # ── Cloud providers (Issue #10147) ────────────────────────────────────────
    # Import selection module to discover which provider (if any) is active.
    from voice_processing.providers.selection import _PROVIDER_MAP, get_active_provider_id

    active_cloud_id = get_active_provider_id()

    for provider_id, provider_cls in _PROVIDER_MAP.items():
        try:
            instance = provider_cls()
            if not instance.is_configured:
                logger.info(
                    "Cloud provider %r not configured (no API key) — skipping registration",
                    provider_id,
                )
                continue
            # Selected provider gets highest priority so get_provider() returns it first
            priority = 20 if provider_id == active_cloud_id else 15
            for lang in instance.supported_languages:
                registry.register(lang, instance, priority=priority)
            logger.info(
                "Registered cloud provider %r for %d languages (priority=%d)",
                instance.provider_name,
                len(instance.supported_languages),
                priority,
            )
        except Exception as exc:
            logger.error("Failed to register cloud provider %r: %s", provider_id, exc)

    # ── Latvian providers ─────────────────────────────────────────────────────
    late = LateProvider()
    registry.register("lv", late, priority=10)  # Primary for Latvian
    registry.register("lat", late, priority=10)  # ISO 639-2 code

    tilde = TildeProvider()
    registry.register("lv", tilde, priority=5)  # Fallback for Latvian
    registry.register("lat", tilde, priority=5)

    # ── Generic fallback ──────────────────────────────────────────────────────
    generic = GenericProvider()
    for lang in generic.supported_languages:
        registry.register(lang, generic, priority=0)

    # Also register generic as lowest-priority fallback for Latvian
    registry.register("lv", generic, priority=-10)
    registry.register("lat", generic, priority=-10)

    logger.info("Speech providers initialized: cloud (if configured), LATE (lv), Tilde (lv), Generic (...)")


# Auto-initialize on import
initialize_providers()
