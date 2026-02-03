# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Pattern Detector Module

Detects design patterns in code.
Extracted from ArchitecturalPatternAnalyzer as part of Issue #394.
"""

import ast
import logging
import re
from pathlib import Path
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


class PatternDetector:
    """
    Detector for design patterns.

    Identifies common design patterns like Singleton, Factory, Observer, etc.

    Example:
        >>> detector = PatternDetector()
        >>> patterns = detector.detect_class_patterns(class_node, content)
    """

    # Design patterns to detect
    PATTERN_SIGNATURES = {
        "singleton": [
            (r"class\s+\w+.*?:\s*\n.*?__new__\s*\(.*?\)", "Singleton pattern detected"),
            (r"_instance\s*=\s*None", "Singleton instance variable"),
        ],
        "factory": [
            (r"def\s+create_\w+\s*\(", "Factory method pattern"),
            (r"class\s+\w*Factory\w*", "Factory class pattern"),
        ],
        "observer": [
            (r"def\s+(?:add_|remove_)(?:observer|listener)", "Observer pattern"),
            (r"def\s+notify\s*\(", "Observer notification method"),
        ],
        "decorator": [
            (r"@\w+", "Decorator pattern usage"),
            (r"def\s+\w+\s*\(.*?\).*?->.*?:", "Potential decorator"),
        ],
        "adapter": [
            (r"class\s+\w*Adapter\w*", "Adapter pattern"),
            (r"def\s+adapt\s*\(", "Adapter method"),
        ],
        "facade": [
            (r"class\s+\w*Facade\w*", "Facade pattern"),
            (r"def\s+simplified_\w+", "Facade method"),
        ],
    }

    def __init__(self, pattern_signatures: Dict[str, List] = None):
        """
        Initialize the pattern detector.

        Args:
            pattern_signatures: Custom pattern signatures (optional)
        """
        self.pattern_signatures = pattern_signatures or self.PATTERN_SIGNATURES

    def detect_class_patterns(self, node: ast.ClassDef, content: str) -> List[str]:
        """
        Detect design patterns in a class.

        Args:
            node: AST ClassDef node
            content: Full source code content

        Returns:
            List of detected pattern names
        """
        patterns = []
        class_content = ast.unparse(node) if hasattr(ast, "unparse") else str(node)

        # Check each pattern
        for pattern_name, pattern_sigs in self.pattern_signatures.items():
            for pattern, description in pattern_sigs:
                if re.search(pattern, class_content, re.MULTILINE | re.IGNORECASE):
                    if pattern_name not in patterns:
                        patterns.append(pattern_name)

        return patterns

    async def detect_patterns(
        self, root_path: str, file_patterns: List[str], skip_check: callable = None
    ) -> List[Dict[str, Any]]:
        """
        Detect design patterns across the codebase.

        Args:
            root_path: Root directory path
            file_patterns: Glob patterns for files to scan
            skip_check: Optional function to check if file should be skipped

        Returns:
            List of detected pattern dictionaries
        """
        detected_patterns = []
        root = Path(root_path)

        for pattern in file_patterns:
            for file_path in root.glob(pattern):
                await self._scan_file_for_patterns(
                    file_path, detected_patterns, skip_check
                )

        return detected_patterns

    async def _scan_file_for_patterns(
        self,
        file_path: Path,
        detected_patterns: List[Dict[str, Any]],
        skip_check: callable = None,
    ) -> None:
        """Scan a single file for design patterns."""
        if not file_path.is_file():
            return
        if skip_check and skip_check(file_path):
            return

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()

            self._find_patterns_in_content(file_path, content, detected_patterns)
        except Exception as e:
            logger.warning(f"Failed to scan patterns in {file_path}: {e}")

    def _find_patterns_in_content(
        self,
        file_path: Path,
        content: str,
        detected_patterns: List[Dict[str, Any]],
    ) -> None:
        """Find pattern matches in file content."""
        for pattern_name, pattern_sigs in self.pattern_signatures.items():
            for regex_pattern, description in pattern_sigs:
                self._match_pattern(
                    file_path,
                    content,
                    pattern_name,
                    regex_pattern,
                    description,
                    detected_patterns,
                )

    def _match_pattern(
        self,
        file_path: Path,
        content: str,
        pattern_name: str,
        regex_pattern: str,
        description: str,
        detected_patterns: List[Dict[str, Any]],
    ) -> None:
        """Match a single pattern and record matches."""
        for match in re.finditer(regex_pattern, content, re.MULTILINE | re.IGNORECASE):
            line_num = content[: match.start()].count("\n") + 1
            detected_patterns.append(
                {
                    "pattern": pattern_name,
                    "file": str(file_path),
                    "line": line_num,
                    "description": description,
                    "code_snippet": match.group(0)[:100],
                }
            )


__all__ = ["PatternDetector"]
