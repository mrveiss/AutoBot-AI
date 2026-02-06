#!/usr/bin/env python3
"""
Fix specific flake8 issues that require manual attention
"""

import re
import subprocess
from pathlib import Path


def fix_syntax_errors():
    """Fix specific syntax errors identified by black formatter"""

    # Fix advanced_web_research.py syntax error
    file_path = Path("src/agents/advanced_web_research.py")
    if file_path.exists():
        try:
            with open(file_path, "r") as f:
                content = f.read()

            # Fix the problematic line with incorrect quotes
            content = content.replace(
                '"document.getElementById("g-recaptcha-response")"',
                "\"document.getElementById('g-recaptcha-response')\"",
            )

            with open(file_path, "w") as f:
                f.write(content)

            print(f"Fixed syntax error in {file_path}")
        except Exception as e:
            print(f"Failed to fix {file_path}: {e}")

    # Fix tool_registry.py syntax error
    file_path = Path("src/tools/tool_registry.py")
    if file_path.exists():
        try:
            with open(file_path, "r") as f:
                content = f.read()

            # Fix logger definition at module level
            lines = content.split("\n")
            fixed_lines = []
            found_logger = False

            for line in lines:
                if "logger = logging.getLogger(__name__)" in line and not found_logger:
                    # Ensure proper imports first
                    if not any("import logging" in l for l in fixed_lines[:10]):
                        fixed_lines.insert(0, "import logging")
                    found_logger = True
                fixed_lines.append(line)

            content = "\n".join(fixed_lines)

            with open(file_path, "w") as f:
                f.write(content)

            print(f"Fixed syntax error in {file_path}")
        except Exception as e:
            print(f"Failed to fix {file_path}: {e}")

    # Fix streaming_executor.py syntax error
    file_path = Path("src/intelligence/streaming_executor.py")
    if file_path.exists():
        try:
            with open(file_path, "r") as f:
                content = f.read()

            # Fix the problematic string with quotes
            content = content.replace(
                '""SKIP" to avoid spam."', '"SKIP to avoid spam."'
            )

            with open(file_path, "w") as f:
                f.write(content)

            print(f"Fixed syntax error in {file_path}")
        except Exception as e:
            print(f"Failed to fix {file_path}: {e}")


def fix_undefined_names():
    """Fix undefined name issues"""

    # Fix chat.py undefined Optional
    file_path = Path("backend/api/chat.py")
    if file_path.exists():
        try:
            with open(file_path, "r") as f:
                content = f.read()

            # Add Optional import if missing
            if "from typing import" in content and "Optional" not in content:
                content = content.replace(
                    "from typing import", "from typing import Optional,"
                )
            elif "typing import" not in content:
                # Add typing import at the top
                lines = content.split("\n")
                import_index = 0
                for i, line in enumerate(lines):
                    if line.startswith("import ") or line.startswith("from "):
                        import_index = i + 1

                lines.insert(import_index, "from typing import Optional")
                content = "\n".join(lines)

            with open(file_path, "w") as f:
                f.write(content)

            print(f"Fixed undefined Optional in {file_path}")
        except Exception as e:
            print(f"Failed to fix {file_path}: {e}")


def remove_unused_variables():
    """Remove unused variables that are easily identifiable"""

    files_to_fix = [
        "backend/api/advanced_control.py",
        "backend/api/chat.py",
        "backend/api/advanced_workflow_orchestrator.py",
        "src/workflow_classifier.py",
    ]

    for file_path_str in files_to_fix:
        file_path = Path(file_path_str)
        if file_path.exists():
            try:
                with open(file_path, "r") as f:
                    content = f.read()

                # Remove specific unused variables
                patterns_to_fix = [
                    (
                        r"(\s+)takeover_status = .*\n",
                        r"",
                    ),  # Remove unused takeover_status
                    (
                        r"(\s+)pending_approval_data = .*\n",
                        r"",
                    ),  # Remove unused variables
                    (
                        r"(\s+)workflow = .*\n(?=\s+except)",
                        r"",
                    ),  # Remove unused workflow var
                    (
                        r"(\s+)complexity_map = .*\n",
                        r"",
                    ),  # Remove unused complexity_map
                    (
                        r"(\s+)security_network_keywords = .*\n",
                        r"",
                    ),  # Remove unused variables
                ]

                for pattern, replacement in patterns_to_fix:
                    content = re.sub(pattern, replacement, content, flags=re.MULTILINE)

                with open(file_path, "w") as f:
                    f.write(content)

                print(f"Removed unused variables in {file_path}")
            except Exception as e:
                print(f"Failed to fix {file_path}: {e}")


def fix_import_duplicates():
    """Fix duplicate imports"""

    files_to_fix = [
        "backend/api/advanced_workflow_orchestrator.py",
        "backend/api/chat.py",
    ]

    for file_path_str in files_to_fix:
        file_path = Path(file_path_str)
        if file_path.exists():
            try:
                with open(file_path, "r") as f:
                    lines = f.readlines()

                # Track imports and remove duplicates
                seen_imports = set()
                fixed_lines = []

                for line in lines:
                    if line.startswith("import ") or line.startswith("from "):
                        import_statement = line.strip()
                        if import_statement not in seen_imports:
                            seen_imports.add(import_statement)
                            fixed_lines.append(line)
                    else:
                        fixed_lines.append(line)

                with open(file_path, "w") as f:
                    f.writelines(fixed_lines)

                print(f"Fixed duplicate imports in {file_path}")
            except Exception as e:
                print(f"Failed to fix {file_path}: {e}")


def run_final_formatting():
    """Run final formatting to clean up remaining issues"""
    try:
        # Run black with lenient line length for problematic files
        subprocess.run(
            [
                "black",
                "src/",
                "backend/",
                "--line-length",
                "100",  # Slightly more lenient
                "--skip-string-normalization",  # Avoid quote style conflicts
            ],
            check=False,
        )

        print("Final black formatting completed")
    except Exception as e:
        print(f"Final formatting failed: {e}")


def main():
    """Main function to fix specific code quality issues"""
    print("Fixing specific code quality issues...")

    print("\n1. Fixing syntax errors...")
    fix_syntax_errors()

    print("\n2. Fixing undefined names...")
    fix_undefined_names()

    print("\n3. Removing unused variables...")
    remove_unused_variables()

    print("\n4. Fixing duplicate imports...")
    fix_import_duplicates()

    print("\n5. Running final formatting...")
    run_final_formatting()

    print("\nSpecific fixes completed!")


if __name__ == "__main__":
    main()
