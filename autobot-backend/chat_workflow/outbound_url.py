# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Outbound URL normalization for the LLM request path.

Extracted from llm_handler.py (#16930 review, to keep it under its
file-size ceiling) -- a move, not a behaviour change.
"""

# Issue #380: Module-level tuple for URL scheme validation
_VALID_URL_SCHEMES = ("http://", "https://")


def _normalize_outbound_url(url: str) -> str:
    """Rewrite a 0.0.0.0 bind-address host to 127.0.0.1 for outbound calls.

    Bug fix: the Ollama endpoint is sometimes configured as
    ``http://0.0.0.0:11434`` (a server *bind* address — "all interfaces").
    0.0.0.0 is not a valid *connect* target, so an outbound client request to
    it raises aiohttp.ClientError, the LLM call fails, and no assistant reply is
    produced. Normalize it to loopback so the call reaches a locally-bound
    Ollama. No-op for any other host.
    """
    if not url:
        return url
    return url.replace("//0.0.0.0:", "//127.0.0.1:").replace("//0.0.0.0/", "//127.0.0.1/")
