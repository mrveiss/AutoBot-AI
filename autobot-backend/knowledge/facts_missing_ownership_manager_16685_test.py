# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Storing and deleting a fact degrade, not crash, without an ownership manager (#16685).

``KnowledgeBase`` sets ``ownership_manager = None`` until it is initialised, so the old
``hasattr(self, "ownership_manager")`` checks were always true. Storing then called
``index_ownership(None, ...)`` and deleting called ``None.cleanup_ownership_indexes``, and
both crashed. The #689 fallback never ran. These tests drive the two steps that carry the
check: the store path's Redis projection, and the delete path's mapping cleanup.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from knowledge.facts import FactsMixin


class _KB(FactsMixin):
    """A FactsMixin host whose ownership manager was never initialised."""

    def __init__(self):
        self.redis_client = MagicMock()
        self.ownership_manager = None


@pytest.mark.asyncio
async def test_storing_an_owned_fact_falls_back_to_the_simple_owner_index():
    kb = _KB()

    await kb._project_fact_to_redis("f1", "content", {"owner_id": "u1", "visibility": "private"})

    kb.redis_client.sadd.assert_any_call("user:facts:u1", "f1")  # the #689 fallback


@pytest.mark.asyncio
async def test_deleting_a_fact_skips_the_ownership_cleanup_instead_of_crashing():
    kb = _KB()

    await kb._cleanup_fact_mappings("f1", "content", {"owner_id": "u1", "visibility": "private"})

    kb.redis_client.delete.assert_any_call("fact:origin:session:f1")  # the rest of the cleanup still ran
