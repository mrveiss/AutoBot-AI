# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Unit tests for Issue #711 parallel file processing.

Tests the following functionality:
- FileAnalysisResult dataclass creation and to_dict()
- ParallelProcessingStats properties
- _determine_analyzer_type() extension mapping
- _enrich_items_with_metadata() item enrichment
- _aggregate_from_file_result() aggregation logic
- _aggregate_all_results() full aggregation
"""

from pathlib import Path

import pytest

from backend.api.codebase_analytics.types import (
    AnalysisBatchResult,
    FileAnalysisResult,
    ParallelProcessingStats,
)


class TestFileAnalysisResult:
    """Tests for FileAnalysisResult dataclass."""

    def test_basic_creation(self):
        """Test basic FileAnalysisResult creation with required fields."""
        result = FileAnalysisResult(
            file_path=Path("/test/file.py"),
            relative_path="test/file.py",
            extension=".py",
            file_category="code",
        )

        assert result.file_path == Path("/test/file.py")
        assert result.relative_path == "test/file.py"
        assert result.extension == ".py"
        assert result.file_category == "code"
        assert result.was_processed is False
        assert result.was_skipped_unchanged is False

    def test_creation_with_analysis_data(self):
        """Test FileAnalysisResult with full analysis data."""
        result = FileAnalysisResult(
            file_path=Path("/test/file.py"),
            relative_path="test/file.py",
            extension=".py",
            file_category="code",
            was_processed=True,
            functions=[{"name": "test_func", "line": 10}],
            classes=[{"name": "TestClass", "line": 20}],
            imports=["os", "sys"],
            line_count=100,
            code_lines=80,
            comment_lines=15,
            analyzer_type="python",
            stat_key="python_files",
        )

        assert result.was_processed is True
        assert len(result.functions) == 1
        assert result.functions[0]["name"] == "test_func"
        assert len(result.classes) == 1
        assert len(result.imports) == 2
        assert result.line_count == 100
        assert result.analyzer_type == "python"

    def test_to_dict_conversion(self):
        """Test FileAnalysisResult.to_dict() returns correct format."""
        result = FileAnalysisResult(
            file_path=Path("/test/file.py"),
            relative_path="test/file.py",
            extension=".py",
            file_category="code",
            was_processed=True,
            functions=[{"name": "func1"}],
            classes=[{"name": "Class1"}],
            imports=["module1"],
            hardcodes=[{"value": "hardcoded"}],
            problems=[{"type": "issue"}],
            line_count=50,
            code_lines=40,
            comment_lines=5,
            docstring_lines=3,
            blank_lines=2,
            documentation_lines=0,
        )

        d = result.to_dict()

        assert "functions" in d
        assert "classes" in d
        assert "imports" in d
        assert "hardcodes" in d
        assert "problems" in d
        assert d["line_count"] == 50
        assert d["code_lines"] == 40
        assert d["comment_lines"] == 5
        # Verify file_path and analyzer_type are NOT in dict (internal fields)
        assert "file_path" not in d
        assert "analyzer_type" not in d

    def test_skipped_file_result(self):
        """Test FileAnalysisResult for skipped (unchanged) file."""
        result = FileAnalysisResult(
            file_path=Path("/test/cached.py"),
            relative_path="test/cached.py",
            extension=".py",
            file_category="code",
            was_processed=False,
            was_skipped_unchanged=True,
            file_hash="abc123",
        )

        assert result.was_processed is False
        assert result.was_skipped_unchanged is True
        assert result.file_hash == "abc123"
        assert result.functions == []


class TestAnalysisBatchResult:
    """Tests for AnalysisBatchResult dataclass."""

    def test_empty_batch(self):
        """Test empty batch result creation."""
        batch = AnalysisBatchResult()

        assert batch.results == []
        assert batch.files_processed == 0
        assert batch.files_skipped == 0
        assert batch.errors == []

    def test_add_processed_result(self):
        """Test adding a processed result updates counters."""
        batch = AnalysisBatchResult()
        result = FileAnalysisResult(
            file_path=Path("/test/file.py"),
            relative_path="test/file.py",
            extension=".py",
            file_category="code",
            was_processed=True,
        )

        batch.add_result(result)

        assert len(batch.results) == 1
        assert batch.files_processed == 1
        assert batch.files_skipped == 0

    def test_add_skipped_result(self):
        """Test adding a skipped result updates counters."""
        batch = AnalysisBatchResult()
        result = FileAnalysisResult(
            file_path=Path("/test/file.py"),
            relative_path="test/file.py",
            extension=".py",
            file_category="code",
            was_processed=False,
            was_skipped_unchanged=True,
        )

        batch.add_result(result)

        assert len(batch.results) == 1
        assert batch.files_processed == 0
        assert batch.files_skipped == 1

    def test_add_error(self):
        """Test adding an error to batch."""
        batch = AnalysisBatchResult()

        batch.add_error("/test/error.py", "Parse error")

        assert len(batch.errors) == 1
        assert batch.errors[0]["file_path"] == "/test/error.py"
        assert batch.errors[0]["error"] == "Parse error"


class TestParallelProcessingStats:
    """Tests for ParallelProcessingStats dataclass."""

    def test_elapsed_seconds_calculation(self):
        """Test elapsed_seconds property calculation."""
        stats = ParallelProcessingStats(
            start_time=100.0,
            end_time=150.0,
        )

        assert stats.elapsed_seconds == 50.0

    def test_elapsed_seconds_zero_when_not_complete(self):
        """Test elapsed_seconds is 0 when end_time not set."""
        stats = ParallelProcessingStats(start_time=100.0)

        assert stats.elapsed_seconds == 0.0

    def test_files_per_second_calculation(self):
        """Test files_per_second property calculation."""
        stats = ParallelProcessingStats(
            files_processed=100,
            start_time=1.0,  # Must be > 0 for elapsed_seconds to work
            end_time=11.0,
        )

        assert stats.files_per_second == 10.0

    def test_files_per_second_zero_when_no_elapsed(self):
        """Test files_per_second is 0 when no elapsed time."""
        stats = ParallelProcessingStats(files_processed=100)

        assert stats.files_per_second == 0.0

    def test_to_dict(self):
        """Test ParallelProcessingStats.to_dict()."""
        stats = ParallelProcessingStats(
            total_files=1000,
            files_processed=900,
            files_skipped=100,
            files_errored=0,
            start_time=1.0,  # Must be > 0 for elapsed_seconds to work
            end_time=11.0,
            concurrency_limit=50,
        )

        d = stats.to_dict()

        assert d["total_files"] == 1000
        assert d["files_processed"] == 900
        assert d["files_skipped"] == 100
        assert d["elapsed_seconds"] == 10.0
        assert d["files_per_second"] == 90.0
        assert d["concurrency_limit"] == 50


class TestDetermineAnalyzerType:
    """Tests for _determine_analyzer_type function."""

    def test_python_extension(self):
        """Test Python file detection."""
        from backend.api.codebase_analytics.scanner import _determine_analyzer_type

        analyzer_type, stat_key = _determine_analyzer_type(".py")

        assert analyzer_type == "python"
        assert stat_key == "python_files"

    def test_javascript_extension(self):
        """Test JavaScript file detection."""
        from backend.api.codebase_analytics.scanner import _determine_analyzer_type

        analyzer_type, stat_key = _determine_analyzer_type(".js")

        assert analyzer_type == "js"
        assert stat_key == "javascript_files"

    def test_vue_extension(self):
        """Test Vue file detection."""
        from backend.api.codebase_analytics.scanner import _determine_analyzer_type

        analyzer_type, stat_key = _determine_analyzer_type(".vue")

        assert analyzer_type == "js"
        assert stat_key == "vue_files"

    def test_markdown_extension(self):
        """Test Markdown (doc) file detection."""
        from backend.api.codebase_analytics.scanner import _determine_analyzer_type

        analyzer_type, stat_key = _determine_analyzer_type(".md")

        assert analyzer_type == "doc"
        assert stat_key == "doc_files"  # Actual key used in _FILE_TYPE_MAP

    def test_unknown_extension(self):
        """Test unknown extension returns None analyzer."""
        from backend.api.codebase_analytics.scanner import _determine_analyzer_type

        analyzer_type, stat_key = _determine_analyzer_type(".xyz")

        assert analyzer_type is None
        assert stat_key == "other_files"


class TestEnrichItemsWithMetadata:
    """Tests for _enrich_items_with_metadata function."""

    def test_adds_file_path_and_category(self):
        """Test items are enriched with file_path and file_category."""
        from backend.api.codebase_analytics.scanner import _enrich_items_with_metadata

        items = [{"name": "func1"}, {"name": "func2"}]
        enriched = _enrich_items_with_metadata(items, "src/module.py", "code")

        assert len(enriched) == 2
        assert enriched[0]["file_path"] == "src/module.py"
        assert enriched[0]["file_category"] == "code"
        assert enriched[0]["name"] == "func1"
        assert enriched[1]["file_path"] == "src/module.py"

    def test_does_not_modify_original(self):
        """Test original items are not modified."""
        from backend.api.codebase_analytics.scanner import _enrich_items_with_metadata

        items = [{"name": "func1"}]
        enriched = _enrich_items_with_metadata(items, "test.py", "code")

        assert "file_path" not in items[0]
        assert "file_path" in enriched[0]

    def test_empty_list(self):
        """Test empty list returns empty list."""
        from backend.api.codebase_analytics.scanner import _enrich_items_with_metadata

        enriched = _enrich_items_with_metadata([], "test.py", "code")

        assert enriched == []


class TestAggregateFromFileResult:
    """Tests for _aggregate_from_file_result function."""

    def test_skips_unprocessed_files(self):
        """Test that unprocessed files are skipped."""
        from backend.api.codebase_analytics.scanner import (
            _aggregate_from_file_result,
            _create_empty_analysis_results,
        )

        analysis_results = _create_empty_analysis_results()
        result = FileAnalysisResult(
            file_path=Path("/test/file.py"),
            relative_path="test/file.py",
            extension=".py",
            file_category="code",
            was_processed=False,
        )

        _aggregate_from_file_result(analysis_results, result)

        assert analysis_results["stats"]["total_files"] == 0
        assert "test/file.py" not in analysis_results["files"]

    def test_aggregates_processed_file(self):
        """Test processed file is aggregated correctly."""
        from backend.api.codebase_analytics.scanner import (
            _aggregate_from_file_result,
            _create_empty_analysis_results,
        )

        analysis_results = _create_empty_analysis_results()
        result = FileAnalysisResult(
            file_path=Path("/test/file.py"),
            relative_path="test/file.py",
            extension=".py",
            file_category="code",
            was_processed=True,
            functions=[{"name": "func1"}],
            classes=[{"name": "Class1"}],
            line_count=100,
            code_lines=80,
            stat_key="python_files",
        )

        _aggregate_from_file_result(analysis_results, result)

        assert analysis_results["stats"]["total_files"] == 1
        assert analysis_results["stats"]["python_files"] == 1
        assert analysis_results["stats"]["total_lines"] == 100
        assert analysis_results["stats"]["total_functions"] == 1
        assert analysis_results["stats"]["total_classes"] == 1
        assert len(analysis_results["all_functions"]) == 1
        assert len(analysis_results["all_classes"]) == 1

    def test_updates_category_stats(self):
        """Test file category stats are updated."""
        from backend.api.codebase_analytics.scanner import (
            _aggregate_from_file_result,
            _create_empty_analysis_results,
        )

        analysis_results = _create_empty_analysis_results()
        result = FileAnalysisResult(
            file_path=Path("/docs/README.md"),
            relative_path="docs/README.md",
            extension=".md",
            file_category="docs",
            was_processed=True,
            line_count=50,
            documentation_lines=50,
            stat_key="documentation_files",
        )

        _aggregate_from_file_result(analysis_results, result)

        assert analysis_results["stats"]["files_by_category"]["docs"] == 1
        assert analysis_results["stats"]["lines_by_category"]["docs"] == 50
        assert analysis_results["stats"]["documentation_lines"] == 50


class TestAggregateAllResults:
    """Tests for _aggregate_all_results function."""

    def test_aggregates_multiple_results(self):
        """Test multiple results are aggregated."""
        from backend.api.codebase_analytics.scanner import _aggregate_all_results

        results = [
            FileAnalysisResult(
                file_path=Path("/test/a.py"),
                relative_path="test/a.py",
                extension=".py",
                file_category="code",
                was_processed=True,
                functions=[{"name": "func_a"}],
                line_count=50,
                stat_key="python_files",
            ),
            FileAnalysisResult(
                file_path=Path("/test/b.py"),
                relative_path="test/b.py",
                extension=".py",
                file_category="code",
                was_processed=True,
                functions=[{"name": "func_b1"}, {"name": "func_b2"}],
                line_count=100,
                stat_key="python_files",
            ),
        ]

        aggregated = _aggregate_all_results(results)

        assert aggregated["stats"]["total_files"] == 2
        assert aggregated["stats"]["python_files"] == 2
        assert aggregated["stats"]["total_functions"] == 3
        assert len(aggregated["all_functions"]) == 3

    def test_skips_unprocessed_in_aggregation(self):
        """Test unprocessed results are skipped during aggregation."""
        from backend.api.codebase_analytics.scanner import _aggregate_all_results

        results = [
            FileAnalysisResult(
                file_path=Path("/test/a.py"),
                relative_path="test/a.py",
                extension=".py",
                file_category="code",
                was_processed=True,
                line_count=50,
                stat_key="python_files",
            ),
            FileAnalysisResult(
                file_path=Path("/test/b.py"),
                relative_path="test/b.py",
                extension=".py",
                file_category="code",
                was_processed=False,
                was_skipped_unchanged=True,
            ),
        ]

        aggregated = _aggregate_all_results(results)

        assert aggregated["stats"]["total_files"] == 1
        assert aggregated["stats"]["python_files"] == 1

    def test_empty_results_list(self):
        """Test empty results list returns valid empty structure."""
        from backend.api.codebase_analytics.scanner import _aggregate_all_results

        aggregated = _aggregate_all_results([])

        assert aggregated["stats"]["total_files"] == 0
        assert aggregated["all_functions"] == []
        assert aggregated["files"] == {}


class TestParallelProcessingConfig:
    """Tests for parallel processing configuration."""

    def test_parallel_file_concurrency_default(self):
        """Test default parallel file concurrency value."""
        from backend.api.codebase_analytics.scanner import PARALLEL_FILE_CONCURRENCY

        # Default is 50, should be between 1-200
        assert 1 <= PARALLEL_FILE_CONCURRENCY <= 200

    def test_parallel_mode_enabled_default(self):
        """Test parallel mode is enabled by default."""
        from backend.api.codebase_analytics.scanner import PARALLEL_MODE_ENABLED

        # Default is True
        assert PARALLEL_MODE_ENABLED is True


@pytest.mark.asyncio
class TestProcessFilesParallel:
    """Async tests for _process_files_parallel function."""

    async def test_empty_file_list(self):
        """Test processing empty file list returns empty results."""
        from backend.api.codebase_analytics.scanner import _process_files_parallel

        results = await _process_files_parallel(
            all_files=[],
            root_path_obj=Path("/test"),
            redis_client=None,
        )

        assert results == []

    async def test_processes_files_returns_results(self):
        """Test files are processed and results returned."""
        from backend.api.codebase_analytics.scanner import _process_files_parallel

        # Use actual files from the project
        project_root = Path("/home/kali/Desktop/AutoBot")
        test_files = list(project_root.glob("backend/api/codebase_analytics/*.py"))[:3]

        if not test_files:
            pytest.skip("No test files found")

        results = await _process_files_parallel(
            all_files=test_files,
            root_path_obj=project_root,
            redis_client=None,
        )

        assert len(results) == len(test_files)
        assert all(isinstance(r, FileAnalysisResult) for r in results)


@pytest.mark.asyncio
class TestAnalyzeSingleFile:
    """Async tests for _analyze_single_file function."""

    async def test_returns_file_analysis_result(self):
        """Test _analyze_single_file returns FileAnalysisResult."""
        from backend.api.codebase_analytics.scanner import _analyze_single_file

        project_root = Path("/home/kali/Desktop/AutoBot")
        test_file = project_root / "backend" / "api" / "codebase_analytics" / "types.py"

        if not test_file.exists():
            pytest.skip("Test file not found")

        result = await _analyze_single_file(
            file_path=test_file,
            root_path_obj=project_root,
            redis_client=None,
        )

        assert isinstance(result, FileAnalysisResult)
        assert result.extension == ".py"
        assert result.was_processed is True
        assert result.analyzer_type == "python"

    async def test_nonexistent_file_returns_base_result(self):
        """Test nonexistent file returns base result without processing."""
        from backend.api.codebase_analytics.scanner import _analyze_single_file

        project_root = Path("/home/kali/Desktop/AutoBot")
        fake_file = project_root / "nonexistent_file_12345.py"

        result = await _analyze_single_file(
            file_path=fake_file,
            root_path_obj=project_root,
            redis_client=None,
        )

        assert isinstance(result, FileAnalysisResult)
        assert result.was_processed is False
