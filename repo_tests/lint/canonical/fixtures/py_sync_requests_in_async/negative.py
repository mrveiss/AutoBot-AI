# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Negative fixture: async path uses an async client; sync path is fine."""

import requests


async def fetch(session):
    async with session.get("http://example.com") as resp:
        return await resp.text()


def sync_fetch():
    return requests.get("http://example.com")
