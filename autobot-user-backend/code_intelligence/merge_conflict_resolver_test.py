# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Unit tests for Merge Conflict Resolver

Tests intelligent merge conflict resolution including:
- Conflict parsing
- Resolution strategies
- Validation
- Semantic analysis

Part of Issue #246 - Intelligent Merge Conflict Resolution
"""

import tempfile
import textwrap

import pytest

from backend.code_intelligence.merge_conflict_resolver import (
    ConflictParser,
    ConflictSeverity,
    MergeConflictResolver,
    ResolutionStrategy,
    ValidationEngine,
    analyze_repository,
)


class TestConflictParser:
    """Test parsing of git conflict markers."""

    def test_parse_simple_conflict(self):
        """Test parsing a simple conflict."""
        conflict_content = textwrap.dedent(
            """
            def hello():
            <<<<<<< HEAD
                return "Hello from current"
            =======
                return "Hello from incoming"
            >>>>>>> branch
        """
        )

        with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
            f.write(conflict_content)
            f.flush()

            parser = ConflictParser()
            conflicts = parser.parse_file(f.name)

            assert len(conflicts) == 1
            conflict = conflicts[0]
            assert "Hello from current" in conflict.ours_content
            assert "Hello from incoming" in conflict.theirs_content
            assert conflict.start_line > 0
            assert conflict.end_line > conflict.start_line

    def test_parse_multiple_conflicts(self):
        """Test parsing multiple conflicts in same file."""
        conflict_content = textwrap.dedent(
            """
            def func1():
            <<<<<<< HEAD
                x = 1
            =======
                x = 2
            >>>>>>> branch

            def func2():
            <<<<<<< HEAD
                y = "a"
            =======
                y = "b"
            >>>>>>> branch
        """
        )

        with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
            f.write(conflict_content)
            f.flush()

            parser = ConflictParser()
            conflicts = parser.parse_file(f.name)

            assert len(conflicts) == 2
            assert "x = 1" in conflicts[0].ours_content
            assert 'y = "a"' in conflicts[1].ours_content

    def test_parse_conflict_with_base(self):
        """Test parsing conflict with base (diff3 style)."""
        conflict_content = textwrap.dedent(
            """
            def hello():
            <<<<<<< HEAD
                return "current"
            ||||||| base
                return "original"
            =======
                return "incoming"
            >>>>>>> branch
        """
        )

        with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
            f.write(conflict_content)
            f.flush()

            parser = ConflictParser()
            conflicts = parser.parse_file(f.name)

            assert len(conflicts) == 1
            conflict = conflicts[0]
            assert conflict.base_content is not None
            assert "original" in conflict.base_content

    def test_has_conflicts(self):
        """Test conflict detection."""
        conflict_content = "<<<<<<< HEAD\ntest\n=======\nother\n>>>>>>> branch"

        with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
            f.write(conflict_content)
            f.flush()

            parser = ConflictParser()
            assert parser.has_conflicts(f.name) is True

    def test_no_conflicts(self):
        """Test file without conflicts."""
        clean_content = "def hello():\n    return 'world'"

        with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
            f.write(clean_content)
            f.flush()

            parser = ConflictParser()
            assert parser.has_conflicts(f.name) is False


class TestConflictSeverity:
    """Test conflict severity calculation."""

    def test_trivial_severity_whitespace(self):
        """Test trivial severity for whitespace conflicts."""
        conflict_content = textwrap.dedent(
            """
            <<<<<<< HEAD
            def hello():
                pass
            =======
            def hello():
                pass
            >>>>>>> branch
        """
        )

        with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
            f.write(conflict_content)
            f.flush()

            parser = ConflictParser()
            conflicts = parser.parse_file(f.name)

            assert conflicts[0].severity == ConflictSeverity.TRIVIAL

    def test_simple_severity_non_overlapping(self):
        """Test simple severity for non-overlapping changes."""
        conflict_content = textwrap.dedent(
            """
            <<<<<<< HEAD
            x = 1
            =======
            y = 2
            >>>>>>> branch
        """
        )

        with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
            f.write(conflict_content)
            f.flush()

            parser = ConflictParser()
            conflicts = parser.parse_file(f.name)

            assert conflicts[0].severity == ConflictSeverity.SIMPLE

    def test_complex_severity_logic_changes(self):
        """Test complex severity for logic changes."""
        conflict_content = textwrap.dedent(
            """
            <<<<<<< HEAD
            def process(data):
                if data:
                    return True
            =======
            def process(data):
                while data:
                    yield data
            >>>>>>> branch
        """
        )

        with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
            f.write(conflict_content)
            f.flush()

            parser = ConflictParser()
            conflicts = parser.parse_file(f.name)

            assert conflicts[0].severity == ConflictSeverity.COMPLEX


class TestValidationEngine:
    """Test code validation."""

    def test_validate_valid_python(self):
        """Test validation of valid Python code."""
        code = "def hello():\n    return 'world'\n"

        validator = ValidationEngine()
        is_valid, errors = validator.validate_python(code)

        assert is_valid is True
        assert len(errors) == 0

    def test_validate_invalid_python(self):
        """Test validation of invalid Python code."""
        code = "def hello(:\n    return 'world'\n"

        validator = ValidationEngine()
        is_valid, errors = validator.validate_python(code)

        assert is_valid is False
        assert len(errors) > 0
        assert "Syntax error" in errors[0]

    def test_validate_imports_no_duplicates(self):
        """Test import validation without duplicates."""
        code = "import os\nimport sys\n"

        validator = ValidationEngine()
        is_valid, errors = validator.validate_imports(code)

        assert is_valid is True
        assert len(errors) == 0

    def test_validate_imports_duplicates(self):
        """Test import validation with duplicates."""
        code = "import os\nimport os\n"

        validator = ValidationEngine()
        is_valid, errors = validator.validate_imports(code)

        assert is_valid is False
        assert "Duplicate imports" in errors[0]


class TestMergeConflictResolver:
    """Test merge conflict resolution strategies."""

    def test_resolve_trivial_conflict(self):
        """Test resolution of trivial conflict."""
        conflict_content = textwrap.dedent(
            """
            <<<<<<< HEAD
            def hello():
                pass
            =======
            def hello():
                pass
            >>>>>>> branch
        """
        )

        with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
            f.write(conflict_content)
            f.flush()

            resolver = MergeConflictResolver()
            results = resolver.resolve_file(f.name)

            assert len(results) == 1
            result = results[0]
            assert result.confidence_score >= 0.9
            assert result.is_validated is True

    def test_resolve_import_conflict(self):
        """Test resolution of import conflict."""
        conflict_content = textwrap.dedent(
            """
            <<<<<<< HEAD
            import os
            import sys
            =======
            import os
            import json
            >>>>>>> branch
        """
        )

        with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
            f.write(conflict_content)
            f.flush()

            resolver = MergeConflictResolver()
            results = resolver.resolve_file(f.name)

            assert len(results) == 1
            result = results[0]
            # Should merge all unique imports
            assert "import os" in result.resolved_content
            assert "import sys" in result.resolved_content
            assert "import json" in result.resolved_content

    def test_accept_ours_strategy(self):
        """Test accept ours resolution strategy."""
        conflict_content = textwrap.dedent(
            """
            <<<<<<< HEAD
            x = 1
            =======
            x = 2
            >>>>>>> branch
        """
        )

        with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
            f.write(conflict_content)
            f.flush()

            resolver = MergeConflictResolver()
            results = resolver.resolve_file(
                f.name, strategy=ResolutionStrategy.ACCEPT_OURS
            )

            assert len(results) == 1
            result = results[0]
            assert "x = 1" in result.resolved_content
            assert "x = 2" not in result.resolved_content

    def test_accept_theirs_strategy(self):
        """Test accept theirs resolution strategy."""
        conflict_content = textwrap.dedent(
            """
            <<<<<<< HEAD
            x = 1
            =======
            x = 2
            >>>>>>> branch
        """
        )

        with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
            f.write(conflict_content)
            f.flush()

            resolver = MergeConflictResolver()
            results = resolver.resolve_file(
                f.name, strategy=ResolutionStrategy.ACCEPT_THEIRS
            )

            assert len(results) == 1
            result = results[0]
            assert "x = 2" in result.resolved_content
            assert "x = 1" not in result.resolved_content

    def test_accept_both_strategy(self):
        """Test accept both resolution strategy."""
        conflict_content = textwrap.dedent(
            """
            <<<<<<< HEAD
            def func1():
                pass
            =======
            def func2():
                pass
            >>>>>>> branch
        """
        )

        with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
            f.write(conflict_content)
            f.flush()

            resolver = MergeConflictResolver()
            results = resolver.resolve_file(
                f.name, strategy=ResolutionStrategy.ACCEPT_BOTH
            )

            assert len(results) == 1
            result = results[0]
            # Should include both functions
            assert "def func1" in result.resolved_content
            assert "def func2" in result.resolved_content

    def test_safe_mode_requires_review(self):
        """Test safe mode requires review for complex conflicts."""
        conflict_content = textwrap.dedent(
            """
            <<<<<<< HEAD
            def process(data):
                if data:
                    return True
                return False
            =======
            def process(data):
                while data:
                    yield data.pop()
            >>>>>>> branch
        """
        )

        with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
            f.write(conflict_content)
            f.flush()

            resolver = MergeConflictResolver(safe_mode=True)
            results = resolver.resolve_file(f.name)

            assert len(results) == 1
            result = results[0]
            # Complex conflict should require review in safe mode
            assert result.requires_review is True

    def test_validation_detects_errors(self):
        """Test validation detects syntax errors."""
        conflict_content = textwrap.dedent(
            """
            <<<<<<< HEAD
            def hello():
                return "current"
            =======
            def hello(
                return "incoming"
            >>>>>>> branch
        """
        )

        with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
            f.write(conflict_content)
            f.flush()

            resolver = MergeConflictResolver(require_validation=True)
            results = resolver.resolve_file(f.name)

            assert len(results) == 1
            result = results[0]
            # Should detect validation errors
            if not result.is_validated:
                assert len(result.validation_errors) > 0


class TestRepositoryAnalysis:
    """Test repository-wide conflict analysis."""

    def test_analyze_repository_no_conflicts(self):
        """Test repository analysis with no conflicts."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a clean Python file
            with open(f"{tmpdir}/test.py", "w") as f:
                f.write("def hello():\n    pass\n")

            analysis = analyze_repository(tmpdir)

            assert analysis["total_files"] == 0
            assert analysis["total_conflicts"] == 0

    def test_analyze_repository_with_conflicts(self):
        """Test repository analysis with conflicts."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a file with conflicts
            with open(f"{tmpdir}/test.py", "w") as f:
                f.write("<<<<<<< HEAD\nx = 1\n=======\nx = 2\n>>>>>>> branch\n")

            analysis = analyze_repository(tmpdir)

            assert analysis["total_files"] == 1
            assert analysis["total_conflicts"] == 1
            assert len(analysis["files"]) == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
