"""
Test suite for dependency injection refactoring.

These tests verify that components can be properly instantiated
with injected dependencies and that backward compatibility is maintained.
"""

import pytest
from unittest.mock import Mock

from src.config import ConfigManager
from src.orchestrator import Orchestrator
from src.knowledge_base import KnowledgeBase
from src.diagnostics import Diagnostics
from backend.dependencies import get_config, get_orchestrator, get_knowledge_base, get_diagnostics


class TestDependencyInjection:
    """Test dependency injection functionality"""

    def test_config_dependency_provider(self):
        """Test that config dependency provider returns the global config"""
        config = get_config()
        assert isinstance(config, ConfigManager)
        assert hasattr(config, 'get')
        assert hasattr(config, 'get_nested')

    def test_orchestrator_with_dependencies(self):
        """Test that Orchestrator can be created with injected dependencies"""
        # Create mock dependencies
        mock_config = Mock(spec=ConfigManager)
        mock_config.get_llm_config.return_value = {
            "orchestrator_llm": "test_model",
            "ollama": {"model": "test_ollama", "models": {}},
            "task_llm": "test_task_llm"
        }
        mock_config.get_nested.return_value = "local"
        
        mock_llm = Mock()
        mock_kb = Mock()
        mock_diagnostics = Mock()
        
        # Create orchestrator with injected dependencies
        orchestrator = Orchestrator(
            config_manager=mock_config,
            llm_interface=mock_llm,
            knowledge_base=mock_kb,
            diagnostics=mock_diagnostics
        )
        
        # Verify dependencies are properly injected
        assert orchestrator.config_manager is mock_config
        assert orchestrator.llm_interface is mock_llm
        assert orchestrator.knowledge_base is mock_kb
        assert orchestrator.diagnostics is mock_diagnostics
        
        # Verify config is used correctly
        mock_config.get_llm_config.assert_called_once()
        mock_config.get_nested.assert_called()

    def test_orchestrator_backward_compatibility(self):
        """Test that Orchestrator still works without injected dependencies"""
        # Create orchestrator without dependencies (should use defaults)
        orchestrator = Orchestrator()
        
        # Verify that default dependencies are created
        assert orchestrator.config_manager is not None
        assert orchestrator.llm_interface is not None
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
        mock_config.get.return_value = {"redis": {"host": "test_host", "port": 6379}}
        
        # Create knowledge base with injected config
        kb = KnowledgeBase(config_manager=mock_config)
        
        # Verify config is properly injected and used
        assert kb.config_manager is mock_config
        mock_config.get_llm_config.assert_called_once()
        mock_config.get_nested.assert_called()

    def test_knowledge_base_backward_compatibility(self):
        """Test that KnowledgeBase still works without injected config"""
        # Create knowledge base without config (should use global)
        kb = KnowledgeBase()
        
        # Verify that global config is used
        assert kb.config_manager is not None
        assert isinstance(kb.config_manager, ConfigManager)

    def test_diagnostics_with_dependencies(self):
        """Test that Diagnostics can be created with injected dependencies"""
        # Create mock dependencies
        mock_config = Mock(spec=ConfigManager)
        # Mock the reliability stats file path to a non-existent file
        mock_config.get_nested.side_effect = lambda key, default=None: {
            "data.reliability_stats_file": "/tmp/test_reliability_stats.json",
            "diagnostics.enabled": True,
            "diagnostics.use_llm_for_analysis": True,
            "diagnostics.use_web_search_for_analysis": False,
            "diagnostics.auto_apply_fixes": False
        }.get(key, default)
        
        mock_llm = Mock()
        
        # Create a minimal reliability stats file for the test
        import tempfile
        import json
        import os
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump({}, f)
            temp_file = f.name
        
        try:
            # Update mock to use the temp file
            mock_config.get_nested.side_effect = lambda key, default=None: {
                "data.reliability_stats_file": temp_file,
                "diagnostics.enabled": True,
                "diagnostics.use_llm_for_analysis": True,
                "diagnostics.use_web_search_for_analysis": False,
                "diagnostics.auto_apply_fixes": False
            }.get(key, default)
            
            # Create diagnostics with injected dependencies
            diagnostics = Diagnostics(
                config_manager=mock_config,
                llm_interface=mock_llm
            )
            
            # Verify dependencies are properly injected
            assert diagnostics.config_manager is mock_config
            assert diagnostics.llm_interface is mock_llm
            
            # Verify config is used correctly
            mock_config.get_nested.assert_called()
            
        finally:
            # Clean up temp file
            os.unlink(temp_file)

    def test_diagnostics_backward_compatibility(self):
        """Test that Diagnostics still works without injected dependencies"""
        # Create diagnostics without dependencies (should use defaults)
        diagnostics = Diagnostics()
        
        # Verify that default dependencies are created
        assert diagnostics.config_manager is not None
        assert diagnostics.llm_interface is not None
        
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
        from src.diagnostics import Diagnostics
        from src.knowledge_base import KnowledgeBase
        from src.orchestrator import Orchestrator
        
        diagnostics = Diagnostics(config_manager=config)
        assert isinstance(diagnostics, Diagnostics)
        
        kb = KnowledgeBase(config_manager=config)
        assert isinstance(kb, KnowledgeBase)
        
        orchestrator = Orchestrator(config_manager=config)
        assert isinstance(orchestrator, Orchestrator)
        assert hasattr(orchestrator, 'config_manager')
        assert hasattr(orchestrator, 'llm_interface')
        assert hasattr(orchestrator, 'knowledge_base')
        assert hasattr(orchestrator, 'diagnostics')

    def test_no_global_config_import_in_classes(self):
        """Test that classes use injected config instead of importing global_config_manager"""
        # Create mock config
        mock_config = Mock(spec=ConfigManager)
        mock_config.get_llm_config.return_value = {
            "orchestrator_llm": "test_model",
            "ollama": {"model": "test_ollama", "models": {}},
            "task_llm": "test_task_llm"
        }
        mock_config.get_nested.return_value = "local"
        mock_config.get.return_value = {"redis": {"host": "test_host", "port": 6379}}
        
        # Create components with mock config
        orchestrator = Orchestrator(config_manager=mock_config)
        kb = KnowledgeBase(config_manager=mock_config)
        diagnostics = Diagnostics(config_manager=mock_config)
        
        # Verify that mock config is used (not global)
        assert orchestrator.config_manager is mock_config
        assert kb.config_manager is mock_config
        assert diagnostics.config_manager is mock_config
        
        # Verify config methods are called on the injected instance
        assert mock_config.get_llm_config.called
        assert mock_config.get_nested.called


if __name__ == "__main__":
    pytest.main([__file__])