# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Coverage for the ``category`` defaults in ``SystemKnowledgeManager``'s
``_import_single_tool`` / ``_import_single_workflow`` (#14047)."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from agents.system_knowledge_manager import SystemKnowledgeManager
from constants.threshold_constants import CategoryDefaults


def _manager():
    manager = SystemKnowledgeManager(MagicMock())
    manager.librarian = MagicMock()
    manager.librarian.store_tool_knowledge = AsyncMock()
    manager.librarian.store_workflow_knowledge = AsyncMock()
    return manager


@pytest.mark.asyncio
async def test_import_single_tool_missing_type_defaults_category_to_general():
    manager = _manager()

    await manager._import_single_tool({"name": "curl"})

    tool_info = manager.librarian.store_tool_knowledge.call_args[0][0]
    assert tool_info["category"] == CategoryDefaults.GENERAL


@pytest.mark.asyncio
async def test_import_single_tool_explicit_type_overrides_category_default():
    manager = _manager()

    await manager._import_single_tool({"name": "curl", "type": "network"})

    tool_info = manager.librarian.store_tool_knowledge.call_args[0][0]
    assert tool_info["category"] == "network"


@pytest.mark.asyncio
async def test_import_single_workflow_missing_category_defaults_to_general():
    manager = _manager()

    await manager._import_single_workflow({"metadata": {"name": "Deploy"}})

    workflow_info = manager.librarian.store_workflow_knowledge.call_args[0][0]
    assert workflow_info["type"] == CategoryDefaults.GENERAL


@pytest.mark.asyncio
async def test_import_single_workflow_explicit_category_overrides_default():
    manager = _manager()

    await manager._import_single_workflow({"metadata": {"name": "Deploy", "category": "ops"}})

    workflow_info = manager.librarian.store_workflow_knowledge.call_args[0][0]
    assert workflow_info["type"] == "ops"
