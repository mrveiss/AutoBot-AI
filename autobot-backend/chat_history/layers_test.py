# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for the tiered L0-L3 context wake-up stack (#5066)."""

import importlib
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _reload_layers(tiered_enabled: bool = False):
    """Reload the layers module with a specific env-var value."""
    with patch.dict("os.environ", {"TIERED_CONTEXT_ENABLED": "true" if tiered_enabled else "false"}):
        if "chat_history.layers" in sys.modules:
            del sys.modules["chat_history.layers"]
        import chat_history.layers as mod

        importlib.reload(mod)
        return mod


# ---------------------------------------------------------------------------
# Layer0Identity tests
# ---------------------------------------------------------------------------


class TestLayer0Identity:
    @pytest.mark.asyncio
    async def test_render_returns_identity_block(self):
        from chat_history.layers import Layer0Identity

        layer = Layer0Identity()
        result = await layer.render({})
        assert "## Identity" in result
        assert "Role" in result
        assert "Owner" in result

    @pytest.mark.asyncio
    async def test_token_estimate_is_100(self):
        from chat_history.layers import Layer0Identity

        layer = Layer0Identity()
        est = await layer.token_estimate({})
        assert est == 100

    @pytest.mark.asyncio
    async def test_render_never_raises_on_missing_config(self):
        """render() must swallow any import error and return a safe default."""
        from chat_history.layers import Layer0Identity

        with patch.dict("sys.modules", {"autobot_shared.ssot_config": None}):
            layer = Layer0Identity()
            result = await layer.render({})
            # Should return something, not raise
            assert isinstance(result, str)


# ---------------------------------------------------------------------------
# Layer1EssentialStory tests
# ---------------------------------------------------------------------------


class TestLayer1EssentialStory:
    @pytest.mark.asyncio
    async def test_render_delegates_to_essential_story_generator(self):
        from chat_history.layers import Layer1EssentialStory

        mock_gen = MagicMock()
        mock_gen.generate = AsyncMock(return_value="## Essential Context\n[general] fact1")
        with patch("memory.essential_story.EssentialStoryGenerator", return_value=mock_gen):
            layer = Layer1EssentialStory()
            result = await layer.render({"model_name": "test-model"})
            assert isinstance(result, str)
            assert result == "## Essential Context\n[general] fact1"
            mock_gen.generate.assert_awaited_once_with("test-model")

    @pytest.mark.asyncio
    async def test_render_returns_empty_on_generator_failure(self):
        from chat_history.layers import Layer1EssentialStory

        with patch(
            "memory.essential_story.EssentialStoryGenerator",
            side_effect=ImportError("no module"),
        ):
            layer = Layer1EssentialStory()
            result = await layer.render({"model_name": "test-model"})
            assert result == ""

    @pytest.mark.asyncio
    async def test_token_estimate_within_reasonable_range(self):
        from chat_history.layers import Layer1EssentialStory

        layer = Layer1EssentialStory()
        est = await layer.token_estimate({"model_name": "default"})
        # Must be between 300 and 800 inclusive
        assert 300 <= est <= 800


# ---------------------------------------------------------------------------
# L0 + L1 combined token budget acceptance criterion
# ---------------------------------------------------------------------------


class TestL0L1CombinedBudget:
    """#13691: this class used to assert the estimates were `<= 900`.

    That was the test recording the acceptance criterion as met on the strength
    of a constant that only logged — the exact thing #13691 was filed about. The
    flat 900 is gone, and the layers' own `token_estimate` values are now the
    per-model *targets* the allocator caps against, so what matters is that they
    are usable as a budget input rather than that they fall under a magic number.
    """

    @pytest.mark.asyncio
    async def test_token_estimates_are_positive_and_per_model(self):
        from chat_history.layers import Layer0Identity, Layer1EssentialStory

        default_ctx: dict = {"model_name": "default"}
        l0_est = await Layer0Identity().token_estimate(default_ctx)
        l1_est = await Layer1EssentialStory().token_estimate(default_ctx)

        assert l0_est > 0 and l1_est > 0, "a zero target would make max_share undefined"

    @pytest.mark.asyncio
    async def test_the_flat_900_budget_is_gone(self):
        """The constant, and any assertion resting on it, must not come back."""
        from chat_history.layers import TieredContextBuilder

        assert not hasattr(TieredContextBuilder, "_L0_L1_MAX_TOKENS")


# ---------------------------------------------------------------------------
# Layer2OnDemand tests
# ---------------------------------------------------------------------------


class TestLayer2OnDemand:
    @pytest.mark.asyncio
    async def test_should_load_true_on_entity_message(self):
        from chat_history.layers import Layer2OnDemand

        layer = Layer2OnDemand()
        assert await layer.should_load("Tell me about AutoBot and Redis")

    @pytest.mark.asyncio
    async def test_should_load_false_on_generic_message(self):
        from chat_history.layers import Layer2OnDemand

        layer = Layer2OnDemand()
        # No uppercase tokens beyond the start of sentence
        assert not await layer.should_load("hello, how are you?")

    @pytest.mark.asyncio
    async def test_render_returns_empty_without_memory_graph(self):
        from chat_history.layers import Layer2OnDemand

        layer = Layer2OnDemand()
        result = await layer.render({"user_message": "Tell me about AutoBot", "memory_graph": None})
        assert result == ""

    @pytest.mark.asyncio
    async def test_render_with_memory_graph_returns_context(self):
        from autobot_memory_graph.entities import EntityOperationsMixin
        from chat_history.layers import Layer2OnDemand

        # Built by the function that defines the schema, not hand-written: the
        # hand-written fixture agreed with the layer's own wrong assumption.
        fake_graph = MagicMock()
        fake_graph.search_entities = AsyncMock(
            return_value=[
                EntityOperationsMixin._build_entity_document(
                    None,
                    entity_id="ent-autobot",
                    entity_type="platform",
                    name="AutoBot",
                    observations=["An AI automation platform"],
                    entity_metadata={},
                ),
            ]
        )
        layer = Layer2OnDemand()
        result = await layer.render(
            {
                "user_message": "Tell me about AutoBot",
                "memory_graph": fake_graph,
                "model_name": "default",
            }
        )
        assert "AutoBot" in result

    @pytest.mark.asyncio
    async def test_render_swallows_memory_graph_errors(self):
        from chat_history.layers import Layer2OnDemand

        fake_graph = MagicMock()
        fake_graph.search_entities = AsyncMock(side_effect=RuntimeError("graph error"))
        layer = Layer2OnDemand()
        result = await layer.render(
            {
                "user_message": "Tell me about AutoBot",
                "memory_graph": fake_graph,
            }
        )
        assert result == ""


# ---------------------------------------------------------------------------
# Layer3DeepSearch tests
# ---------------------------------------------------------------------------


class TestLayer3DeepSearch:
    @pytest.mark.asyncio
    async def test_should_load_true_on_search_message(self):
        from chat_history.layers import Layer3DeepSearch

        layer = Layer3DeepSearch()
        assert await layer.should_load("search for recent deployments")
        assert await layer.should_load("find me all records about ansible")
        assert await layer.should_load("lookup the Redis config")

    @pytest.mark.asyncio
    async def test_should_load_false_on_greeting(self):
        from chat_history.layers import Layer3DeepSearch

        layer = Layer3DeepSearch()
        assert not await layer.should_load("hello")
        assert not await layer.should_load("what time is it?")

    @pytest.mark.asyncio
    async def test_render_returns_empty_without_knowledge_service(self):
        from chat_history.layers import Layer3DeepSearch

        layer = Layer3DeepSearch()
        result = await layer.render({"user_message": "search for X", "knowledge_service": None})
        assert result == ""

    @pytest.mark.asyncio
    async def test_render_with_knowledge_service_returns_context(self):
        from chat_history.layers import Layer3DeepSearch

        fake_ks = MagicMock()
        fake_ks.conversation_aware_retrieve = AsyncMock(
            return_value=("KNOWLEDGE CONTEXT:\n1. Some fact", [{"content": "Some fact"}], None, None)
        )
        layer = Layer3DeepSearch()
        result = await layer.render(
            {
                "user_message": "search for Redis config",
                "knowledge_service": fake_ks,
            }
        )
        assert "KNOWLEDGE CONTEXT" in result

    @pytest.mark.asyncio
    async def test_render_swallows_knowledge_service_errors(self):
        from chat_history.layers import Layer3DeepSearch

        fake_ks = MagicMock()
        fake_ks.conversation_aware_retrieve = AsyncMock(side_effect=RuntimeError("kb error"))
        layer = Layer3DeepSearch()
        result = await layer.render(
            {
                "user_message": "search for Redis config",
                "knowledge_service": fake_ks,
            }
        )
        assert result == ""


# ---------------------------------------------------------------------------
# TieredContextBuilder — feature flag tests
# ---------------------------------------------------------------------------


class TestTieredContextBuilderFeatureFlag:
    @pytest.mark.asyncio
    async def test_returns_empty_when_flag_off(self):
        """When TIERED_CONTEXT_ENABLED=false, builder returns empty string."""
        # Temporarily override the module-level flag
        import chat_history.layers as layers_mod
        from chat_history.layers import TieredContextBuilder

        original = layers_mod.TIERED_CONTEXT_ENABLED
        try:
            layers_mod.TIERED_CONTEXT_ENABLED = False
            builder = TieredContextBuilder()
            result = await builder.build(
                user_message="hello",
                model_name="default",
                session_id="sess-1",
            )
            assert result == ""
        finally:
            layers_mod.TIERED_CONTEXT_ENABLED = original

    @pytest.mark.asyncio
    async def test_returns_content_when_flag_on(self):
        """When TIERED_CONTEXT_ENABLED=true, builder returns non-empty context."""
        import chat_history.layers as layers_mod

        original = layers_mod.TIERED_CONTEXT_ENABLED
        try:
            layers_mod.TIERED_CONTEXT_ENABLED = True

            mock_gen = MagicMock()
            mock_gen.generate = AsyncMock(return_value="## Essential Context\n[general] some fact")

            with patch("memory.essential_story.EssentialStoryGenerator", return_value=mock_gen):
                builder = layers_mod.TieredContextBuilder()
                result = await builder.build(
                    user_message="hello there",
                    model_name="default",
                    session_id="sess-1",
                )
                # L0 at minimum should appear
                assert "## Identity" in result
        finally:
            layers_mod.TIERED_CONTEXT_ENABLED = original

    @pytest.mark.asyncio
    async def test_l2_fires_when_entity_in_message_and_flag_on(self):
        """L2 fires when entity detected and flag is on."""
        import chat_history.layers as layers_mod

        original = layers_mod.TIERED_CONTEXT_ENABLED
        try:
            layers_mod.TIERED_CONTEXT_ENABLED = True

            from autobot_memory_graph.entities import EntityOperationsMixin

            mock_gen = MagicMock()
            mock_gen.generate = AsyncMock(return_value="")
            fake_graph = MagicMock()
            fake_graph.search_entities = AsyncMock(
                return_value=[
                    EntityOperationsMixin._build_entity_document(
                        None,
                        entity_id="ent-redis",
                        entity_type="service",
                        name="Redis",
                        observations=["In-memory data store"],
                        entity_metadata={},
                    )
                ]
            )

            with patch("memory.essential_story.EssentialStoryGenerator", return_value=mock_gen):
                builder = layers_mod.TieredContextBuilder()
                result = await builder.build(
                    user_message="Tell me about Redis configuration",
                    model_name="default",
                    session_id="sess-2",
                    memory_graph=fake_graph,
                )
                assert "Redis" in result
        finally:
            layers_mod.TIERED_CONTEXT_ENABLED = original

    @pytest.mark.asyncio
    async def test_l3_fires_on_retrieval_query_and_flag_on(self):
        """L3 fires when retrieval keyword detected and flag is on."""
        import chat_history.layers as layers_mod

        original = layers_mod.TIERED_CONTEXT_ENABLED
        try:
            layers_mod.TIERED_CONTEXT_ENABLED = True

            mock_gen = MagicMock()
            mock_gen.generate = AsyncMock(return_value="")
            fake_ks = MagicMock()
            fake_ks.conversation_aware_retrieve = AsyncMock(
                return_value=("KNOWLEDGE CONTEXT:\n1. Deep fact", [{"content": "Deep fact"}], None, None)
            )

            with patch("memory.essential_story.EssentialStoryGenerator", return_value=mock_gen):
                builder = layers_mod.TieredContextBuilder()
                result = await builder.build(
                    user_message="search for ansible playbooks",
                    model_name="default",
                    session_id="sess-3",
                    knowledge_service=fake_ks,
                )
                assert "KNOWLEDGE CONTEXT" in result
        finally:
            layers_mod.TIERED_CONTEXT_ENABLED = original

    @pytest.mark.asyncio
    async def test_l3_does_not_fire_on_greeting_even_when_flag_on(self):
        """L3 must not fire for generic non-retrieval messages."""
        import chat_history.layers as layers_mod

        original = layers_mod.TIERED_CONTEXT_ENABLED
        try:
            layers_mod.TIERED_CONTEXT_ENABLED = True

            mock_gen = MagicMock()
            mock_gen.generate = AsyncMock(return_value="")
            fake_ks = MagicMock()
            fake_ks.conversation_aware_retrieve = AsyncMock(return_value=("SHOULD NOT APPEAR", [], None, None))

            with patch("memory.essential_story.EssentialStoryGenerator", return_value=mock_gen):
                builder = layers_mod.TieredContextBuilder()
                result = await builder.build(
                    user_message="hello",
                    model_name="default",
                    session_id="sess-4",
                    knowledge_service=fake_ks,
                )
                assert "SHOULD NOT APPEAR" not in result
        finally:
            layers_mod.TIERED_CONTEXT_ENABLED = original


# ---------------------------------------------------------------------------
# L2 entity fact extraction (#13686)
#
# The layer used to read `description` then `content`. The canonical document
# from EntityOperationsMixin._build_entity_document carries neither — so L2
# found entities, produced an empty string for each, and rendered nothing on
# every real turn. Reconnecting the graph (#13696) fixed the plumbing; this is
# the half that made the layer still silent.
# ---------------------------------------------------------------------------


class TestEntityFacts:
    def test_reads_observations_from_a_real_entity_document(self):
        """Built by the function that defines the schema, not hand-written."""
        from autobot_memory_graph.entities import EntityOperationsMixin
        from chat_history.layers import _entity_facts

        doc = EntityOperationsMixin._build_entity_document(
            None,
            entity_id="ent-1",
            entity_type="service",
            name="Redis",
            observations=["in-memory store", "used for sessions"],
            entity_metadata={},
        )

        assert _entity_facts(doc) == "in-memory store; used for sessions"

    def test_the_old_fields_are_absent_from_a_real_document(self):
        """Pins why the previous read could never match."""
        from autobot_memory_graph.entities import EntityOperationsMixin

        doc = EntityOperationsMixin._build_entity_document(
            None,
            entity_id="ent-1",
            entity_type="service",
            name="Redis",
            observations=["anything"],
            entity_metadata={},
        )

        assert "description" not in doc
        assert "content" not in doc

    def test_caps_the_number_of_observations(self):
        from chat_history.layers import _entity_facts

        facts = _entity_facts({"observations": [f"obs{i}" for i in range(10)]})

        assert facts == "obs0; obs1; obs2"

    def test_falls_back_to_description_then_content(self):
        """Other callers may hand L2 a different mapping; do not regress them."""
        from chat_history.layers import _entity_facts

        assert _entity_facts({"description": "a description"}) == "a description"
        assert _entity_facts({"content": "some content"}) == "some content"
        assert _entity_facts({"observations": [], "content": "fallback"}) == "fallback"

    def test_empty_entity_yields_nothing(self):
        from chat_history.layers import _entity_facts

        assert _entity_facts({}) == ""
        assert _entity_facts({"observations": ["  ", ""]}) == ""

    @pytest.mark.asyncio
    async def test_layer2_renders_a_block_for_a_real_entity(self):
        """End of the chain: a real document reaches the rendered prompt block."""
        from unittest.mock import AsyncMock, MagicMock

        from autobot_memory_graph.entities import EntityOperationsMixin
        from chat_history.layers import Layer2OnDemand

        doc = EntityOperationsMixin._build_entity_document(
            None,
            entity_id="ent-1",
            entity_type="service",
            name="Redis",
            observations=["in-memory store used for sessions"],
            entity_metadata={},
        )
        graph = MagicMock()
        graph.search_entities = AsyncMock(return_value=[doc])

        out = await Layer2OnDemand().render({"user_message": "How does Redis work?", "memory_graph": graph})

        assert out.startswith("## Related Context")
        assert "**Redis**: in-memory store used for sessions" in out

    @pytest.mark.asyncio
    async def test_layer2_stays_silent_without_a_graph(self):
        from chat_history.layers import Layer2OnDemand

        assert await Layer2OnDemand().render({"user_message": "Redis?", "memory_graph": None}) == ""
