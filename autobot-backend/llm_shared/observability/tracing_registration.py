# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Register the optional LangFuse / LangSmith observers (#19933).

Tracing is optional: nothing here may stop ``import llm_shared``. Every failure -- policy,
config, a missing client package -- registers no observer and logs a warning naming the
exception type only (a message could carry a key).

Called at import because workers and CLI processes use ``llm_shared`` without the app lifespan.
The only blocking step is the DNS lookup in ``is_public_url`` (2 s bound), and it runs only for an
unlisted destination with ``AUTOBOT_LLM_TRACING_ALLOW_EXTERNAL`` on.
"""

from __future__ import annotations

from autobot_shared.logging_manager import get_logger

from .langfuse_observer import LangFuseObserver
from .langsmith_observer import LangSmithObserver
from .registry import register
from .tracing_config import LangFuseTracingConfig, LangSmithTracingConfig
from .tracing_policy import destination_allowed

logger = get_logger(__name__)


def _register_one(service: str, config_cls, observer_cls, url_attr: str) -> None:
    try:
        cfg = config_cls()
        if cfg.enabled and destination_allowed(service, getattr(cfg, url_attr)):
            register(observer_cls(cfg))
    except Exception as exc:  # noqa: BLE001 -- optional tracing must never stop the app
        logger.warning("LLM tracing for %s not registered (%s)", service, type(exc).__name__)


def register_tracing_observers() -> None:
    """Register each enabled tracing observer whose destination passes the policy."""
    _register_one("langfuse", LangFuseTracingConfig, LangFuseObserver, "host")
    _register_one("langsmith", LangSmithTracingConfig, LangSmithObserver, "api_url")
