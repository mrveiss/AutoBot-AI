# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Integration tests for the openai_compat rate-limit wiring (#7271).

Per-IP rate-limit logic itself lives in
``autobot_shared.rate_limit.IPRateLimiter`` and is comprehensively tested
in ``autobot_shared/rate_limit_test.py`` (covers Redis path, in-process
fallback, env-driven limit, etc.).

This file pins the openai_compat-specific configuration of that helper:
the right key prefix, the right env var, and that the helper is the same
instance referenced by the request handler.

Pre-#7271 this file tested the standalone ``_check_oai_rate_limit``
function shipped in #6588. That function was extracted into the shared
helper, so the tests are now at the helper-level and the integration
tests below pin the per-endpoint configuration.
"""

from api import openai_compat
from autobot_shared.rate_limit import IPRateLimiter


class TestOAIRateLimitWiring:
    """Issue #7271: openai_compat uses the shared IPRateLimiter."""

    def test_module_exposes_limiter_instance(self):
        """``_oai_limiter`` must be an IPRateLimiter (not the legacy func)."""
        assert isinstance(openai_compat._oai_limiter, IPRateLimiter)

    def test_limiter_uses_oai_specific_config(self):
        """The instance is configured for the /v1/chat/completions endpoint."""
        limiter = openai_compat._oai_limiter
        # #6588 / #7271: prefix shared across uvicorn workers via Redis key.
        assert limiter._key_prefix == "ratelimit:oai"
        # AUTOBOT_OAI_RATE_LIMIT env var; default 60/min preserved.
        assert limiter._limit_env == "AUTOBOT_OAI_RATE_LIMIT"
        assert limiter._default_limit == 60
        assert limiter._window_seconds == 60
