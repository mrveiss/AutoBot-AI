#!/usr/bin/env python3
"""
Script to automatically refactor print_header function duplicates
"""

import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)

_SCRIPT_FORMATTER_IMPORT = "from utils.script_utils import ScriptFormatter"

# Regex pattern for the print_header method body
_PRINT_HEADER_PATTERN = (
    r'    def print_header\(self, title: str\):\s*"""[^"]*"""\s*'
    r'print\(f"\\n\{\'=\' \* 60\}"\)\s*print\(f"  \{title\}"\)\s*'
    r'print\("=" \* 60\)'
)

_PRINT_HEADER_REPLACEMENT = (
    "    def print_header(self, title: str):\n"
    '        """Print formatted header."""\n'
    "        ScriptFormatter.print_header(title)"
)

# Regex pattern for the print_step method body
_PRINT_STEP_PATTERN = (
    r"    def print_step\(self, step: str, "
    r'status: str = "info"\):\s*'
    r'"""[^"]*"""\s*status_icons = \{[^}]+\}\s*'
    r'icon = status_icons\.get\(status, "[^"]*"\)\s*'
    r'print\(f"\{icon\} \{step\}"\)'
)

_PRINT_STEP_REPLACEMENT = (
    '    def print_step(self, step: str, status: str = "info"):\n'
    '        """Print step with status."""\n'
    "        ScriptFormatter.print_step(step, status)"
)


def _add_formatter_import(content):
    """Add ScriptFormatter import after existing imports.

    Helper for refactor_print_header_script (#825).
    """
    import_pattern = r"(from src\.utils\.service_registry import [^\n]+)"
    if re.search(import_pattern, content):
        return re.sub(
            import_pattern,
            r"\1\n" + _SCRIPT_FORMATTER_IMPORT,
            content,
        )

    last_import_match = None
    for match in re.finditer(r"^(from .+|import .+)$", content, re.MULTILINE):
        last_import_match = match

    if last_import_match:
        end_pos = last_import_match.end()
        return content[:end_pos] + "\n" + _SCRIPT_FORMATTER_IMPORT + content[end_pos:]

    return content


def _replace_method_bodies(content):
    """Replace print_header and print_step method bodies.

    Helper for refactor_print_header_script (#825).
    """
    content = re.sub(
        _PRINT_HEADER_PATTERN,
        _PRINT_HEADER_REPLACEMENT,
        content,
        flags=re.MULTILINE | re.DOTALL,
    )
    content = re.sub(
        _PRINT_STEP_PATTERN,
        _PRINT_STEP_REPLACEMENT,
        content,
        flags=re.MULTILINE | re.DOTALL,
    )
    return content


def refactor_print_header_script(file_path: Path):
    """Refactor a single script to use shared ScriptFormatter."""
    logger.info(f"🔧 Refactoring {file_path.name}...")

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()

        if _SCRIPT_FORMATTER_IMPORT in content:
            logger.info("   ✅ Already refactored")
            return

        if "def print_header(self, title: str):" not in content:
            logger.info("   ⏭️  No print_header function found")
            return

        content = _add_formatter_import(content)
        content = _replace_method_bodies(content)

        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)

        logger.info("   ✅ Successfully refactored")

    except Exception as e:
        logger.error(f"   ❌ Error refactoring {file_path}: {e}")


def main():
    """Refactor all scripts with print_header duplicates"""
    scripts_to_refactor = [
        "/home/kali/Desktop/AutoBot/scripts/zero_downtime_deploy.py",
        "/home/kali/Desktop/AutoBot/scripts/secrets_manager.py",
        "/home/kali/Desktop/AutoBot/scripts/deployment_rollback.py",
        "/home/kali/Desktop/AutoBot/scripts/log_aggregator.py",
        "/home/kali/Desktop/AutoBot/scripts/metrics_collector.py",
    ]

    logger.info("🚀 Starting print_header refactoring...")

    for script_path in scripts_to_refactor:
        file_path = Path(script_path)
        if file_path.exists():
            refactor_print_header_script(file_path)
        else:
            logger.warning(f"   ⚠️  File not found: {script_path}")

    logger.info("\n✅ Print header refactoring complete!")


if __name__ == "__main__":
    main()
