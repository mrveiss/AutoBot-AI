# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Active cloud ASR provider selection (Issue #10147).

Reads TRANSCRIBER_ASR_PROVIDER (deepgram | assemblyai | google | unset) to
determine which cloud provider is preferred.  A provider is only offered when
its API key / credentials are present in the environment.

Active-provider persistence: the value is stored in app state
(FastAPI request.app.state.transcriber_asr_provider) at runtime.  On restart
the env var is the source of truth.  This is documented as a limitation — no
heavy settings store is needed for the initial implementation.
"""

import os
from typing import Any, Dict, List, Optional

from autobot_shared.logging_manager import get_logger
from voice_processing.providers.cloud.assemblyai_provider import AssemblyAIProvider
from voice_processing.providers.cloud.deepgram_provider import DeepgramProvider
from voice_processing.providers.cloud.google_provider import GoogleSpeechProvider

logger = get_logger(__name__)

# Module-level runtime override (survives in-process PATCH; reset on restart)
_active_provider_override: Optional[str] = None

_PROVIDER_MAP = {
    "deepgram": DeepgramProvider,
    "assemblyai": AssemblyAIProvider,
    "google": GoogleSpeechProvider,
}


def _env_selected() -> Optional[str]:
    """Return the value of TRANSCRIBER_ASR_PROVIDER, lower-cased, or None."""
    raw = os.environ.get("TRANSCRIBER_ASR_PROVIDER", "").strip().lower()
    return raw or None


def get_active_provider_id() -> Optional[str]:
    """Return the currently active provider id (override > env > None)."""
    return _active_provider_override or _env_selected()


def set_active_provider(provider_id: Optional[str]) -> None:
    """Set the in-process active-provider override.

    Limitation: this is process-local and lost on restart.  Configure
    TRANSCRIBER_ASR_PROVIDER in the environment for persistence.
    """
    global _active_provider_override
    if provider_id and provider_id not in _PROVIDER_MAP:
        raise ValueError(f"Unknown provider: {provider_id!r}. Valid: {list(_PROVIDER_MAP)}")
    _active_provider_override = provider_id
    logger.info("Active cloud ASR provider set to: %s", provider_id or "(none)")


def list_available_providers() -> List[Dict[str, Any]]:
    """Return metadata for all cloud providers, regardless of configuration.

    Each entry: {id, name, configured, languages}
    """
    result = []
    for pid, cls in _PROVIDER_MAP.items():
        instance = cls()
        result.append(
            {
                "id": pid,
                "name": instance.provider_name,
                "configured": instance.is_configured,
                "languages": instance.supported_languages,
            }
        )
    return result


def get_selected_cloud_provider() -> Optional[Any]:
    """Return an instance of the selected + configured cloud provider, or None."""
    pid = get_active_provider_id()
    if pid is None:
        return None
    cls = _PROVIDER_MAP.get(pid)
    if cls is None:
        logger.warning("TRANSCRIBER_ASR_PROVIDER=%r is not a known provider id", pid)
        return None
    instance = cls()
    if not instance.is_configured:
        logger.warning("Selected cloud provider %r is not configured (missing API key)", pid)
        return None
    return instance
