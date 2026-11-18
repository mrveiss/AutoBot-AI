# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The one constant-time secret comparison (#20761).

``hmac.compare_digest`` / ``secrets.compare_digest`` raise ``TypeError`` when
given a ``str`` holding a non-ASCII character, so a hostile header turned a
refusal into a 500. Every secret, token, key or signature comparison goes
through :func:`secure_compare`, which compares UTF-8 bytes and never raises.
"""

import hmac


def _as_bytes(value: str | bytes | None) -> bytes | None:
    """UTF-8 bytes of ``value``; None for a missing, empty or non-text value."""
    if isinstance(value, str):
        value = value.encode("utf-8", errors="surrogatepass")
    if isinstance(value, (bytes, bytearray)) and value:
        return bytes(value)
    return None


def secure_compare(provided: str | bytes | None, expected: str | bytes | None) -> bool:
    """Constant-time equality of two secrets; False on anything missing or unequal.

    Fails closed: ``None``, an empty value or a non-text value on either side is
    never a match (two empties do not authenticate each other). Never raises.
    """
    left, right = _as_bytes(provided), _as_bytes(expected)
    if left is None or right is None:
        return False
    return hmac.compare_digest(left, right)
