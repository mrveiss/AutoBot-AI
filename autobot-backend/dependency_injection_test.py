# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""
Test suite for dependency injection refactoring.

These tests verify that components can be properly instantiated
with injected dependencies and that backward compatibility is maintained.
"""

from unittest.mock import Mock

import pytest

from config import ConfigManager
from dependencies import (
    get_config,
    get_diagnostics,
    get_knowledge_base,
    get_orchestrator,
)
from diagnostics import Diagnostics
from knowledge_base import KnowledgeBase
from orchestrator import Orchestrator


class TestDependencyInjection:
    """Test dependency injection functionality"""

    def test_config_dependency_provider(self):
        """Test that config dependency provider returns the global config"""
        config = get_config()
        assert isinstance(config, ConfigManager)
        assert hasattr(config, "get")
        assert hasattr(config, "get_nested")

    def test_orchestrator_with_dependencies(self):
        """Test that Orchestrator can be created with injected dependencies"""
        # Create mock dependencies
        mock_config = Mock(spec=ConfigManager)
        mock_config.get_llm_config.return_value = {
            "orchestrator_llm": "test_model",
            "ollama": {"model": "test_ollama", "models": {}},
            "task_llm": "test_task_llm",
        }
        mock_config.get_nested.return_value = "local"
        # ConfigManager.get() returns the caller's default for any key the
        # settings model does not declare (e.g. orchestrator.max_parallel_tasks),
        # so mirror that instead of handing back bare Mocks that no numeric
        # consumer can use.
        mock_config.get.side_effect = lambda key, default=None: default

        mock_llm = Mock()
        mock_kb = Mock()
        mock_diagnostics = Mock()

        # Create orchestrator with injected dependencies
        orchestrator = Orchestrator(
            config_manager=mock_config,
            llm_service=mock_llm,
            knowledge_base=mock_kb,
            diagnostics=mock_diagnostics,
        )

        # Verify dependencies are properly injected
        assert orchestrator.config_manager is mock_config
        assert orchestrator.llm_service is mock_llm
        assert orchestrator.knowledge_base is mock_kb
        assert orchestrator.diagnostics is mock_diagnostics

        # Verify config is used correctly. OrchestratorConfig reads the model
        # names through get_llm_config() and every orchestrator.* tunable
        # through get(); it has no get_nested() call to assert on.
        mock_config.get_llm_config.assert_called_once()
        mock_config.get.assert_called()

    def test_orchestrator_backward_compatibility(self):
        """Test that Orchestrator still works without injected dependencies"""
        # Create orchestrator without dependencies (should use defaults)
        orchestrator = Orchestrator()

        # Verify that default dependencies are created
        assert orchestrator.config_manager is not None
        assert orchestrator.llm_service is not None
        assert orchestrator.knowledge_base is not None
        assert orchestrator.diagnostics is not None

        # Verify they are the expected types
        assert isinstance(orchestrator.config_manager, ConfigManager)

    def test_knowledge_base_with_config(self):
        """Test that KnowledgeBase can be created with injected config"""
        # Create mock config
        mock_config = Mock(spec=ConfigManager)
        mock_config.get_nested.return_value = None
        mock_config.get_llm_config.return_value = {
            "unified": {"embedding": {"providers": {"ollama": {"selected_model": "test_embed"}}}}
        }
        mock_config.get.side_effect = lambda key, default=None: default

        # Create knowledge base with injected config
        kb = KnowledgeBase(config_manager=mock_config)

        # Verify config is properly injected and used. KnowledgeBase reads its
        # Redis/ChromaDB settings through ConfigManager.get(); the embedding
        # model it once resolved via get_llm_config() now comes from ssot_config
        # inside the async _configure_llama_index step, not from construction.
        assert kb.config_manager is mock_config
        mock_config.get.assert_called()

    def test_knowledge_base_backward_compatibility(self):
        """Test that KnowledgeBase still works without injected config"""
        # Create knowledge base without config (should use global)
        kb = KnowledgeBase()

        # Verify that global config is used
        assert kb.config_manager is not None
        assert isinstance(kb.config_manager, ConfigManager)

    def test_diagnostics_with_dependencies(self):
        """Test that Diagnostics can be created with injected dependencies.

        Diagnostics reads no ConfigManager keys at construction: the
        ``diagnostics.*`` settings that models/settings.py declares
        (enabled, use_llm_for_analysis, use_web_search_for_analysis,
        auto_apply_fixes) are not reachable through ConfigManager at all --
        it exposes no ``diagnostics`` section, so every one of those lookups
        can only ever return the caller's default. Asserting a config read
        here would therefore be asserting fake wiring; the contract that
        matters, and that dependencies.get_diagnostics depends on, is that the
        injected instances are the ones held.
        """
        mock_config = Mock(spec=ConfigManager)
        mock_llm = Mock()

        diagnostics = Diagnostics(config_manager=mock_config, llm_service=mock_llm)

        assert diagnostics.config_manager is mock_config
        assert diagnostics.llm_service is mock_llm

    def test_diagnostics_backward_compatibility(self):
        """Test that Diagnostics still works without injected dependencies"""
        # Create diagnostics without dependencies (should use defaults)
        diagnostics = Diagnostics()

        # Verify that default dependencies are created
        assert diagnostics.config_manager is not None
        assert diagnostics.llm_service is not None

        # Verify they are the expected types
        assert isinstance(diagnostics.config_manager, ConfigManager)

    def test_dependency_providers(self):
        """Test that FastAPI dependency providers work correctly"""
        # Test config provider (this works outside FastAPI context)
        config = get_config()
        assert isinstance(config, ConfigManager)

        # Note: Other dependency providers require FastAPI request context
        # They use Depends() which only works within FastAPI endpoint execution
        # We test the actual dependency injection in other test methods

        # Test that the provider functions exist and are callable
        assert callable(get_diagnostics)
        assert callable(get_knowledge_base)
        assert callable(get_orchestrator)

        # Test manual dependency creation (simulates FastAPI behavior)
        config = get_config()

        # Manually call with resolved dependencies (as FastAPI would do)
        from diagnostics import Diagnostics
        from knowledge_base import KnowledgeBase
        from orchestrator import Orchestrator

        diagnostics = Diagnostics(config_manager=config)
        assert isinstance(diagnostics, Diagnostics)

        kb = KnowledgeBase(config_manager=config)
        assert isinstance(kb, KnowledgeBase)

        orchestrator = Orchestrator(config_manager=config)
        assert isinstance(orchestrator, Orchestrator)
        assert hasattr(orchestrator, "config_manager")
        assert hasattr(orchestrator, "llm_service")
        assert hasattr(orchestrator, "knowledge_base")
        assert hasattr(orchestrator, "diagnostics")

    def test_no_global_config_import_in_classes(self):
        """Test that classes use injected config instead of importing global_config_manager"""
        # Create mock config
        mock_config = Mock(spec=ConfigManager)
        mock_config.get_llm_config.return_value = {
            "orchestrator_llm": "test_model",
            "ollama": {"model": "test_ollama", "models": {}},
            "task_llm": "test_task_llm",
        }
        mock_config.get_nested.return_value = "local"
        mock_config.get.side_effect = lambda key, default=None: default

        # Create components with mock config
        orchestrator = Orchestrator(config_manager=mock_config)
        kb = KnowledgeBase(config_manager=mock_config)
        diagnostics = Diagnostics(config_manager=mock_config)

        # Verify that mock config is used (not global)
        assert orchestrator.config_manager is mock_config
        assert kb.config_manager is mock_config
        assert diagnostics.config_manager is mock_config

        # Verify config methods are called on the injected instance. Both
        # Orchestrator and KnowledgeBase read their settings through get();
        # neither reaches for the module-level ConfigManager any more.
        assert mock_config.get_llm_config.called
        assert mock_config.get.called


if __name__ == "__main__":
    pytest.main([__file__])
