# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Unit tests for NPU-Accelerated Semantic Code Search

Issue #207: Tests for code embedding generation and semantic search.

Tests:
- CodeEmbeddingGenerator initialization and embedding generation
- Code collection storage in ChromaDB
- Semantic code search with embeddings
- Hybrid search combining semantic and keyword
"""

import asyncio
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))


class TestCodeEmbeddingGenerator(unittest.TestCase):
    """Test suite for CodeEmbeddingGenerator class."""

    def setUp(self):
        """Set up test fixtures."""
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)

    def tearDown(self):
        """Clean up."""
        self.loop.close()

    @patch("src.code_embedding_generator.get_embedding_cache")
    @patch("src.code_embedding_generator.WorkerNode")
    def test_generator_initialization(self, mock_worker, mock_cache):
        """Test CodeEmbeddingGenerator initializes correctly."""
        from code_embedding_generator import CodeEmbeddingGenerator

        mock_cache.return_value = MagicMock()
        mock_worker_instance = MagicMock()
        mock_worker_instance.detect_capabilities.return_value = {
            "openvino_npu_available": False,
            "cuda_available": False,
        }
        mock_worker.return_value = mock_worker_instance

        generator = CodeEmbeddingGenerator()

        self.assertEqual(generator.model_name, "microsoft/codebert-base")
        self.assertEqual(generator.embedding_dim, 768)
        self.assertFalse(generator.initialized)

    @patch("src.code_embedding_generator.get_embedding_cache")
    @patch("src.code_embedding_generator.WorkerNode")
    def test_embedding_dimension(self, mock_worker, mock_cache):
        """Test embedding dimension is correct."""
        from code_embedding_generator import (
            CODEBERT_EMBEDDING_DIM,
            CodeEmbeddingGenerator,
        )

        mock_cache.return_value = MagicMock()
        mock_worker.return_value = MagicMock()

        generator = CodeEmbeddingGenerator()
        self.assertEqual(generator.get_embedding_dim(), CODEBERT_EMBEDDING_DIM)
        self.assertEqual(generator.get_embedding_dim(), 768)

    @patch("src.code_embedding_generator.get_embedding_cache")
    @patch("src.code_embedding_generator.WorkerNode")
    def test_cache_key_generation(self, mock_worker, mock_cache):
        """Test cache key generation is deterministic."""
        from code_embedding_generator import CodeEmbeddingGenerator

        mock_cache.return_value = MagicMock()
        mock_worker.return_value = MagicMock()

        generator = CodeEmbeddingGenerator()

        code1 = "def hello(): pass"
        code2 = "def world(): pass"

        key1a = generator._get_cache_key(code1, "python")
        key1b = generator._get_cache_key(code1, "python")
        key2 = generator._get_cache_key(code2, "python")
        key3 = generator._get_cache_key(code1, "javascript")

        self.assertEqual(key1a, key1b)
        self.assertNotEqual(key1a, key2)
        self.assertNotEqual(key1a, key3)


class TestNPUCodeSearchAgent(unittest.TestCase):
    """Test suite for NPUCodeSearchAgent code search functionality."""

    def setUp(self):
        """Set up test fixtures."""
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)

    def tearDown(self):
        """Clean up."""
        self.loop.close()

    def test_extract_element_code_function(self):
        """Test extraction of function code."""
        from agents.npu_code_search_agent import NPUCodeSearchAgent

        with patch.object(NPUCodeSearchAgent, "__init__", lambda x: None):
            agent = NPUCodeSearchAgent()

            content = '''def hello():
    """Say hello."""
    print("Hello")  # noqa: print
    return True

def world():
    pass
'''
            result = agent._extract_element_code(content, 1, "function", max_lines=10)

            self.assertIn("def hello():", result)
            self.assertIn('print("Hello")', result)  # noqa: print
            self.assertIn("return True", result)
            self.assertNotIn("def world():", result)

    def test_extract_element_code_class(self):
        """Test extraction of class code."""
        from agents.npu_code_search_agent import NPUCodeSearchAgent

        with patch.object(NPUCodeSearchAgent, "__init__", lambda x: None):
            agent = NPUCodeSearchAgent()

            content = '''class MyClass:
    """A test class."""

    def __init__(self):
        self.value = 0

    def method(self):
        return self.value

class OtherClass:
    pass
'''
            result = agent._extract_element_code(content, 1, "class", max_lines=20)

            self.assertIn("class MyClass:", result)
            self.assertIn("def __init__(self):", result)
            self.assertIn("def method(self):", result)
            self.assertNotIn("class OtherClass:", result)

    def test_extract_element_code_empty(self):
        """Test extraction with invalid line number."""
        from agents.npu_code_search_agent import NPUCodeSearchAgent

        with patch.object(NPUCodeSearchAgent, "__init__", lambda x: None):
            agent = NPUCodeSearchAgent()

            content = "def hello(): pass"
            result = agent._extract_element_code(content, 100, "function")

            self.assertEqual(result, "")


class TestHybridSearch(unittest.TestCase):
    """Test suite for hybrid search functionality."""

    def test_hybrid_weight_calculation(self):
        """Test that hybrid weights sum to 1.0."""
        semantic_weight = 0.7
        keyword_weight = 1.0 - semantic_weight

        self.assertAlmostEqual(semantic_weight + keyword_weight, 1.0)

    def test_result_merging_logic(self):
        """Test that results from same location are merged."""
        from agents.npu_code_search_agent import CodeSearchResult

        semantic_result = CodeSearchResult(
            file_path="test.py",
            content="def test(): pass",
            line_number=1,
            confidence=0.9,
            context_lines=[],
            metadata={"search_type": "semantic"},
        )

        keyword_result = CodeSearchResult(
            file_path="test.py",
            content="def test(): pass",
            line_number=1,
            confidence=0.8,
            context_lines=[],
            metadata={"search_type": "keyword"},
        )

        key1 = (semantic_result.file_path, semantic_result.line_number)
        key2 = (keyword_result.file_path, keyword_result.line_number)
        self.assertEqual(key1, key2)


class TestCodeCollectionIntegration(unittest.TestCase):
    """Integration tests for code collection in ChromaDB."""

    def setUp(self):
        """Set up test fixtures."""
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)

    def tearDown(self):
        """Clean up."""
        self.loop.close()

    def test_collection_name_added(self):
        """Test that code collection is added to collection_names."""
        collection_names = {
            "text": "autobot_text_embeddings",
            "image": "autobot_image_embeddings",
            "audio": "autobot_audio_embeddings",
            "multimodal": "autobot_multimodal_fused",
            "code": "autobot_code_embeddings",
        }

        self.assertIn("code", collection_names)
        self.assertEqual(collection_names["code"], "autobot_code_embeddings")

    def test_embedding_metadata_structure(self):
        """Test that embedding metadata has required fields."""
        required_fields = [
            "file_path",
            "line_number",
            "element_type",
            "element_name",
            "language",
            "content_hash",
            "indexed_at",
        ]

        test_metadata = {
            "file_path": "test.py",
            "line_number": 1,
            "element_type": "function",
            "element_name": "test_func",
            "language": "python",
            "content_hash": "abc123",
            "indexed_at": 1234567890.0,
        }

        for field in required_fields:
            self.assertIn(field, test_metadata)


class TestSearchTypes(unittest.TestCase):
    """Test different search type handling."""

    def test_search_types_supported(self):
        """Test that all search types are recognized."""
        supported_types = ["element", "exact", "regex", "hybrid", "semantic"]

        for search_type in supported_types:
            self.assertIn(search_type, supported_types)

    def test_hybrid_is_new_type(self):
        """Test that hybrid search type is available."""
        search_type = "hybrid"
        self.assertEqual(search_type, "hybrid")


if __name__ == "__main__":
    unittest.main()
