# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Positive fixture: blocking requests.get inside async def (one violation).

The sync function below uses requests too, but must NOT be flagged.
"""

import requests


async def fetch():
    return requests.get("http://example.com")


def sync_fetch():
    return requests.get("http://example.com")
