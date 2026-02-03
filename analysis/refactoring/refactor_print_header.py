#!/usr/bin/env python3
"""
Script to automatically refactor print_header function duplicates
"""

import re
from pathlib import Path


def refactor_print_header_script(file_path: Path):
    """Refactor a single script to use shared ScriptFormatter"""
    print(f"🔧 Refactoring {file_path.name}...")

    try:
        with open(file_path, 'r') as f:
            content = f.read()

        # Check if it already imports ScriptFormatter
        if 'from src.utils.script_utils import ScriptFormatter' in content:
            print("   ✅ Already refactored")
            return

        # Check if it has the print_header function
        if 'def print_header(self, title: str):' not in content:
            print("   ⏭️  No print_header function found")
            return

        # Add import after existing imports
        import_pattern = r'(from src\.utils\.service_registry import [^\n]+)'
        if re.search(import_pattern, content):
            content = re.sub(
                import_pattern,
                r'\1\nfrom src.utils.script_utils import ScriptFormatter',
                content
            )
        else:
            # Find last import line and add after it
            last_import_match = None
            for match in re.finditer(r'^(from .+|import .+)$', content, re.MULTILINE):
                last_import_match = match

            if last_import_match:
                end_pos = last_import_match.end()
                content = content[:end_pos] + '\nfrom src.utils.script_utils import ScriptFormatter' + content[end_pos:]

        # Replace the print_header method implementation
        print_header_pattern = r'    def print_header\(self, title: str\):\s*"""[^"]*"""\s*print\(f"\\n\{\'=\' \* 60\}"\)\s*print\(f"  \{title\}"\)\s*print\("=" \* 60\)'
        content = re.sub(
            print_header_pattern,
            '    def print_header(self, title: str):\n        """Print formatted header."""\n        ScriptFormatter.print_header(title)',
            content,
            flags=re.MULTILINE | re.DOTALL
        )

        # Replace print_step method implementation
        print_step_pattern = r'    def print_step\(self, step: str, status: str = "info"\):\s*"""[^"]*"""\s*status_icons = \{[^}]+\}\s*icon = status_icons\.get\(status, "[^"]*"\)\s*print\(f"\{icon\} \{step\}"\)'
        content = re.sub(
            print_step_pattern,
            '    def print_step(self, step: str, status: str = "info"):\n        """Print step with status."""\n        ScriptFormatter.print_step(step, status)',
            content,
            flags=re.MULTILINE | re.DOTALL
        )

        # Write back the modified content
        with open(file_path, 'w') as f:
            f.write(content)

        print("   ✅ Successfully refactored")

    except Exception as e:
        print(f"   ❌ Error refactoring {file_path}: {e}")


def main():
    """Refactor all scripts with print_header duplicates"""
    scripts_to_refactor = [
        '/home/kali/Desktop/AutoBot/scripts/zero_downtime_deploy.py',
        '/home/kali/Desktop/AutoBot/scripts/secrets_manager.py',
        '/home/kali/Desktop/AutoBot/scripts/deployment_rollback.py',
        '/home/kali/Desktop/AutoBot/scripts/log_aggregator.py',
        '/home/kali/Desktop/AutoBot/scripts/metrics_collector.py'
    ]

    print("🚀 Starting print_header refactoring...")

    for script_path in scripts_to_refactor:
        file_path = Path(script_path)
        if file_path.exists():
            refactor_print_header_script(file_path)
        else:
            print(f"   ⚠️  File not found: {script_path}")

    print("\n✅ Print header refactoring complete!")


if __name__ == "__main__":
    main()
