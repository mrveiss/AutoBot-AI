# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Fix f-string logging statements to use lazy evaluation.

Issue #401: Converts logger.xxx(f"...{var}...") to logger.xxx("...%s...", var)

Usage:
    python scripts/fstring_logging_corrector.py --directory src/services/
    python scripts/fstring_logging_corrector.py --directory src/security/
    python scripts/fstring_logging_corrector.py --file src/services/temporal_invalidation_service.py
"""

import argparse
import re
import sys
from pathlib import Path


def fstring_logging_corrector(content: str) -> tuple[str, int]:
    """
    Convert f-string logging to lazy evaluation %s-style.

    Returns:
        Tuple of (fixed_content, number_of_fixes)
    """
    fixes = 0
    lines = content.split("\n")
    result_lines = []
    i = 0

    while i < len(lines):
        line = lines[i]

        # Pattern to match logger.xxx(f"..." or logger.xxx(f'...'
        # This handles single-line cases
        single_line_pattern = r'(logger\.(debug|info|warning|error|exception|critical))\(f(["\'])(.*?)\3\)'

        match = re.search(single_line_pattern, line)
        if match:
            # Single line f-string logging
            prefix = match.group(1)
            quote = match.group(3)
            fstring_content = match.group(4)

            # Extract variables from f-string
            new_format, args = convert_fstring_to_format(fstring_content)

            if args:
                # Get everything before and after the match
                before = line[: match.start()]
                after = line[match.end() :]

                # Reconstruct the line
                new_line = f'{before}{prefix}("{new_format}", {", ".join(args)}){after}'
                result_lines.append(new_line)
                fixes += 1
            else:
                # No variables to extract, just remove the f
                new_line = line.replace(
                    f"{match.group(1)}(f{quote}", f"{match.group(1)}({quote}"
                )
                result_lines.append(new_line)
                fixes += 1
        else:
            # Check for multi-line f-string logging
            multiline_start = re.search(
                r"(logger\.(debug|info|warning|error|exception|critical))\(\s*$", line
            )
            if multiline_start:
                # Collect all lines of the multi-line statement
                block_lines = [line]
                j = i + 1
                paren_count = 1
                while j < len(lines) and paren_count > 0:
                    block_lines.append(lines[j])
                    paren_count += lines[j].count("(") - lines[j].count(")")
                    j += 1

                block = "\n".join(block_lines)

                # Check if it contains f-strings
                if re.search(r'f["\']', block):
                    fixed_block, block_fixes = fix_multiline_fstring_logging(block)
                    result_lines.extend(fixed_block.split("\n"))
                    fixes += block_fixes
                    i = j
                    continue
                else:
                    result_lines.append(line)
            else:
                # Check for logger.xxx(f" pattern that might span lines
                partial_match = re.search(
                    r'(logger\.(debug|info|warning|error|exception|critical))\(f(["\'])',
                    line,
                )
                if partial_match and not line.rstrip().endswith(")"):
                    # Multi-line f-string
                    block_lines = [line]
                    j = i + 1
                    paren_count = line.count("(") - line.count(")")
                    while j < len(lines) and paren_count > 0:
                        block_lines.append(lines[j])
                        paren_count += lines[j].count("(") - lines[j].count(")")
                        j += 1

                    block = "\n".join(block_lines)
                    fixed_block, block_fixes = fix_multiline_fstring_logging(block)
                    result_lines.extend(fixed_block.split("\n"))
                    fixes += block_fixes
                    i = j
                    continue
                else:
                    result_lines.append(line)

        i += 1

    return "\n".join(result_lines), fixes


def convert_fstring_to_format(fstring_content: str) -> tuple[str, list[str]]:
    """
    Convert f-string content to format string and argument list.

    Example:
        "Error: {e}" -> ("Error: %s", ["e"])
        "Value {x} is {y}" -> ("Value %s is %s", ["x", "y"])
        "Score: {score:.3f}" -> ("Score: %.3f", ["score"])
    """
    args = []

    def replace_placeholder(match):
        expr = match.group(1)
        format_spec = match.group(2) if match.group(2) else ""

        # Handle format specifiers
        if format_spec:
            # Convert Python format spec to printf-style
            if format_spec.startswith(":"):
                format_spec = format_spec[1:]

            if "f" in format_spec or "e" in format_spec or "g" in format_spec:
                # Float formatting
                args.append(expr)
                return f"%{format_spec}"
            elif "d" in format_spec:
                # Integer formatting
                args.append(expr)
                return f"%{format_spec}"
            else:
                # Other formatting (width, precision for strings, etc.)
                args.append(expr)
                return "%s"
        else:
            args.append(expr)
            return "%s"

    # Pattern to match {expr} or {expr:format}
    pattern = r"\{([^{}:]+)(:[^{}]*)?\}"
    new_format = re.sub(pattern, replace_placeholder, fstring_content)

    return new_format, args


def fix_multiline_fstring_logging(block: str) -> tuple[str, int]:
    """
    Fix multi-line f-string logging statements.
    """
    # This is complex - for multi-line, we'll try a simpler approach
    # Find all f-strings and extract their content

    # Pattern to find logger call
    logger_match = re.search(
        r"(logger\.(debug|info|warning|error|exception|critical))\(", block
    )
    if not logger_match:
        return block, 0

    prefix = logger_match.group(1)

    # Find all f-string parts
    fstring_pattern = r'f(["\'])((?:[^"\'\\]|\\.)*?)\1'
    fstrings = re.findall(fstring_pattern, block)

    if not fstrings:
        return block, 0

    # Combine all f-string contents
    all_content = []
    all_args = []

    for quote, content in fstrings:
        new_format, args = convert_fstring_to_format(content)
        all_content.append(new_format)
        all_args.extend(args)

    # Get indentation
    indent_match = re.match(r"^(\s*)", block)
    indent = indent_match.group(1) if indent_match else ""

    # Check for trailing arguments like exc_info=True
    trailing_args = ""
    if "exc_info=" in block:
        exc_match = re.search(r",\s*(exc_info\s*=\s*\w+)", block)
        if exc_match:
            trailing_args = ", " + exc_match.group(1)

    # Build the new statement
    combined_format = "".join(all_content)
    if all_args:
        args_str = ", ".join(all_args)
        if trailing_args:
            new_block = (
                f'{indent}{prefix}("{combined_format}", {args_str}{trailing_args})'
            )
        else:
            new_block = f'{indent}{prefix}("{combined_format}", {args_str})'
    else:
        new_block = f'{indent}{prefix}("{combined_format}"{trailing_args})'

    return new_block, 1


def process_file(filepath: Path, dry_run: bool = False) -> int:
    """Process a single file and fix f-string logging."""
    try:
        content = filepath.read_text(encoding="utf-8")
    except Exception as e:
        print(f"Error reading {filepath}: {e}")
        return 0

    fixed_content, fixes = fstring_logging_corrector(content)

    if fixes > 0:
        if dry_run:
            print(f"Would fix {fixes} instances in {filepath}")
        else:
            filepath.write_text(fixed_content, encoding="utf-8")
            print(f"Fixed {fixes} instances in {filepath}")

    return fixes


def process_directory(directory: Path, dry_run: bool = False) -> int:
    """Process all Python files in a directory."""
    total_fixes = 0

    for filepath in directory.rglob("*.py"):
        # Skip archive directories
        if "archive" in str(filepath):
            continue

        fixes = process_file(filepath, dry_run)
        total_fixes += fixes

    return total_fixes


def main():
    parser = argparse.ArgumentParser(
        description="Fix f-string logging to lazy evaluation"
    )
    parser.add_argument("--directory", "-d", type=str, help="Directory to process")
    parser.add_argument("--file", "-f", type=str, help="Single file to process")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be fixed without making changes",
    )

    args = parser.parse_args()

    if not args.directory and not args.file:
        parser.print_help()
        sys.exit(1)

    if args.file:
        filepath = Path(args.file)
        if not filepath.exists():
            print(f"File not found: {filepath}")
            sys.exit(1)
        fixes = process_file(filepath, args.dry_run)
        print(f"Total fixes: {fixes}")
    else:
        directory = Path(args.directory)
        if not directory.exists():
            print(f"Directory not found: {directory}")
            sys.exit(1)
        fixes = process_directory(directory, args.dry_run)
        print(f"Total fixes: {fixes}")


if __name__ == "__main__":
    main()
