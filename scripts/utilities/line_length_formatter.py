#!/usr/bin/env python3
"""
Reusable E501 Line Length Fixer

A utility to automatically fix E501 violations (lines too long) by intelligently
splitting long strings at natural boundaries.

Author: mrveiss
Copyright: © 2025 mrveiss
Related: Issue #175 - Code Quality Enforcement
"""

import re
import sys
from pathlib import Path
from typing import List, Tuple


class E501Fixer:
    """Intelligently fix E501 violations by splitting long strings."""

    def __init__(self, max_length: int = 100):
        """
        Initialize fixer with max line length.

        Args:
            max_length: Maximum characters per line (default: 100)
        """
        self.max_length = max_length

    def find_split_point(self, text: str, max_pos: int) -> int:
        """
        Find optimal split point in text before max_pos.

        Prioritizes natural boundaries:
        1. ", " (comma-space)
        2. ": " (colon-space)
        3. " - " (dash-space)
        4. " and " / " or " (conjunctions)
        5. " " (any space)

        Args:
            text: String to find split point in
            max_pos: Maximum position to split at

        Returns:
            Position to split at, or -1 if no good split found
        """
        # Search patterns in order of preference
        patterns = [", ", ": ", " - ", " and ", " or ", " with ", " for ", " "]

        # Search backward from max_pos
        search_start = max(0, max_pos - 30)
        search_end = min(max_pos + 10, len(text))

        for pattern in patterns:
            pos = text.rfind(pattern, search_start, search_end)
            if pos != -1:
                return pos + len(pattern)

        # Fallback to any space
        pos = text.rfind(" ", search_start, search_end)
        return pos + 1 if pos != -1 else -1

    def split_long_logger(self, line: str, indent: str) -> List[str]:
        """
        Split a long logger statement into multiple lines.

        Args:
            line: Logger line to split
            indent: Indentation string to use

        Returns:
            List of split lines, or original line if can't split
        """
        # Match logger.xxx("...") pattern
        match = re.match(r'(\s*)(logger\.\w+\(\s*)(f?"[^"]+")(\s*\))', line)
        if not match:
            return [line]

        leading_space, logger_call, fstring, closing = match.groups()

        # Extract string content
        is_fstring = fstring.startswith('f"')
        content = fstring[2:-1] if is_fstring else fstring[1:-1]

        # If not too long, don't split
        if len(line.rstrip()) <= self.max_length:
            return [line]

        # Find split point
        target = self.max_length - len(leading_space) - len(logger_call) - (3 if is_fstring else 2)
        split_pos = self.find_split_point(content, target)

        if split_pos == -1 or split_pos < 20:
            return [line]  # Can't split reasonably

        # Split into two parts
        part1 = content[:split_pos].rstrip()
        part2 = content[split_pos:].lstrip()

        prefix = '"' if is_fstring else '"'

        return [
            f'{leading_space}{logger_call}\n',
            f'{leading_space}    {prefix}{part1}"\n',
            f'{leading_space}    {prefix}{part2}"\n',
            f'{leading_space}{closing}\n'
        ]

    def split_long_string(self, line: str, indent: str) -> List[str]:
        """
        Split a long string assignment or literal.

        Args:
            line: Line with long string
            indent: Indentation string

        Returns:
            List of split lines, or original line if can't split
        """
        # Match string assignment: var = "..." or var = "..."
        match = re.match(r'(\s*)(\w+\s*=\s*)(f?"[^"]+")(\s*)', line)
        if not match:
            return [line]

        leading_space, assignment, string_part, trailing = match.groups()

        # Extract string content
        is_fstring = string_part.startswith('f"')
        content = string_part[2:-1] if is_fstring else string_part[1:-1]

        if len(line.rstrip()) <= self.max_length:
            return [line]

        # Find split point
        target = self.max_length - len(leading_space) - len(assignment) - (3 if is_fstring else 2)
        split_pos = self.find_split_point(content, target)

        if split_pos == -1 or split_pos < 20:
            return [line]

        # Split into parts
        part1 = content[:split_pos].rstrip()
        part2 = content[split_pos:].lstrip()

        prefix = '"' if is_fstring else '"'

        return [
            f'{leading_space}{assignment}(\n',
            f'{leading_space}    {prefix}{part1}"\n',
            f'{leading_space}    {prefix}{part2}"\n',
            f'{leading_space}){trailing}\n'
        ]

    def split_long_comment(self, line: str, indent: str) -> List[str]:
        """
        Split a long comment into multiple lines.

        Args:
            line: Comment line to split
            indent: Indentation string

        Returns:
            List of split lines, or original line if can't split
        """
        match = re.match(r'(\s*)(#\s*)(.+)', line)
        if not match:
            return [line]

        leading_space, comment_start, content = match.groups()

        if len(line.rstrip()) <= self.max_length:
            return [line]

        # Find split point
        target = self.max_length - len(leading_space) - len(comment_start)
        split_pos = self.find_split_point(content, target)

        if split_pos == -1 or split_pos < 20:
            return [line]

        part1 = content[:split_pos].rstrip()
        part2 = content[split_pos:].lstrip()

        return [
            f'{leading_space}{comment_start}{part1}\n',
            f'{leading_space}{comment_start}{part2}\n'
        ]

    def fix_file(self, filepath: str) -> Tuple[int, int]:
        """
        Fix E501 violations in a file.

        Args:
            filepath: Path to file to fix

        Returns:
            Tuple of (lines_fixed, violations_remaining)
        """
        path = Path(filepath)
        if not path.exists():
            print(f"❌ File not found: {filepath}")
            return 0, 0

        with open(path, 'r', encoding='utf-8') as f:
            lines = f.readlines()

        new_lines = []
        lines_fixed = 0

        for line in lines:
            if len(line.rstrip()) > self.max_length:
                indent = len(line) - len(line.lstrip())
                indent_str = ' ' * indent

                # Try different splitting strategies
                if 'logger.' in line and ('"' in line or '"' in line):
                    split_lines = self.split_long_logger(line, indent_str)
                    if len(split_lines) > 1:
                        new_lines.extend(split_lines)
                        lines_fixed += 1
                        continue

                if '=' in line and ('"' in line or '"' in line):
                    split_lines = self.split_long_string(line, indent_str)
                    if len(split_lines) > 1:
                        new_lines.extend(split_lines)
                        lines_fixed += 1
                        continue

                if line.lstrip().startswith('#'):
                    split_lines = self.split_long_comment(line, indent_str)
                    if len(split_lines) > 1:
                        new_lines.extend(split_lines)
                        lines_fixed += 1
                        continue

            new_lines.append(line)

        # Write back if changes made
        if lines_fixed > 0:
            with open(path, 'w', encoding='utf-8') as f:
                f.writelines(new_lines)

        # Count remaining violations
        remaining = sum(1 for line in new_lines if len(line.rstrip()) > self.max_length)

        return lines_fixed, remaining


def main():
    """Main entry point."""
    if len(sys.argv) < 2:
        print("Usage: python e501_violations_corrector.py <file1> [file2] ...")
        print("\nExample:")
        print("  python e501_violations_corrector.py src/chat_workflow_manager.py")
        print("  python e501_violations_corrector.py backend/api/*.py")
        sys.exit(1)

    fixer = E501Fixer(max_length=100)
    total_fixed = 0
    total_remaining = 0

    for filepath in sys.argv[1:]:
        print(f"\n📝 Processing: {filepath}")
        fixed, remaining = fixer.fix_file(filepath)
        total_fixed += fixed
        total_remaining += remaining

        if fixed > 0:
            print(f"  ✅ Fixed {fixed} lines")
        if remaining > 0:
            print(f"  ⚠️  {remaining} violations still remain (manual fix needed)")
        else:
            print("  🎉 File is clean!")

    print(f"\n{'='*60}")
    print(f"Total lines fixed: {total_fixed}")
    print(f"Total violations remaining: {total_remaining}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
