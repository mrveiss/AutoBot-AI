# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The one place a test secrets root key is generated (#17219)."""

import base64
import secrets


def fresh_root_key() -> str:
    """A new random 32-byte root key, url-safe base64 -- what ``load_root_key`` parses."""
    return base64.urlsafe_b64encode(secrets.token_bytes(32)).decode("ascii")
