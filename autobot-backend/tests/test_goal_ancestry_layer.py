# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
"""Tests for Layer4GoalAncestry and TieredContextBuilder.build() L4 path (GH#6469).

Imports layers.py directly via importlib to avoid the chat_history package
__init__.py import chain which has heavier dependencies (session, Redis, etc.).
"""

import importlib.util
import sys
import types
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ----------------------------------------------------------------- Helpers


def _load_layers_module():
    """Load chat_history/layers.py without triggering chat_history/__init__.py."""
    layers_path = Path(__file__).parent.parent / "chat_history" / "layers.py"

    # Provide a minimal stub for autobot_shared.logging_manager so the
    # module-level ``logger = get_logger(__name__)`` succeeds.
    import logging

    if "autobot_shared.logging_manager" not in sys.modules:
        stub = types.ModuleType("autobot_shared.logging_manager")
        stub.get_logger = lambda name, *a, **kw: logging.getLogger(name)  # type: ignore[attr-defined]
        sys.modules["autobot_shared.logging_manager"] = stub

    # Provide a minimal stub for autobot_shared.ssot_config / config so that
    # ``TIERED_CONTEXT_ENABLED = config.tiered_context_enabled.lower() == "true"``
    # resolves to False at import time.
    # conftest.py imports `from autobot_shared.ssot_config import config` before
    # test collection, so sys.modules["autobot_shared.ssot_config"] is already
    # populated with the real module — the if-not-in guard would never fire.
    # Unconditionally patch the attribute on whatever config object is present.
    import autobot_shared.ssot_config as _ssot_cfg_mod

    _ssot_cfg_mod.config.tiered_context_enabled = "false"  # type: ignore[attr-defined]

    spec = importlib.util.spec_from_file_location("chat_history.layers", layers_path)
    module = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


_layers = _load_layers_module()
Layer4GoalAncestry = _layers.Layer4GoalAncestry
TieredContextBuilder = _layers.TieredContextBuilder


# ----------------------------------------------------------------- Layer4


class TestLayer4GoalAncestry:
    @pytest.mark.asyncio
    async def test_should_load_false_when_none(self):
        layer = Layer4GoalAncestry()
        assert await layer.should_load(None) is False

    @pytest.mark.asyncio
    async def test_should_load_false_when_empty(self):
        layer = Layer4GoalAncestry()
        assert await layer.should_load([]) is False

    @pytest.mark.asyncio
    async def test_should_load_true_when_populated(self):
        layer = Layer4GoalAncestry()
        assert await layer.should_load([{"title": "Vision", "level": "vision"}]) is True

    @pytest.mark.asyncio
    async def test_render_empty_ancestry(self):
        layer = Layer4GoalAncestry()
        result = await layer.render({"goal_ancestry": []})
        assert result == ""

    @pytest.mark.asyncio
    async def test_render_none_ancestry(self):
        layer = Layer4GoalAncestry()
        result = await layer.render({"goal_ancestry": None})
        assert result == ""

    @pytest.mark.asyncio
    async def test_render_single_goal(self):
        layer = Layer4GoalAncestry()
        ancestry = [{"title": "Company Vision", "level": "vision"}]
        result = await layer.render({"goal_ancestry": ancestry})
        assert "## Goal Ancestry" in result
        assert "Vision: Company Vision" in result

    @pytest.mark.asyncio
    async def test_render_full_chain(self):
        layer = Layer4GoalAncestry()
        ancestry = [
            {"title": "Company Vision", "level": "vision"},
            {"title": "Q1 Mission", "level": "mission"},
            {"title": "Ship Feature X", "level": "objective"},
        ]
        result = await layer.render({"goal_ancestry": ancestry})
        assert "Vision: Company Vision" in result
        assert "Mission: Q1 Mission" in result
        assert "Objective: Ship Feature X" in result
        assert "→" in result

    @pytest.mark.asyncio
    async def test_token_estimate(self):
        layer = Layer4GoalAncestry()
        assert await layer.token_estimate({}) == 200


# ----------------------------------------------------------------- TieredContextBuilder L4


class TestTieredContextBuilderL4:
    @pytest.mark.asyncio
    async def test_build_skips_all_when_flag_disabled(self):
        """Flag off → empty string regardless of goal_ancestry."""
        _layers.TIERED_CONTEXT_ENABLED = False
        builder = TieredContextBuilder()
        result = await builder.build(
            user_message="hello",
            model_name="default",
            session_id="sess-1",
            goal_ancestry=[{"title": "Vision", "level": "vision"}],
        )
        assert result == ""

    @pytest.mark.asyncio
    async def test_build_includes_l4_when_ancestry_present(self):
        """When flag is on and goal_ancestry is set, L4 text appears in output."""
        _layers.TIERED_CONTEXT_ENABLED = True
        ancestry = [{"title": "Q1 Goal", "level": "objective"}]
        builder = TieredContextBuilder()

        with (
            patch.object(_layers.Layer0Identity, "render", new=AsyncMock(return_value="")),
            patch.object(_layers.Layer1EssentialStory, "render", new=AsyncMock(return_value="")),
            patch.object(
                _layers.Layer1EssentialStory,
                "token_estimate",
                new=AsyncMock(return_value=600),
            ),
        ):
            result = await builder.build(
                user_message="do work",
                model_name="default",
                session_id="sess-2",
                goal_ancestry=ancestry,
            )

        assert "Goal Ancestry" in result
        assert "Q1 Goal" in result

    @pytest.mark.asyncio
    async def test_build_omits_l4_when_ancestry_absent(self):
        """When goal_ancestry is absent, L4 section is not in output."""
        _layers.TIERED_CONTEXT_ENABLED = True
        builder = TieredContextBuilder()
        with (
            patch.object(_layers.Layer0Identity, "render", new=AsyncMock(return_value="")),
            patch.object(_layers.Layer1EssentialStory, "render", new=AsyncMock(return_value="")),
            patch.object(
                _layers.Layer1EssentialStory,
                "token_estimate",
                new=AsyncMock(return_value=600),
            ),
        ):
            result = await builder.build(
                user_message="do work",
                model_name="default",
                session_id="sess-3",
            )

        assert "Goal Ancestry" not in result
