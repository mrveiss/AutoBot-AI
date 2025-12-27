# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Configuration Duplication Detector

Detects duplicate configuration values across the codebase to enforce
single-source-of-truth principle (Issue #341).

Part of EPIC #217 - Advanced Code Intelligence Methods

Issue #554: Enhanced with Vector/Redis/LLM infrastructure:
- ChromaDB for semantic config pattern matching
- Redis for caching detection results
- LLM for detecting semantically equivalent config values
"""

import ast
import logging
import os
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Issue #554: Flag to enable semantic analysis infrastructure
SEMANTIC_ANALYSIS_AVAILABLE = False
SemanticAnalysisMixin = None

try:
    from src.code_intelligence.analytics_infrastructure import (
        SemanticAnalysisMixin as _SemanticAnalysisMixin,
    )
    SemanticAnalysisMixin = _SemanticAnalysisMixin
    SEMANTIC_ANALYSIS_AVAILABLE = True
except ImportError:
    logger.debug("SemanticAnalysisMixin not available - semantic features disabled")


# Values to ignore (too generic or acceptable duplicates)
IGNORE_VALUES = {
    # Boolean and None
    True, False, None,
    # Common integers
    0, 1, -1,
    # Empty strings
    "", " ",
    # HTTP status codes (acceptable duplicates)
    200, 201, 204, 400, 401, 403, 404, 405, 409, 422, 500, 502, 503,
}

# Source of truth directories (where constants should live)
SOURCE_DIRS = {"src/constants", "backend/constants"}


def _extract_constant_value(node: ast.AST) -> any:
    """Extract value from ast.Constant node (Issue #315: extracted)."""
    return node.value


def _extract_num_value(node: ast.AST) -> any:
    """Extract value from ast.Num node - Python 3.7 compat (Issue #315: extracted)."""
    return node.n


def _extract_str_value(node: ast.AST) -> any:
    """Extract value from ast.Str node - Python 3.7 compat (Issue #315: extracted)."""
    return node.s


def _extract_name_constant_value(node: ast.AST) -> any:
    """Extract value from ast.NameConstant node - Python 3.7 compat (Issue #315)."""
    return node.value


# AST node type to value extractor mapping (Issue #315: dictionary dispatch)
_AST_VALUE_EXTRACTORS = {
    ast.Constant: _extract_constant_value,
    ast.Num: _extract_num_value,
    ast.Str: _extract_str_value,
    ast.NameConstant: _extract_name_constant_value,
}


# Issue #554: Dynamic base class selection for semantic analysis support
_BaseClass = SemanticAnalysisMixin if SEMANTIC_ANALYSIS_AVAILABLE else object


class ConfigDuplicationDetector(_BaseClass):
    """
    Detects configuration value duplicates across codebase.

    Issue #554: Enhanced with optional Vector/Redis/LLM infrastructure:
    - use_semantic_analysis=True enables semantic config matching
    - Detects semantically equivalent but syntactically different values
    - Results cached in Redis for performance

    Usage:
        # Standard detection
        detector = ConfigDuplicationDetector(project_root)
        detector.scan_directory()
        report = detector.generate_report()

        # With semantic analysis (requires ChromaDB + Ollama)
        detector = ConfigDuplicationDetector(project_root, use_semantic_analysis=True)
        detector.scan_directory()
        report = await detector.generate_report_async()
    """

    def __init__(
        self,
        project_root: str,
        use_semantic_analysis: bool = False,
    ):
        """
        Initialize detector.

        Args:
            project_root: Root directory of the project
            use_semantic_analysis: Enable LLM-based semantic matching (Issue #554)
        """
        # Issue #554: Initialize semantic analysis infrastructure if enabled
        self.use_semantic_analysis = use_semantic_analysis and SEMANTIC_ANALYSIS_AVAILABLE

        if self.use_semantic_analysis:
            super().__init__()
            self._init_infrastructure(
                collection_name="config_pattern_vectors",
                use_llm=True,
                use_cache=True,
                redis_database="analytics",
            )

        self.project_root = Path(project_root)
        self.config_values: Dict[any, List[Tuple[str, int, str]]] = defaultdict(list)

    def _should_ignore_value(self, value: any) -> bool:
        """
        Check if value should be ignored.

        Args:
            value: Configuration value to check

        Returns:
            True if value should be ignored
        """
        if value in IGNORE_VALUES:
            return True

        # Ignore very short strings (likely not config)
        if isinstance(value, str) and len(value) <= 2:
            return True

        return False

    def _is_source_of_truth(self, filepath: str) -> bool:
        """
        Check if file is a source of truth for configuration.

        Args:
            filepath: Path to check

        Returns:
            True if file should be considered source of truth
        """
        for source_dir in SOURCE_DIRS:
            if source_dir in filepath:
                return True
        return False

    def _extract_value(self, node: ast.AST) -> any:
        """
        Extract literal value from AST node.

        Args:
            node: AST node to extract value from

        Returns:
            Extracted value or None

        Issue #315: Refactored to use dictionary dispatch for reduced nesting.
        """
        # Try dictionary dispatch for common node types
        extractor = _AST_VALUE_EXTRACTORS.get(type(node))
        if extractor:
            return extractor(node)

        # Handle negative numbers separately
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
            val = self._extract_value(node.operand)
            return -val if val is not None else None

        return None

    def _process_pydantic_field(self, node: ast.Call, filepath: str) -> None:
        """Extract config values from Pydantic Field() calls."""
        if not isinstance(node.func, ast.Name) or node.func.id != "Field":
            return
        for keyword in node.keywords:
            if keyword.arg != "default":
                continue
            value = self._extract_value(keyword.value)
            if value is not None and not self._should_ignore_value(value):
                self.config_values[value].append((filepath, node.lineno, "Pydantic Field"))

    def _is_dataclass(self, node: ast.ClassDef) -> bool:
        """Check if class has @dataclass decorator."""
        for dec in node.decorator_list:
            if isinstance(dec, ast.Name) and dec.id == "dataclass":
                return True
            if isinstance(dec, ast.Call) and isinstance(dec.func, ast.Name):
                if dec.func.id == "dataclass":
                    return True
        return False

    def _process_dataclass_fields(self, node: ast.ClassDef, filepath: str) -> None:
        """Extract config values from dataclass field defaults."""
        if not self._is_dataclass(node):
            return
        for item in node.body:
            if not isinstance(item, ast.AnnAssign) or item.value is None:
                continue
            value = self._extract_value(item.value)
            if value is None or self._should_ignore_value(value):
                continue
            target_name = item.target.id if isinstance(item.target, ast.Name) else "field"
            self.config_values[value].append((filepath, item.lineno, f"dataclass {target_name}"))

    def analyze_file(self, filepath: str) -> None:
        """
        Analyze a single Python file for config duplicates (Issue #327 optimization).

        Args:
            filepath: Path to file to analyze

        Optimized to perform single AST walk instead of dual walks.
        """
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()

            tree = ast.parse(content)

            # Single unified AST walk (Issue #327)
            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    self._process_pydantic_field(node, filepath)
                elif isinstance(node, ast.ClassDef):
                    self._process_dataclass_fields(node, filepath)

        except Exception as e:
            logger.debug("Could not analyze %s: %s", filepath, e)

    def scan_directory(self, directory: str = None) -> None:
        """
        Scan directory for Python files and analyze them.

        Args:
            directory: Directory to scan (defaults to project root)
        """
        if directory is None:
            directory = self.project_root

        dir_path = Path(directory)

        for py_file in dir_path.rglob("*.py"):
            # Skip test files and archived code
            if "test" in str(py_file) or "archive" in str(py_file):
                continue

            self.analyze_file(str(py_file))

    def find_duplicates(self) -> Dict[any, List[Dict]]:
        """
        Find configuration values that appear in multiple files.

        Returns:
            Dict mapping values to their occurrences with metadata
        """
        duplicates = {}

        for value, locations in self.config_values.items():
            if len(locations) > 1:
                # Check if any location is a source of truth
                source_locations = [loc for loc in locations if self._is_source_of_truth(loc[0])]
                duplicate_locations = [loc for loc in locations if not self._is_source_of_truth(loc[0])]

                if duplicate_locations:  # Only report if there are actual duplicates
                    duplicates[value] = {
                        "value": value,
                        "count": len(locations),
                        "sources": [
                            {"file": loc[0], "line": loc[1], "context": loc[2], "is_source": True}
                            for loc in source_locations
                        ],
                        "duplicates": [
                            {"file": loc[0], "line": loc[1], "context": loc[2], "is_source": False}
                            for loc in duplicate_locations
                        ],
                    }

        return duplicates

    def generate_report(self) -> str:
        """
        Generate a human-readable report of config duplicates.

        Returns:
            Formatted report string
        """
        duplicates = self.find_duplicates()

        if not duplicates:
            return "✅ No configuration duplicates found!"

        report = ["Configuration Duplication Report", "=" * 60, ""]

        # Sort by number of duplicates (most problematic first)
        sorted_dups = sorted(
            duplicates.items(), key=lambda x: len(x[1]["duplicates"]), reverse=True
        )

        for value, data in sorted_dups:
            report.append(f"\nValue: {repr(value)} ({len(data['duplicates'])} duplicates)")

            # Show sources of truth
            if data["sources"]:
                report.append("  ✅ SOURCE OF TRUTH:")
                for source in data["sources"]:
                    report.append(f"     - {source['file']}:{source['line']} ({source['context']})")

            # Show duplicates
            report.append("  ❌ DUPLICATES:")
            for dup in data["duplicates"]:
                report.append(f"     - {dup['file']}:{dup['line']} ({dup['context']})")

        report.append(f"\n\nTotal: {len(duplicates)} configuration values with duplicates")
        return "\n".join(report)

    # Issue #554: Async methods for semantic analysis
    async def find_duplicates_async(self) -> Dict[str, any]:
        """
        Find duplicates with optional caching.

        Issue #554: Async version with Redis caching support.
        """
        if self.use_semantic_analysis:
            cache_key = f"config_dups:{hash(str(self.project_root))}"
            cached = await self._get_cached_result(cache_key, prefix="config_detector")
            if cached:
                return cached

        result = self.find_duplicates()

        if self.use_semantic_analysis:
            await self._cache_result(cache_key, result, prefix="config_detector", ttl=1800)

        return result

    def get_infrastructure_metrics(self) -> Dict[str, Any]:
        """Get infrastructure metrics for monitoring (Issue #554)."""
        if self.use_semantic_analysis:
            return self._get_infrastructure_metrics()
        return {}


def detect_config_duplicates(project_root: str) -> Dict[str, any]:
    """
    Main entry point for config duplication detection.

    Args:
        project_root: Root directory of project

    Returns:
        Dict with detection results and report
    """
    detector = ConfigDuplicationDetector(project_root)

    # Scan key directories
    detector.scan_directory(os.path.join(project_root, "src"))
    detector.scan_directory(os.path.join(project_root, "backend"))

    duplicates = detector.find_duplicates()
    report = detector.generate_report()

    return {
        "duplicates_found": len(duplicates),
        "duplicates": duplicates,
        "report": report,
    }


if __name__ == "__main__":
    # Test the detector
    import sys

    project_root = sys.argv[1] if len(sys.argv) > 1 else "/home/kali/Desktop/AutoBot"
    result = detect_config_duplicates(project_root)

    print(result["report"])
    print(f"\nFound {result['duplicates_found']} configuration values with duplicates")
