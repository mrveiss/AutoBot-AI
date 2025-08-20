#!/usr/bin/env python3
"""
Script to fix common linting issues in Python files.
"""

import re
import sys


def fix_line_length_issues(content):
    """Fix line length and formatting issues."""
    lines = content.split("\n")
    fixed_lines = []

    for i, line in enumerate(lines):
        original_line = line

        # Skip already properly formatted lines or very short lines
        if len(line) <= 88 or line.strip() == "":
            fixed_lines.append(line)
            continue

        # Handle long logger calls
        if "logger." in line and 'f"' in line and len(line) > 88:
            # Split f-string logger calls
            indent = len(line) - len(line.lstrip())
            if 'logger.info(f"' in line:
                match = re.match(r'(\s*)(logger\.info\(f")([^"]+)("\))', line)
                if match:
                    spaces, prefix, message, suffix = match.groups()
                    if len(message) > 50:  # Long message
                        fixed_lines.append(f'{spaces}{prefix.replace("(f", "(")}')
                        fixed_lines.append(f'{spaces}    f"{message}"{suffix}')
                        continue
            elif 'logger.error(f"' in line:
                match = re.match(r'(\s*)(logger\.error\(f")([^"]+)("\))', line)
                if match:
                    spaces, prefix, message, suffix = match.groups()
                    if len(message) > 50:
                        fixed_lines.append(f'{spaces}{prefix.replace("(f", "(")}')
                        fixed_lines.append(f'{spaces}    f"{message}"{suffix}')
                        continue
            elif 'logger.debug(f"' in line:
                match = re.match(r'(\s*)(logger\.debug\(f")([^"]+)("\))', line)
                if match:
                    spaces, prefix, message, suffix = match.groups()
                    if len(message) > 50:
                        fixed_lines.append(f'{spaces}{prefix.replace("(f", "(")}')
                        fixed_lines.append(f'{spaces}    f"{message}"{suffix}')
                        continue

        # Handle long function calls with await
        if "await " in line and "(" in line and len(line) > 88:
            indent = len(line) - len(line.lstrip())
            spaces = " " * indent

            # Handle assignment with await
            if " = await " in line:
                parts = line.split(" = await ", 1)
                if len(parts) == 2:
                    var_part = parts[0]
                    func_part = "await " + parts[1]
                    if len(var_part) + len(func_part) + 3 > 88:
                        fixed_lines.append(f"{var_part} = (")
                        fixed_lines.append(f"{spaces}    {func_part}")
                        fixed_lines.append(f"{spaces})")
                        continue

        # Handle long string concatenation in f-strings
        if 'f"' in line and "{" in line and "}" in line and len(line) > 88:
            indent = len(line) - len(line.lstrip())
            spaces = " " * indent

            # Try to split at logical points
            if " -> " in line:
                parts = line.split(" -> ", 1)
                if len(parts) == 2:
                    fixed_lines.append(f"{parts[0]} -> ")
                    fixed_lines.append(f"{spaces}    {parts[1]}")
                    continue

        # Handle long dictionary lines
        if (
            ('": ' in line or '":' in line)
            and (line.strip().endswith(",") or line.strip().endswith("}"))
            and len(line) > 88
        ):
            # Already handled by existing logic, skip for now
            pass

        # Handle long condition statements
        if ("if " in line or "elif " in line) and " and " in line and len(line) > 88:
            indent = len(line) - len(line.lstrip())
            spaces = " " * indent

            # Split on 'and' conditions
            if_match = re.match(r"(\s*)(if|elif)\s+(.+):", line)
            if if_match:
                spaces_part, if_part, condition = if_match.groups()
                if " and " in condition:
                    conditions = condition.split(" and ")
                    if len(conditions) >= 2:
                        fixed_lines.append(
                            f"{spaces_part}{if_part} ({conditions[0]} and"
                        )
                        for cond in conditions[1:-1]:
                            fixed_lines.append(f"{spaces}        {cond.strip()} and")
                        fixed_lines.append(
                            f"{spaces}        {conditions[-1].strip()}):"
                        )
                        continue

        # For other long lines, keep as is for now
        fixed_lines.append(line)

    return "\n".join(fixed_lines)


def main():
    if len(sys.argv) != 2:
        print("Usage: python fix_linting.py <file_path>")
        sys.exit(1)

    file_path = sys.argv[1]

    with open(file_path, "r") as f:
        content = f.read()

    fixed_content = fix_line_length_issues(content)

    with open(file_path, "w") as f:
        f.write(fixed_content)

    print(f"Fixed linting issues in {file_path}")


if __name__ == "__main__":
    main()
