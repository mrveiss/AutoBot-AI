# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Pattern Extractor Tests (Issue #903)

Tests for code pattern extraction from codebase.
"""

import ast
import tempfile
from pathlib import Path

import pytest
from backend.services.pattern_extractor import PatternExtractor


@pytest.fixture
def temp_codebase():
    """Create temporary codebase for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        base = Path(tmpdir)

        # Create directory structure
        backend = base / "autobot-user-backend"
        backend.mkdir()

        # Create sample Python file
        sample_py = backend / "sample.py"
        sample_py.write_text(
            '''
"""Sample module for testing."""

import logging
from typing import Dict, List

logger = logging.getLogger(__name__)


async def get_user(user_id: int) -> Dict:
    """Fetch user by ID."""
    try:
        # Simulate database call
        return {"id": user_id, "name": "Test User"}
    except KeyError as e:
        logger.error(f"User not found: {e}")
        return {}


def process_data(items: List[str]) -> int:
    """Process list of items."""
    return len(items)


class UserService:
    """User service class."""

    def __init__(self):
        self.cache = {}

    async def create_user(self, name: str) -> Dict:
        """Create new user."""
        user = {"name": name}
        self.cache[name] = user
        return user
'''
        )

        # Create sample TypeScript file
        frontend = base / "autobot-user-frontend" / "src"
        frontend.mkdir(parents=True)

        sample_ts = frontend / "composable.ts"
        sample_ts.write_text(
            """
export interface User {
  id: number
  name: string
}

export function useUserStore(): {
  users: Ref<User[]>
  fetchUsers: () => Promise<void>
} {
  const users = ref<User[]>([])

  async function fetchUsers() {
    users.value = await ApiClient.get('/users')
  }

  return { users, fetchUsers }
}
"""
        )

        yield base


def test_pattern_extractor_initialization(temp_codebase):
    """Test PatternExtractor initialization."""
    extractor = PatternExtractor(base_path=str(temp_codebase))
    assert extractor.base_path == temp_codebase
    assert extractor.patterns is not None


def test_extract_python_function_patterns(temp_codebase):
    """Test extraction of Python function patterns."""
    extractor = PatternExtractor(base_path=str(temp_codebase))
    extractor._extract_python_patterns()

    # Should find functions
    function_patterns = extractor.patterns.get("function", [])
    assert len(function_patterns) >= 2  # get_user, process_data, create_user

    # Check function signature extraction
    signatures = [p["signature"] for p in function_patterns]
    assert any("get_user" in sig for sig in signatures)
    assert any("process_data" in sig for sig in signatures)


def test_extract_python_error_handling_patterns(temp_codebase):
    """Test extraction of error handling patterns."""
    extractor = PatternExtractor(base_path=str(temp_codebase))
    extractor._extract_python_patterns()

    # Should find try/except pattern
    error_patterns = extractor.patterns.get("error_handling", [])
    assert len(error_patterns) >= 1

    # Check exception type
    pattern = error_patterns[0]
    assert pattern["pattern_type"] == "error_handling"
    assert "KeyError" in pattern["category"]


def test_extract_async_function_patterns(temp_codebase):
    """Test extraction of async function patterns."""
    extractor = PatternExtractor(base_path=str(temp_codebase))
    extractor._extract_python_patterns()

    function_patterns = extractor.patterns.get("function", [])

    # Find async functions
    async_patterns = [p for p in function_patterns if p["context"].get("is_async")]
    assert len(async_patterns) >= 1  # get_user and create_user are async


def test_categorize_function():
    """Test function categorization logic."""
    extractor = PatternExtractor()

    # Test async function
    async_node = ast.parse("async def fetch_data(): pass").body[0]
    category = extractor._categorize_function(
        async_node, Path("/test/redis_service.py")
    )
    assert category == "redis"

    # Test test function
    test_node = ast.parse("def test_something(): pass").body[0]
    category = extractor._categorize_function(test_node, Path("/test/test.py"))
    assert category == "test"

    # Test private function
    private_node = ast.parse("def _helper(): pass").body[0]
    category = extractor._categorize_function(private_node, Path("/test/utils.py"))
    assert category == "private"


def test_extract_typescript_composable_patterns(temp_codebase):
    """Test extraction of Vue composable patterns."""
    extractor = PatternExtractor(base_path=str(temp_codebase))
    extractor._extract_typescript_vue_patterns()

    # Should find composable function
    composable_patterns = extractor.patterns.get("composable", [])
    assert len(composable_patterns) >= 1

    pattern = composable_patterns[0]
    assert pattern["pattern_type"] == "composable"
    assert pattern["language"] == "typescript"
    assert "useUserStore" in pattern["signature"]


def test_extract_typescript_interface_patterns(temp_codebase):
    """Test extraction of TypeScript interface patterns."""
    extractor = PatternExtractor(base_path=str(temp_codebase))
    extractor._extract_typescript_vue_patterns()

    # Should find interface
    interface_patterns = extractor.patterns.get("interface", [])
    assert len(interface_patterns) >= 1

    pattern = interface_patterns[0]
    assert pattern["pattern_type"] == "interface"
    assert pattern["language"] == "typescript"
    assert "User" in pattern["signature"]


def test_extract_from_codebase_all_languages(temp_codebase):
    """Test extracting patterns from all languages."""
    extractor = PatternExtractor(base_path=str(temp_codebase))
    patterns = extractor.extract_from_codebase(
        languages=["python", "typescript", "vue"]
    )

    # Should have multiple pattern types
    assert len(patterns) > 0
    assert "function" in patterns or "composable" in patterns


def test_extract_from_codebase_python_only(temp_codebase):
    """Test extracting patterns from Python only."""
    extractor = PatternExtractor(base_path=str(temp_codebase))
    patterns = extractor.extract_from_codebase(languages=["python"])

    # Should only have Python patterns
    for pattern_list in patterns.values():
        for pattern in pattern_list:
            assert pattern["language"] == "python"


def test_get_statistics(temp_codebase):
    """Test pattern extraction statistics."""
    extractor = PatternExtractor(base_path=str(temp_codebase))
    extractor.extract_from_codebase()

    stats = extractor.get_statistics()

    # Should have counts for each pattern type
    assert isinstance(stats, dict)
    assert sum(stats.values()) > 0


def test_pattern_context_includes_metadata(temp_codebase):
    """Test that patterns include context metadata."""
    extractor = PatternExtractor(base_path=str(temp_codebase))
    extractor._extract_python_patterns()

    function_patterns = extractor.patterns.get("function", [])
    if function_patterns:
        pattern = function_patterns[0]

        # Check required fields
        assert "pattern_type" in pattern
        assert "language" in pattern
        assert "signature" in pattern
        assert "file_path" in pattern
        assert "line_number" in pattern
        assert "context" in pattern

        # Check context has metadata
        context = pattern["context"]
        assert "decorators" in context
        assert "is_async" in context


def test_skip_test_files():
    """Test that test files are skipped during extraction."""
    with tempfile.TemporaryDirectory() as tmpdir:
        base = Path(tmpdir)
        backend = base / "autobot-user-backend"
        backend.mkdir()

        # Create test file
        test_file = backend / "test_sample.py"
        test_file.write_text("def test_function(): pass")

        extractor = PatternExtractor(base_path=str(base))
        extractor._extract_python_patterns()

        # Test files should be skipped
        function_patterns = extractor.patterns.get("function", [])
        test_file_patterns = [
            p for p in function_patterns if "test_" in str(p["file_path"])
        ]
        assert len(test_file_patterns) == 0


def test_skip_long_functions():
    """Test that very long functions are skipped."""
    with tempfile.TemporaryDirectory() as tmpdir:
        base = Path(tmpdir)
        backend = base / "autobot-user-backend"
        backend.mkdir()

        # Create file with long function
        long_func = backend / "long.py"
        code = "def very_long_function():\n" + "    pass\n" * 1000
        long_func.write_text(code)

        extractor = PatternExtractor(base_path=str(base))
        extractor._extract_python_patterns()

        # Long function should be skipped
        function_patterns = extractor.patterns.get("function", [])
        long_patterns = [
            p for p in function_patterns if "very_long_function" in p["signature"]
        ]
        assert len(long_patterns) == 0
