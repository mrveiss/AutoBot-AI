#!/usr/bin/env python3
"""
Script to refactor hardcoded IP addresses and URLs to use shared constants
"""

import os
import re
from pathlib import Path
from typing import Dict, List, Tuple

# Mapping of hardcoded values to constants
REPLACEMENT_MAP = {
    # IP addresses
    '172.16.168.20': 'NetworkConstants.MAIN_MACHINE_IP',
    '172.16.168.21': 'NetworkConstants.FRONTEND_VM_IP',
    '172.16.168.22': 'NetworkConstants.NPU_WORKER_VM_IP',
    '172.16.168.23': 'NetworkConstants.REDIS_VM_IP',
    '172.16.168.24': 'NetworkConstants.AI_STACK_VM_IP',
    '172.16.168.25': 'NetworkConstants.BROWSER_VM_IP',
    '127.0.0.1': 'NetworkConstants.LOCALHOST_IP',

    # URLs (need to be more careful with these to avoid false positives)
    'http://localhost:8001': 'ServiceURLs.BACKEND_LOCAL',
    'http://172.16.168.20:8001': 'ServiceURLs.BACKEND_API',
    'http://localhost:5173': 'ServiceURLs.FRONTEND_LOCAL',
    'http://172.16.168.21:5173': 'ServiceURLs.FRONTEND_VM',
    'http://localhost:11434': 'ServiceURLs.OLLAMA_LOCAL',
    'redis://172.16.168.23:6379': 'ServiceURLs.REDIS_VM',
    'redis://127.0.0.1:6379': 'ServiceURLs.REDIS_LOCAL',
}

def should_refactor_file(file_path: Path) -> bool:
    """Check if file should be refactored"""
    # Skip certain directories and files
    skip_patterns = [
        'node_modules', '.venv', '__pycache__', '.git',
        'reports', 'logs', 'temp', 'archives',
        'analysis/refactoring'  # Don't refactor our own analysis tools
    ]

    path_str = str(file_path)
    for pattern in skip_patterns:
        if pattern in path_str:
            return False

    # Only refactor code files
    return file_path.suffix in {'.py', '.js', '.ts', '.vue', '.jsx', '.tsx'}

def add_import_if_needed(content: str, file_path: Path) -> str:
    """Add NetworkConstants import if replacements were made and not already imported"""

    # Check if we already have the import
    if 'from src.constants import NetworkConstants' in content or \
       'from src.constants.network_constants import NetworkConstants' in content:
        return content

    # Check if any of our constants are used
    uses_constants = any(const_name in content for const_name in REPLACEMENT_MAP.values())
    if not uses_constants:
        return content

    # Find where to add the import
    lines = content.split('\n')
    import_line = 'from src.constants import NetworkConstants, ServiceURLs'

    # Find the best place to add the import
    last_import_line = -1
    for i, line in enumerate(lines):
        if line.strip().startswith(('import ', 'from ')) and not line.strip().startswith('from .'):
            last_import_line = i

    if last_import_line >= 0:
        # Add after the last import
        lines.insert(last_import_line + 1, import_line)
    else:
        # Add at the beginning after any docstring
        insert_pos = 0
        if lines and lines[0].strip().startswith('"""') or lines[0].strip().startswith("'''"):
            # Find end of docstring
            quote_char = '"""' if lines[0].strip().startswith('"""') else "'''"
            for i in range(1, len(lines)):
                if quote_char in lines[i]:
                    insert_pos = i + 1
                    break

        lines.insert(insert_pos, import_line)
        lines.insert(insert_pos + 1, '')  # Add blank line

    return '\n'.join(lines)

def refactor_file_content(content: str, file_path: Path) -> Tuple[str, int]:
    """Refactor content to use constants. Returns (new_content, num_replacements)"""
    original_content = content
    replacements_made = 0

    # Sort replacements by length (longest first) to avoid partial replacements
    sorted_replacements = sorted(REPLACEMENT_MAP.items(), key=lambda x: len(x[0]), reverse=True)

    for hardcoded_value, constant_name in sorted_replacements:
        # Create patterns for different contexts
        patterns = [
            # In quotes
            f'"{re.escape(hardcoded_value)}"',
            f"'{re.escape(hardcoded_value)}'",
            # In f-strings and other contexts
            re.escape(hardcoded_value)
        ]

        for pattern in patterns:
            if pattern in content:
                # For quoted strings, replace with the constant
                if pattern.startswith(('"', "'")):
                    quote_char = pattern[0]
                    replacement = f'{constant_name}'
                    content = content.replace(pattern, replacement)
                else:
                    # For unquoted occurrences, be more careful
                    # Use word boundaries to avoid partial matches
                    regex_pattern = r'\b' + re.escape(hardcoded_value) + r'\b'
                    if re.search(regex_pattern, content):
                        content = re.sub(regex_pattern, constant_name, content)

                if content != original_content:
                    replacements_made += 1
                    original_content = content

    # Add import if we made replacements
    if replacements_made > 0:
        content = add_import_if_needed(content, file_path)

    return content, replacements_made

def refactor_file(file_path: Path) -> bool:
    """Refactor a single file. Returns True if changes were made."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            original_content = f.read()

        new_content, replacements = refactor_file_content(original_content, file_path)

        if replacements > 0:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(new_content)
            print(f"   ✅ {file_path.name}: {replacements} replacements")
            return True
        else:
            print(f"   ⏭️  {file_path.name}: No changes needed")
            return False

    except Exception as e:
        print(f"   ❌ Error refactoring {file_path}: {e}")
        return False

def find_core_files() -> List[Path]:
    """Find core AutoBot files that should be refactored"""
    root_path = Path('/home/kali/Desktop/AutoBot')
    core_files = []

    # Focus on core directories
    core_dirs = ['src', 'backend', 'autobot-vue/src', 'scripts']

    for core_dir in core_dirs:
        dir_path = root_path / core_dir
        if dir_path.exists():
            for file_path in dir_path.rglob('*'):
                if file_path.is_file() and should_refactor_file(file_path):
                    core_files.append(file_path)

    return core_files

def main():
    """Main refactoring function"""
    print("🚀 Starting network constants refactoring...")
    print(f"📋 Will replace {len(REPLACEMENT_MAP)} hardcoded values with constants")

    files = find_core_files()
    print(f"📁 Found {len(files)} files to analyze")

    total_files_changed = 0
    total_replacements = 0

    for file_path in files:
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()

            # Check if file contains any hardcoded values
            has_hardcoded = any(hardcoded in content for hardcoded in REPLACEMENT_MAP.keys())
            if not has_hardcoded:
                continue

            print(f"🔧 Refactoring {file_path.relative_to(Path('/home/kali/Desktop/AutoBot'))}...")
            if refactor_file(file_path):
                total_files_changed += 1

        except Exception as e:
            print(f"❌ Error processing {file_path}: {e}")

    print(f"\n✅ Network constants refactoring complete!")
    print(f"📊 Files modified: {total_files_changed}")
    print(f"🔄 Total patterns available for replacement: {len(REPLACEMENT_MAP)}")

    print(f"\n💡 Next steps:")
    print(f"   1. Test the refactored code")
    print(f"   2. Update any remaining hardcoded values manually")
    print(f"   3. Add environment-specific configuration")

if __name__ == "__main__":
    main()