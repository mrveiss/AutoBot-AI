#!/usr/bin/env python3
"""Fix common whitespace issues in Python files."""

from pathlib import Path


def fix_whitespace_issues(filepath):
    """Fix whitespace issues in a single file."""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            lines = f.readlines()

        modified = False
        new_lines = []

        for line in lines:
            # Remove trailing whitespace (W291)
            if line.rstrip() != line.rstrip("\n"):
                line = line.rstrip() + "\n"
                modified = True

            # Fix blank lines with whitespace (W293)
            if line.strip() == "" and line != "\n":
                line = "\n"
                modified = True

            new_lines.append(line)

        # Ensure file ends with newline (W292)
        if new_lines and not new_lines[-1].endswith("\n"):
            new_lines[-1] += "\n"
            modified = True

        if modified:
            with open(filepath, "w", encoding="utf-8") as f:
                f.writelines(new_lines)
            return True
        return False
    except Exception as e:
        print(f"Error processing {filepath}: {e}")
        return False


def main():
    """Fix whitespace issues in backend/ and src/ directories."""
    root_dir = Path(__file__).parent.parent
    fixed_count = 0

    for directory in ["backend", "src"]:
        dir_path = root_dir / directory
        if not dir_path.exists():
            print(f"Directory {dir_path} not found")
            continue

        for py_file in dir_path.rglob("*.py"):
            if fix_whitespace_issues(py_file):
                fixed_count += 1
                print(f"Fixed: {py_file.relative_to(root_dir)}")

    print(f"\nTotal files fixed: {fixed_count}")


if __name__ == "__main__":
    main()
