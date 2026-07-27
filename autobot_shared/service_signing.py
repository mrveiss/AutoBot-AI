# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Canonical service-to-service request signing.

Holds the HMAC-SHA256 signature formula shared by the caller side
(``autobot_shared.http_client.sign_request``) and the receiver side
(``security.service_auth.ServiceAuthManager.generate_signature``).

This module depends on nothing but the standard library. That is its
reason to exist: the formula previously lived in
:mod:`autobot_shared.http_client`, which imports ``aiohttp`` at module
level, so every consumer of a pure crypto helper inherited a transport
dependency it never used. Any environment able to verify a signature —
a migration gate, a slim worker, a test job — can now import the helper
without an HTTP stack.
"""

import hashlib
import hmac


def _service_signature(
    service_id: str,
    method: str,
    path: str,
    timestamp: int,
    key: str,
) -> str:
    """
    Canonical HMAC-SHA256 signature for service-to-service requests (#12766).

    Single source of truth for the signature computation shared by
    ``autobot_shared.http_client.sign_request`` (caller side) and
    ``security.service_auth.ServiceAuthManager.generate_signature``
    (receiver side, ``autobot-backend``) — the two previously duplicated an
    identical ``hmac.new(key, "service_id:method:path:timestamp", sha256)``
    formula. Extracting one helper guarantees they can never silently drift.

    SECURITY: the message format, field order, ``:`` separator, UTF-8
    encoding, and SHA-256 digest MUST NOT change — any edit here changes
    every signature this system has ever produced or verified.

    Args:
        service_id: Caller's service identifier (e.g. ``'main-backend'``).
        method: HTTP method in upper-case (e.g. ``'GET'``, ``'POST'``).
        path: URL path component only (e.g. ``'/api/inference'``).
        timestamp: Unix timestamp (seconds).
        key: 256-bit hex-encoded secret shared between caller and receiver.

    Returns:
        Hex-encoded HMAC-SHA256 signature.
    """
    message = f"{service_id}:{method}:{path}:{timestamp}"
    return hmac.new(
        key.encode(encoding="utf-8"),
        message.encode(encoding="utf-8"),
        hashlib.sha256,
    ).hexdigest()


__all__ = ["_service_signature"]
