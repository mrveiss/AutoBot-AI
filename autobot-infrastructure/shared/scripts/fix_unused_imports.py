#!/usr/bin/env python3
"""Fix unused imports in Python files."""

import subprocess
import sys
from pathlib import Path


def fix_unused_imports(filepath):
    """Fix unused imports in a single file using autoflake."""
    try:
        # Run autoflake to remove unused imports
        result = subprocess.run(
            [
                "autoflake",
                "--in-place",
                "--remove-unused-variables",
                "--remove-all-unused-imports",
                str(filepath),
            ],
            capture_output=True,
            text=True,
        )

        return result.returncode == 0
    except Exception as e:
        print(f"Error processing {filepath}: {e}")
        return False


def main():
    """Fix unused imports in backend/ and src/ directories."""
    # First check if autoflake is installed
    try:
        subprocess.run(["autoflake", "--version"], capture_output=True, check=True)
    except Exception:
        print("Installing autoflake...")
        subprocess.run([sys.executable, "-m", "pip", "install", "autoflake"])

    root_dir = Path(__file__).parent.parent
    fixed_count = 0

    # Get list of files with F401 errors from flake8
    files_with_unused_imports = [
        "backend/api/advanced_control.py",
        "backend/api/advanced_workflow_orchestrator.py",
        "backend/api/agent_config.py",
        "backend/api/research_browser.py",
        "backend/api/llm.py",
        "backend/api/base_terminal.py",
        "backend/api/chat.py",
        "backend/api/secure_terminal_websocket.py",
        "backend/api/simple_terminal_websocket.py",
        "backend/api/secrets.py",
        "backend/app_factory.py",
        "backend/services/secrets_service.py",
        "src/voice_processing_system.py",
        "src/orchestrator.py",
        "src/project_state_manager.py",
        "src/agents/classification_agent.py",
        "src/agents/gemma_classification_agent.py",
        "src/autobot_types.py",
        "src/config.py",
        "src/research_browser_manager.py",
        "src/workflow_classifier.py",
    ]

    for filepath in files_with_unused_imports:
        full_path = root_dir / filepath
        if full_path.exists():
            if fix_unused_imports(full_path):
                fixed_count += 1
                print(f"Fixed: {filepath}")
        else:
            print(f"File not found: {filepath}")

    print(f"\nTotal files fixed: {fixed_count}")


if __name__ == "__main__":
    main()
