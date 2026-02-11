# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Unit tests for TaskRegistry.

Issue #759: Knowledge Pipeline Foundation - Extract, Cognify, Load (ECL).
"""

import pytest
from knowledge.pipeline.registry import TaskRegistry


@pytest.fixture(autouse=True)
def clean_registry():
    """Clear registry between tests."""
    original_ext = TaskRegistry._extractors.copy()
    original_cog = TaskRegistry._cognifiers.copy()
    original_ldr = TaskRegistry._loaders.copy()
    yield
    TaskRegistry._extractors = original_ext
    TaskRegistry._cognifiers = original_cog
    TaskRegistry._loaders = original_ldr


class TestRegisterExtractor:
    """Tests for extractor registration."""

    def test_register_extractor_decorator(self):
        @TaskRegistry.register_extractor("test_extract")
        class TestExtractor:
            pass

        assert "test_extract" in TaskRegistry._extractors
        assert TaskRegistry._extractors["test_extract"] is TestExtractor

    def test_get_extractor_returns_class(self):
        @TaskRegistry.register_extractor("my_extract")
        class MyExtractor:
            pass

        result = TaskRegistry.get_extractor("my_extract")
        assert result is MyExtractor

    def test_get_extractor_returns_none_for_missing(self):
        assert TaskRegistry.get_extractor("nonexistent") is None


class TestRegisterCognifier:
    """Tests for cognifier registration."""

    def test_register_cognifier_decorator(self):
        @TaskRegistry.register_cognifier("test_cognify")
        class TestCognifier:
            pass

        assert "test_cognify" in TaskRegistry._cognifiers
        assert TaskRegistry._cognifiers["test_cognify"] is TestCognifier

    def test_get_cognifier_returns_class(self):
        @TaskRegistry.register_cognifier("my_cognify")
        class MyCognifier:
            pass

        assert TaskRegistry.get_cognifier("my_cognify") is MyCognifier

    def test_get_cognifier_returns_none_for_missing(self):
        assert TaskRegistry.get_cognifier("nonexistent") is None


class TestRegisterLoader:
    """Tests for loader registration."""

    def test_register_loader_decorator(self):
        @TaskRegistry.register_loader("test_load")
        class TestLoader:
            pass

        assert "test_load" in TaskRegistry._loaders
        assert TaskRegistry._loaders["test_load"] is TestLoader

    def test_get_loader_returns_class(self):
        @TaskRegistry.register_loader("my_load")
        class MyLoader:
            pass

        assert TaskRegistry.get_loader("my_load") is MyLoader

    def test_get_loader_returns_none_for_missing(self):
        assert TaskRegistry.get_loader("nonexistent") is None


class TestGetTask:
    """Tests for unified get_task method."""

    def test_get_task_extract(self):
        @TaskRegistry.register_extractor("chunk_text")
        class Chunker:
            pass

        assert TaskRegistry.get_task("extract", "chunk_text") is Chunker

    def test_get_task_cognify(self):
        @TaskRegistry.register_cognifier("extract_entities")
        class EntityExtractor:
            pass

        result = TaskRegistry.get_task("cognify", "extract_entities")
        assert result is EntityExtractor

    def test_get_task_load(self):
        @TaskRegistry.register_loader("chromadb")
        class ChromaLoader:
            pass

        assert TaskRegistry.get_task("load", "chromadb") is ChromaLoader

    def test_get_task_invalid_stage(self):
        assert TaskRegistry.get_task("invalid", "test") is None

    def test_get_task_missing_name(self):
        assert TaskRegistry.get_task("extract", "missing") is None


class TestDecoratorPreservesClass:
    """Decorators should return the original class unchanged."""

    def test_extractor_decorator_returns_class(self):
        @TaskRegistry.register_extractor("preserve_test")
        class Original:
            value = 42

        assert Original.value == 42

    def test_cognifier_decorator_returns_class(self):
        @TaskRegistry.register_cognifier("preserve_test_c")
        class Original:
            value = 99

        assert Original.value == 99

    def test_loader_decorator_returns_class(self):
        @TaskRegistry.register_loader("preserve_test_l")
        class Original:
            value = 7

        assert Original.value == 7
