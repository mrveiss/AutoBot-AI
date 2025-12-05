# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Configuration Duplication Detector

Detects duplicate configuration values across the codebase to enforce
single-source-of-truth principle (Issue #341).
"""

import ast
import logging
import os
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Tuple

logger = logging.getLogger(__name__)


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


class ConfigDuplicationDetector:
    """Detects configuration value duplicates across codebase."""

    def __init__(self, project_root: str):
        """
        Initialize detector.

        Args:
            project_root: Root directory of the project
        """
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
        """
        if isinstance(node, ast.Constant):
            return node.value
        elif isinstance(node, ast.Num):  # Python 3.7 compat
            return node.n
        elif isinstance(node, ast.Str):  # Python 3.7 compat
            return node.s
        elif isinstance(node, ast.NameConstant):  # Python 3.7 compat
            return node.value
        elif isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
            # Negative numbers
            if isinstance(node.operand, (ast.Num, ast.Constant)):
                val = self._extract_value(node.operand)
                return -val if val is not None else None
        return None

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

            # Single unified AST walk (Issue #327) - extract both Pydantic and dataclass defaults
            for node in ast.walk(tree):
                # Check for Pydantic Field(...) calls
                if isinstance(node, ast.Call):
                    if isinstance(node.func, ast.Name) and node.func.id == "Field":
                        # Extract Field(default=X) keyword argument
                        for keyword in node.keywords:
                            if keyword.arg == "default":
                                value = self._extract_value(keyword.value)
                                if value is not None and not self._should_ignore_value(value):
                                    self.config_values[value].append(
                                        (filepath, node.lineno, "Pydantic Field")
                                    )

                # Check for dataclass definitions
                if isinstance(node, ast.ClassDef):
                    # Check if it has @dataclass decorator
                    has_dataclass = any(
                        isinstance(dec, ast.Name) and dec.id == "dataclass"
                        or (isinstance(dec, ast.Call) and isinstance(dec.func, ast.Name) and dec.func.id == "dataclass")
                        for dec in node.decorator_list
                    )

                    if has_dataclass:
                        # Extract field defaults
                        for item in node.body:
                            if isinstance(item, ast.AnnAssign) and item.value:
                                value = self._extract_value(item.value)
                                if value is not None and not self._should_ignore_value(value):
                                    target_name = item.target.id if isinstance(item.target, ast.Name) else "field"
                                    self.config_values[value].append(
                                        (filepath, item.lineno, f"dataclass {target_name}")
                                    )

        except Exception as e:
            logger.debug(f"Could not analyze {filepath}: {e}")

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
