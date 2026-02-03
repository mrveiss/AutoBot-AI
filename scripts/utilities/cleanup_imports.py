#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Quick import cleanup utility for AutoBot codebase
Removes common unused imports while preserving code functionality
"""

import subprocess
import sys
from pathlib import Path
from typing import List


def get_unused_imports(file_path: str) -> List[str]:
    """Get list of unused imports using flake8"""
    try:
        result = subprocess.run(
            ["flake8", file_path, "--select=F401", "--max-line-length=88"],
            capture_output=True,
            text=True,
        )

        unused_imports = []
        for line in result.stdout.strip().split("\n"):
            if "F401" in line and "imported but unused" in line:
                # Extract the import name from the flake8 output
                if "'" in line:
                    import_name = line.split("'")[1]
                    unused_imports.append(import_name)

        return unused_imports
    except Exception as e:
        print(f"Error checking {file_path}: {e}")
        return []


def remove_unused_imports(file_path: str, max_removals: int = 10) -> bool:
    """Remove unused imports from a file"""
    try:
        unused_imports = get_unused_imports(file_path)
        if not unused_imports:
            return False

        # Limit removals for safety
        unused_imports = unused_imports[:max_removals]

        with open(file_path, "r") as f:
            content = f.read()

        original_content = content
        lines = content.split("\n")
        modified_lines = []

        for line in lines:
            should_remove = False

            for unused_import in unused_imports:
                # Remove simple import lines
                if (
                    line.strip().startswith("import ")
                    and unused_import in line
                    and line.strip().endswith(unused_import)
                ):
                    should_remove = True
                    break

                # Remove from import lines
                if line.strip().startswith("from ") and f" {unused_import}" in line:
                    # Handle multi-import lines
                    if "," in line:
                        # Remove just this import
                        parts = line.split("import")[1]
                        imports = [imp.strip() for imp in parts.split(",")]
                        remaining_imports = [
                            imp for imp in imports if imp != unused_import
                        ]

                        if remaining_imports:
                            line = (
                                line.split("import")[0]
                                + "import "
                                + ", ".join(remaining_imports)
                            )
                        else:
                            should_remove = True
                    else:
                        should_remove = True
                    break

            if not should_remove:
                modified_lines.append(line)

        new_content = "\n".join(modified_lines)

        # Only write if we actually changed something
        if new_content != original_content:
            with open(file_path, "w") as f:
                f.write(new_content)
            print(f"Cleaned {len(unused_imports)} unused imports from {file_path}")
            return True

        return False

    except Exception as e:
        print(f"Error processing {file_path}: {e}")
        return False


def main():
    """Main cleanup function"""
    if len(sys.argv) > 1:
        files_to_clean = sys.argv[1:]
    else:
        # Default to the files with most unused imports
        files_to_clean = [
            "src/context_aware_decision_system.py",
            "src/voice_processing_system.py",
            "backend/api/advanced_workflow_orchestrator.py",
            "src/orchestrator.py",
            "src/computer_vision_system.py",
            "src/multimodal_processor.py",
        ]

    cleaned_files = 0

    for file_path in files_to_clean:
        if Path(file_path).exists():
            if remove_unused_imports(file_path):
                cleaned_files += 1
        else:
            print(f"File not found: {file_path}")

    print(f"\nCleaned unused imports from {cleaned_files} files")


if __name__ == "__main__":
    main()
