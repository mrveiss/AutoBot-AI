# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Unit Tests for Shared Caches (Issue #607)

Tests for FileListCache and ASTCache utilities that eliminate
redundant file traversals and AST parsing across analyzers.
"""

import ast

import pytest
from src.code_intelligence.shared.ast_cache import (
    ASTCache,
    get_ast,
    get_ast_cache_stats,
    get_ast_safe,
    get_ast_with_content,
    invalidate_ast_cache,
)
from src.code_intelligence.shared.file_cache import (
    FileListCache,
    get_file_cache_stats,
    get_frontend_files,
    get_python_files,
    invalidate_file_cache,
)


class TestFileListCache:
    """Tests for FileListCache."""

    @pytest.fixture(autouse=True)
    def reset_cache(self):
        """Reset singleton before and after each test."""
        # Reset module-level instance as well
        import src.code_intelligence.shared.file_cache as fc

        fc._cache_instance = None
        FileListCache.reset_instance()
        yield
        fc._cache_instance = None
        FileListCache.reset_instance()

    @pytest.mark.asyncio
    async def test_cache_returns_python_files(self):
        """Test that get_python_files returns Python files."""
        files = await get_python_files()
        assert isinstance(files, list)
        assert len(files) > 0
        assert all(str(f).endswith(".py") for f in files)

    @pytest.mark.asyncio
    async def test_cache_hit_on_second_call(self):
        """Test that second call uses cache."""
        # First call - cache miss
        files1 = await get_python_files()
        stats1 = get_file_cache_stats()
        assert stats1["misses"] >= 1  # At least one miss

        initial_hits = stats1["hits"]
        initial_misses = stats1["misses"]

        # Second call - cache hit
        files2 = await get_python_files()
        stats2 = get_file_cache_stats()
        assert stats2["hits"] == initial_hits + 1  # One more hit
        assert stats2["misses"] == initial_misses  # No new misses
        assert files1 == files2

    @pytest.mark.asyncio
    async def test_cache_invalidation(self):
        """Test that invalidation clears cache."""
        # Populate cache
        await get_python_files()
        stats1 = get_file_cache_stats()
        initial_misses = stats1["misses"]

        # Invalidate
        invalidate_file_cache()

        # Should be cache miss again
        await get_python_files()
        stats2 = get_file_cache_stats()
        assert stats2["misses"] == initial_misses + 1
        assert stats2["invalidations"] >= 1

    @pytest.mark.asyncio
    async def test_different_extensions_cached_separately(self):
        """Test that different extensions are cached separately."""
        stats_before = get_file_cache_stats()
        initial_misses = stats_before["misses"]

        await get_python_files()
        await get_frontend_files()

        stats = get_file_cache_stats()
        # Should have 2 additional misses (one for each extension set)
        assert stats["misses"] >= initial_misses + 2

    @pytest.mark.asyncio
    async def test_custom_root_path(self, tmp_path):
        """Test cache with custom root path."""
        # Create test files
        (tmp_path / "test1.py").write_text("# test")
        (tmp_path / "test2.py").write_text("# test")
        (tmp_path / "sub").mkdir()
        (tmp_path / "sub" / "test3.py").write_text("# test")

        files = await get_python_files(tmp_path)
        assert len(files) == 3

    def test_singleton_pattern(self):
        """Test that FileListCache is a singleton."""
        cache1 = FileListCache()
        cache2 = FileListCache()
        assert cache1 is cache2


class TestASTCache:
    """Tests for ASTCache."""

    @pytest.fixture(autouse=True)
    def reset_cache(self):
        """Reset singleton before and after each test."""
        # Reset module-level instance as well
        import src.code_intelligence.shared.ast_cache as ac

        ac._cache_instance = None
        ASTCache.reset_instance()
        yield
        ac._cache_instance = None
        ASTCache.reset_instance()

    def test_get_ast_parses_python_file(self, tmp_path):
        """Test that get_ast parses Python file."""
        test_file = tmp_path / "test.py"
        test_file.write_text("def hello():\n    pass\n")

        tree = get_ast(str(test_file))
        assert isinstance(tree, ast.Module)
        assert len(tree.body) == 1
        assert isinstance(tree.body[0], ast.FunctionDef)

    def test_cache_hit_on_second_call(self, tmp_path):
        """Test that second call uses cache."""
        test_file = tmp_path / "test.py"
        test_file.write_text("x = 1\n")

        # First call - cache miss
        tree1 = get_ast(str(test_file))
        stats1 = get_ast_cache_stats()
        initial_misses = stats1["misses"]
        initial_hits = stats1["hits"]

        # Second call - cache hit
        tree2 = get_ast(str(test_file))
        stats2 = get_ast_cache_stats()
        assert stats2["hits"] == initial_hits + 1
        assert stats2["misses"] == initial_misses  # No new misses

        # Same AST object returned
        assert tree1 is tree2

    def test_cache_invalidation_on_file_change(self, tmp_path):
        """Test that cache is invalidated when file changes."""
        import time

        test_file = tmp_path / "test.py"
        test_file.write_text("x = 1\n")

        # First parse
        tree1 = get_ast(str(test_file))
        assert isinstance(tree1.body[0], ast.Assign)

        # Modify file (need to change mtime)
        time.sleep(0.1)
        test_file.write_text("def func(): pass\n")

        # Should re-parse due to mtime change
        tree2 = get_ast(str(test_file))
        assert isinstance(tree2.body[0], ast.FunctionDef)
        assert tree1 is not tree2

    def test_get_ast_safe_returns_none_on_error(self, tmp_path):
        """Test that get_ast_safe returns None on parse error."""
        test_file = tmp_path / "test.py"
        test_file.write_text("def broken(:\n")  # Invalid syntax

        tree = get_ast_safe(str(test_file))
        assert tree is None

        stats = get_ast_cache_stats()
        assert stats["parse_errors"] == 1

    def test_get_ast_with_content(self, tmp_path):
        """Test that get_ast_with_content returns both AST and content."""
        test_file = tmp_path / "test.py"
        content = "x = 42\ny = 'hello'\n"
        test_file.write_text(content)

        tree, returned_content = get_ast_with_content(str(test_file))
        assert isinstance(tree, ast.Module)
        assert returned_content == content

    def test_lru_eviction(self, tmp_path, monkeypatch):
        """Test that LRU eviction works when cache is full."""
        # Monkeypatch env var BEFORE importing/creating cache
        monkeypatch.setenv("AST_CACHE_MAX_SIZE", "3")

        # Force module reload and reset to pick up new env var
        import importlib

        import src.code_intelligence.shared.ast_cache as ac

        ac._cache_instance = None
        ASTCache.reset_instance()
        importlib.reload(ac)

        cache = ac.ASTCache()

        # Create test files
        files = []
        for i in range(5):
            f = tmp_path / f"test{i}.py"
            f.write_text(f"x = {i}\n")
            files.append(str(f))

        # Parse all files - should evict oldest
        for f in files:
            cache.get(f)

        stats = cache.get_stats()
        assert stats.current_size == 3
        assert stats.evictions == 2

        # Cleanup - restore default env and reset
        monkeypatch.setenv("AST_CACHE_MAX_SIZE", "1000")
        ac._cache_instance = None
        ac.ASTCache.reset_instance()
        importlib.reload(ac)

    def test_invalidate_specific_file(self, tmp_path):
        """Test invalidating a specific file."""
        test_file1 = tmp_path / "test1.py"
        test_file2 = tmp_path / "test2.py"
        test_file1.write_text("x = 1\n")
        test_file2.write_text("y = 2\n")

        # Parse both files
        get_ast(str(test_file1))
        get_ast(str(test_file2))

        stats1 = get_ast_cache_stats()
        assert stats1["current_size"] == 2

        # Invalidate only first file
        invalidate_ast_cache(str(test_file1))

        stats2 = get_ast_cache_stats()
        assert stats2["current_size"] == 1
        assert stats2["invalidations"] == 1

    def test_file_not_found_raises(self, tmp_path):
        """Test that get_ast raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            get_ast(str(tmp_path / "nonexistent.py"))

    def test_syntax_error_raises(self, tmp_path):
        """Test that get_ast raises SyntaxError."""
        test_file = tmp_path / "test.py"
        test_file.write_text("def broken(\n")

        with pytest.raises(SyntaxError):
            get_ast(str(test_file))

    def test_singleton_pattern(self):
        """Test that ASTCache is a singleton."""
        cache1 = ASTCache()
        cache2 = ASTCache()
        assert cache1 is cache2


class TestIntegration:
    """Integration tests for caches working together."""

    @pytest.fixture(autouse=True)
    def reset_caches(self):
        """Reset all caches before and after each test."""
        # Reset both module-level instances
        import src.code_intelligence.shared.ast_cache as ac
        import src.code_intelligence.shared.file_cache as fc

        fc._cache_instance = None
        ac._cache_instance = None
        FileListCache.reset_instance()
        ASTCache.reset_instance()
        yield
        fc._cache_instance = None
        ac._cache_instance = None
        FileListCache.reset_instance()
        ASTCache.reset_instance()

    @pytest.mark.asyncio
    async def test_analyze_files_with_both_caches(self, tmp_path):
        """Test using both caches together like an analyzer would."""
        # Create test files
        (tmp_path / "module1.py").write_text("def func1(): pass\n")
        (tmp_path / "module2.py").write_text("class Class1: pass\n")
        (tmp_path / "module3.py").write_text("x = 1\n")

        # Get initial stats for relative comparison
        initial_file_stats = get_file_cache_stats()
        initial_ast_stats = get_ast_cache_stats()
        initial_file_misses = initial_file_stats["misses"]
        initial_file_hits = initial_file_stats["hits"]
        initial_ast_misses = initial_ast_stats["misses"]
        initial_ast_hits = initial_ast_stats["hits"]

        # Simulate analyzer workflow
        python_files = await get_python_files(tmp_path)
        assert len(python_files) == 3

        # Parse each file
        results = []
        for file_path in python_files:
            tree = get_ast_safe(str(file_path))
            if tree:
                results.append(
                    {
                        "file": str(file_path),
                        "nodes": len(list(ast.walk(tree))),
                    }
                )

        assert len(results) == 3

        # Check both caches have stats (use relative comparisons)
        file_stats = get_file_cache_stats()
        ast_stats = get_ast_cache_stats()

        assert file_stats["misses"] == initial_file_misses + 1  # One file list miss
        assert ast_stats["misses"] == initial_ast_misses + 3  # Three AST misses

        # Second pass should use cache
        python_files2 = await get_python_files(tmp_path)
        for file_path in python_files2:
            get_ast_safe(str(file_path))

        file_stats2 = get_file_cache_stats()
        ast_stats2 = get_ast_cache_stats()

        assert file_stats2["hits"] == initial_file_hits + 1  # One file list hit
        assert ast_stats2["hits"] == initial_ast_hits + 3  # Three AST hits


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
