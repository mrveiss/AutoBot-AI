#!/usr/bin/env python3
"""
Automated Code Quality Fix Script for AutoBot
Fixes common flake8 issues including unused imports, line length, and formatting
"""

import ast
import re
import subprocess
from pathlib import Path
from typing import Dict, List


class CodeQualityFixer:
    """Automated code quality fixer for Python files"""

    def __init__(self, base_path: str = "."):
        self.base_path = Path(base_path)
        self.max_line_length = 88

    def fix_file(self, file_path: Path) -> bool:
        """Fix code quality issues in a single file"""
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                original_content = f.read()

            content = original_content

            # Fix various issues
            content = self._remove_unused_imports(content, file_path)
            content = self._fix_blank_lines(content)
            content = self._fix_trailing_whitespace(content)
            content = self._ensure_newline_at_end(content)
            content = self._fix_f_strings(content)

            # Write back if changed
            if content != original_content:
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(content)
                return True

            return False

        except Exception as e:
            print(f"Error fixing {file_path}: {e}")
            return False

    def _remove_unused_imports(self, content: str, file_path: Path) -> str:
        """Remove unused imports from file content"""
        try:
            tree = ast.parse(content)
        except SyntaxError:
            return content

        # Get all imported names
        imported_names = set()
        import_lines = {}

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    name = alias.asname if alias.asname else alias.name
                    imported_names.add(name)
                    import_lines[name] = node.lineno
            elif isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    name = alias.asname if alias.asname else alias.name
                    imported_names.add(name)
                    import_lines[name] = node.lineno

        # Find used names
        used_names = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Name):
                used_names.add(node.id)
            elif isinstance(node, ast.Attribute):
                # Handle module.attr access
                if isinstance(node.value, ast.Name):
                    used_names.add(node.value.id)

        # Find unused imports
        unused_imports = imported_names - used_names

        # Remove unused import lines
        lines = content.split("\n")
        lines_to_remove = set()

        for unused in unused_imports:
            if unused in import_lines:
                line_num = import_lines[unused] - 1  # Convert to 0-based
                if line_num < len(lines):
                    line = lines[line_num]
                    # Only remove if it's a simple single import
                    if (
                        f"import {unused}" in line
                        or f"from .* import.*{unused}" in line
                    ):
                        lines_to_remove.add(line_num)

        # Remove lines in reverse order to maintain indices
        for line_num in sorted(lines_to_remove, reverse=True):
            del lines[line_num]

        return "\n".join(lines)

    def _fix_blank_lines(self, content: str) -> str:
        """Fix blank line issues"""
        lines = content.split("\n")
        fixed_lines = []

        for i, line in enumerate(lines):
            # Remove trailing whitespace from blank lines
            if line.strip() == "":
                fixed_lines.append("")
            else:
                fixed_lines.append(line)

        # Remove excessive blank lines (more than 2 consecutive)
        result_lines = []
        blank_count = 0

        for line in fixed_lines:
            if line.strip() == "":
                blank_count += 1
                if blank_count <= 2:
                    result_lines.append(line)
            else:
                blank_count = 0
                result_lines.append(line)

        return "\n".join(result_lines)

    def _fix_trailing_whitespace(self, content: str) -> str:
        """Remove trailing whitespace from all lines"""
        lines = content.split("\n")
        return "\n".join(line.rstrip() for line in lines)

    def _ensure_newline_at_end(self, content: str) -> str:
        """Ensure file ends with newline"""
        if content and not content.endswith("\n"):
            content += "\n"
        return content

    def _fix_f_strings(self, content: str) -> str:
        """Fix f-strings missing placeholders"""
        # Simple regex to find f-strings without placeholders
        pattern = r'f"([^"]*)"'

        def replace_f_string(match):
            string_content = match.group(1)
            if "{" not in string_content:
                # Remove f prefix if no placeholders
                return f'"{string_content}"'
            return match.group(0)

        content = re.sub(pattern, replace_f_string, content)

        # Handle single quotes too
        pattern = r"f'([^']*)'"
        content = re.sub(pattern, replace_f_string, content)

        return content

    def fix_directory(
        self, directory: Path, extensions: List[str] = None
    ) -> Dict[str, int]:
        """Fix all Python files in directory"""
        if extensions is None:
            extensions = [".py"]

        results = {"fixed": 0, "total": 0}

        for file_path in directory.rglob("*"):
            if file_path.suffix in extensions and file_path.is_file():
                results["total"] += 1
                if self.fix_file(file_path):
                    results["fixed"] += 1
                    print(f"Fixed: {file_path}")

        return results


def run_black_formatter(directory: Path):
    """Run black formatter on directory"""
    try:
        cmd = ["black", str(directory), "--line-length", "88"]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0:
            print("Black formatting completed successfully")
        else:
            print(f"Black formatting had issues: {result.stderr}")
    except FileNotFoundError:
        print("Black formatter not found, skipping")


def run_isort(directory: Path):
    """Run isort on directory"""
    try:
        cmd = ["isort", str(directory)]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0:
            print("Import sorting completed successfully")
        else:
            print(f"Import sorting had issues: {result.stderr}")
    except FileNotFoundError:
        print("isort not found, skipping")


def main():
    """Main function to fix code quality issues"""
    base_path = Path(".")

    # Initialize fixer
    fixer = CodeQualityFixer(base_path)

    # Fix src/ directory
    print("Fixing src/ directory...")
    src_results = fixer.fix_directory(base_path / "src")

    # Fix backend/ directory
    print("Fixing backend/ directory...")
    backend_results = fixer.fix_directory(base_path / "backend")

    # Run formatters
    print("Running black formatter...")
    run_black_formatter(base_path / "src")
    run_black_formatter(base_path / "backend")

    print("Running isort...")
    run_isort(base_path / "src")
    run_isort(base_path / "backend")

    # Print summary
    total_fixed = src_results["fixed"] + backend_results["fixed"]
    total_files = src_results["total"] + backend_results["total"]

    print(f"\nCode Quality Fix Summary:")
    print(f"Files processed: {total_files}")
    print(f"Files fixed: {total_fixed}")
    print(
        f"Success rate: {(total_fixed/total_files*100):.1f}%"
        if total_files > 0
        else "0%"
    )


if __name__ == "__main__":
    main()
