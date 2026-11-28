# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""One ``log_initialization_step``, and a wrapper named for what it does (#18459).

``background_tasks`` carried a byte-identical copy of ``ai_stack_init``'s
helper and a ``get_or_create_knowledge_base`` that, unlike the factory function
of the same name, swallows every error and returns ``None``.
"""

import ast
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from initialization import ai_stack_init, background_tasks


def test_background_tasks_binds_the_ai_stack_helper_it_used_to_copy():
    assert background_tasks.log_initialization_step is ai_stack_init.log_initialization_step


def test_background_tasks_defines_no_second_copy():
    tree = ast.parse(Path(background_tasks.__file__).read_text(encoding="utf-8"))
    defined = {n.name for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))}
    assert "log_initialization_step" not in defined
    assert "get_or_create_knowledge_base" not in defined


@pytest.mark.asyncio
async def test_the_wrapper_returns_none_where_the_factory_would_raise():
    with patch("knowledge_factory.get_or_create_knowledge_base", new=AsyncMock(side_effect=RuntimeError("down"))):
        assert await background_tasks.get_or_create_knowledge_base_or_none(object()) is None
