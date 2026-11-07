# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Shared HMAC-SHA256 webhook signature verification (#18452).

GitHub (``X-Hub-Signature-256``) and Meta/WhatsApp (``X-Hub-Signature-256``)
both sign the raw request body as ``sha256=<hex>`` using a shared secret. This
is the single verifier for that scheme; callers must not re-implement it.
"""

import hashlib
import hmac
from typing import Optional

_SIGNATURE_PREFIX = "sha256="


def verify_webhook_signature(payload: bytes, signature_header: Optional[str], secret: str) -> bool:
    """Verify a ``sha256=<hex>`` HMAC over the raw request body.

    Fails closed: a missing/malformed header or an absent secret yields False.
    Comparison is timing-safe.
    """
    if not secret or not signature_header:
        return False
    if not signature_header.startswith(_SIGNATURE_PREFIX):
        return False
    provided = signature_header[len(_SIGNATURE_PREFIX) :]
    expected = hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()
    try:
        return hmac.compare_digest(provided.encode("utf-8"), expected.encode("ascii"))
    except (UnicodeError, TypeError):
        return False
