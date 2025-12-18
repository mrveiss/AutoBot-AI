# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Diff Generator

Issue #381: Extracted from llm_code_generator.py god class refactoring.
Contains DiffGenerator for unified diff generation between code versions.
"""

import difflib
from typing import Dict


class DiffGenerator:
    """Generates unified diff between original and modified code."""

    @classmethod
    def generate_diff(
        cls,
        original: str,
        modified: str,
        filename: str = "code.py",
        context_lines: int = 3,
    ) -> str:
        """
        Generate a unified diff between original and modified code.

        Args:
            original: Original code
            modified: Modified code
            filename: Filename for diff header
            context_lines: Number of context lines

        Returns:
            Unified diff string
        """
        original_lines = original.splitlines(keepends=True)
        modified_lines = modified.splitlines(keepends=True)

        diff = difflib.unified_diff(
            original_lines,
            modified_lines,
            fromfile=f"a/{filename}",
            tofile=f"b/{filename}",
            n=context_lines,
        )

        return "".join(diff)

    @classmethod
    def generate_side_by_side(
        cls, original: str, modified: str, width: int = 80
    ) -> str:
        """Generate side-by-side comparison."""
        original_lines = original.splitlines()
        modified_lines = modified.splitlines()

        max_len = max(len(original_lines), len(modified_lines))
        half_width = (width - 3) // 2

        result = []
        result.append("=" * width)
        result.append(f"{'ORIGINAL':<{half_width}} | {'MODIFIED':<{half_width}}")
        result.append("=" * width)

        for i in range(max_len):
            orig = original_lines[i] if i < len(original_lines) else ""
            mod = modified_lines[i] if i < len(modified_lines) else ""

            # Truncate if needed
            orig = orig[:half_width].ljust(half_width)
            mod = mod[:half_width].ljust(half_width)

            marker = " " if orig.strip() == mod.strip() else "*"
            result.append(f"{orig} {marker} {mod}")

        result.append("=" * width)
        return "\n".join(result)

    @classmethod
    def count_changes(cls, original: str, modified: str) -> Dict[str, int]:
        """Count additions, deletions, and modifications."""
        original_lines = set(original.splitlines())
        modified_lines = set(modified.splitlines())

        added = len(modified_lines - original_lines)
        removed = len(original_lines - modified_lines)
        unchanged = len(original_lines & modified_lines)

        return {
            "added": added,
            "removed": removed,
            "unchanged": unchanged,
            "total_changes": added + removed,
        }
