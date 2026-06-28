# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Waiver fixture: explicitly waived blocking call on an async path."""

import requests


async def fetch():
    return requests.get("http://example.com")  # canonical: ignore py-sync-requests-in-async
