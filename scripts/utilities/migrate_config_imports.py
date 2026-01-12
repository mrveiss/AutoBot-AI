#!/usr/bin/env python3
"""
AutoBot - AI-Powered Automation Platform
Copyright (c) 2025 mrveiss
Author: mrveiss

Automated Config Import Migration Script
Migrates files from old config.py imports to unified_config.py

Usage:
    python scripts/utilities/migrate_config_imports.py --file path/to/file.py
    python scripts/utilities/migrate_config_imports.py --batch production
    python scripts/utilities/migrate_config_imports.py --dry-run --batch all
"""

import argparse
import ast
import re
import shutil
import sys
from pathlib import Path
from typing import List, Tuple

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))


class ConfigMigrator:
    """Migrates config imports from old system to unified_config.py"""

    # Import patterns to detect
    IMPORT_PATTERNS = [
        re.compile(r'^from\s+src\.config\s+import\s+(.+)$', re.MULTILINE),
        re.compile(r'^from\s+config\s+import\s+(.+)$', re.MULTILINE),
        re.compile(r'^import\s+config$', re.MULTILINE),
        re.compile(r'^from\s+src\.config\s+import\s+config$', re.MULTILINE),
    ]

    # Files to skip (archived, already migrated, etc.)
    SKIP_PATTERNS = [
        'archives/',
        'src/archive/',
        'unified_config.py',
        'unified_config_old.py',
        'unified_config_shim.py',
        'config.py',
        'config_consolidated.py',
        'config_helper.py',
        '.pyc',
        '__pycache__',
    ]

    def __init__(self, dry_run: bool = False):
        """Initialize config migrator with dry run mode and file tracking lists."""
        self.dry_run = dry_run
        self.migrated_files = []
        self.failed_files = []
        self.skipped_files = []

    def should_skip(self, file_path: str) -> bool:
        """Check if file should be skipped"""
        return any(pattern in file_path for pattern in self.SKIP_PATTERNS)

    def detect_config_imports(self, content: str) -> List[Tuple[str, str]]:
        """Detect old config import patterns in file content

        Returns:
            List of (pattern, match) tuples
        """
        matches = []
        for pattern in self.IMPORT_PATTERNS:
            for match in pattern.finditer(content):
                matches.append((pattern.pattern, match.group(0)))
        return matches

    def migrate_imports(self, content: str) -> str:
        """Migrate config imports to unified_config

        Handles various import patterns:
        - from src.config import config -> from src.config import UnifiedConfig
        - from config import config -> from src.config import UnifiedConfig
        - import config -> from src.config import UnifiedConfig

        Then initializes: config = UnifiedConfig()
        """
        lines = content.split('\n')
        new_lines = []
        needs_initialization = False
        import_line_index = -1

        for i, line in enumerate(lines):
            modified = False

            # Pattern 1: from src.config import config
            if re.match(r'^from\s+src\.config\s+import\s+config', line):
                new_lines.append('from src.config import UnifiedConfig')
                needs_initialization = True
                import_line_index = len(new_lines) - 1
                modified = True

            # Pattern 2: from config import config
            elif re.match(r'^from\s+config\s+import\s+config', line):
                new_lines.append('from src.config import UnifiedConfig')
                needs_initialization = True
                import_line_index = len(new_lines) - 1
                modified = True

            # Pattern 3: import config
            elif re.match(r'^import\s+config$', line):
                new_lines.append('from src.config import UnifiedConfig')
                needs_initialization = True
                import_line_index = len(new_lines) - 1
                modified = True

            # Pattern 4: from src.config import Config (class-based)
            elif re.match(r'^from\s+src\.config\s+import\s+Config', line):
                new_lines.append('from src.config import UnifiedConfig as Config')
                modified = True

            if not modified:
                new_lines.append(line)

        # Add config initialization after import if needed
        if needs_initialization and import_line_index != -1:
            # Find next non-empty, non-import line to insert initialization
            insert_index = import_line_index + 1
            while insert_index < len(new_lines) and (
                not new_lines[insert_index].strip() or
                new_lines[insert_index].startswith('import') or
                new_lines[insert_index].startswith('from')
            ):
                insert_index += 1

            # Insert initialization
            new_lines.insert(insert_index, '')
            new_lines.insert(insert_index + 1, '# Initialize unified config')
            new_lines.insert(insert_index + 2, 'config = UnifiedConfig()')

        return '\n'.join(new_lines)

    def validate_syntax(self, content: str, file_path: str) -> bool:
        """Validate Python syntax after migration"""
        try:
            ast.parse(content)
            return True
        except SyntaxError as e:
            print(f"❌ Syntax error in {file_path}: {e}")
            return False

    def migrate_file(self, file_path: str) -> bool:
        """Migrate a single file

        Returns:
            True if migration successful, False otherwise
        """
        if self.should_skip(file_path):
            self.skipped_files.append(file_path)
            print(f"⏭️  Skipped: {file_path}")
            return False

        try:
            # Read file
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()

            # Detect imports
            imports = self.detect_config_imports(content)
            if not imports:
                print(f"ℹ️  No config imports found: {file_path}")
                return False

            print(f"\n📝 Migrating: {file_path}")
            print(f"   Found {len(imports)} import(s) to migrate")

            # Migrate
            migrated_content = self.migrate_imports(content)

            # Validate syntax
            if not self.validate_syntax(migrated_content, file_path):
                self.failed_files.append(file_path)
                return False

            if self.dry_run:
                print(f"   [DRY RUN] Would migrate {file_path}")
                return True

            # Backup original
            backup_path = f"{file_path}.backup"
            shutil.copy2(file_path, backup_path)

            # Write migrated content
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(migrated_content)

            print(f"✅ Migrated successfully (backup: {backup_path})")
            self.migrated_files.append(file_path)
            return True

        except Exception as e:
            print(f"❌ Error migrating {file_path}: {e}")
            self.failed_files.append(file_path)
            return False

    def get_file_list(self, batch: str) -> List[str]:
        """Get list of files to migrate based on batch type

        Args:
            batch: 'production', 'scripts', 'tools', or 'all'
        """
        files = []

        if batch == 'production':
            # Production-critical files
            patterns = [
                'backend/app_factory.py',
                'backend/api/*.py',
                'backend/services/*.py',
                'backend/utils/*.py',
                'src/orchestrator.py',
                'src/llm_interface.py',
                'src/knowledge_base.py',
                'src/agents/*.py',
                'src/*.py',
            ]
        elif batch == 'scripts':
            patterns = [
                'scripts/*.py',
                'monitoring/*.py',
            ]
        elif batch == 'tools':
            patterns = [
                'tools/code-analysis-suite/src/*.py',
            ]
        elif batch == 'all':
            patterns = [
                'backend/**/*.py',
                'src/**/*.py',
                'scripts/**/*.py',
                'tools/**/*.py',
                'monitoring/**/*.py',
            ]
        else:
            raise ValueError(f"Unknown batch type: {batch}")

        # Collect files matching patterns
        for pattern in patterns:
            if '**' in pattern:
                # Recursive glob
                base_path = pattern.split('**')[0]
                for file_path in Path(project_root / base_path).rglob('*.py'):
                    if not self.should_skip(str(file_path)):
                        files.append(str(file_path))
            elif '*' in pattern:
                # Single-level glob
                for file_path in Path(project_root).glob(pattern):
                    if file_path.is_file() and not self.should_skip(str(file_path)):
                        files.append(str(file_path))
            else:
                # Exact file
                file_path = project_root / pattern
                if file_path.exists() and not self.should_skip(str(file_path)):
                    files.append(str(file_path))

        return sorted(set(files))

    def print_summary(self):
        """Print migration summary"""
        print("\n" + "="*60)
        print("MIGRATION SUMMARY")
        print("="*60)
        print(f"✅ Successfully migrated: {len(self.migrated_files)}")
        print(f"❌ Failed: {len(self.failed_files)}")
        print(f"⏭️  Skipped: {len(self.skipped_files)}")

        if self.failed_files:
            print("\n❌ Failed files:")
            for f in self.failed_files:
                print(f"   - {f}")

        if self.migrated_files and not self.dry_run:
            print("\n💡 Next steps:")
            print("1. Run tests to verify migrations")
            print("2. Review changes with: git diff")
            print("3. Remove backup files if satisfied: rm **/*.backup")
            print("4. Commit changes: git add . && git commit -m 'refactor: Migrate to unified_config (#142)'")


def main():
    """Entry point for config import migration CLI."""
    parser = argparse.ArgumentParser(
        description='Migrate config imports to unified_config.py'
    )
    parser.add_argument(
        '--file',
        help='Single file to migrate'
    )
    parser.add_argument(
        '--batch',
        choices=['production', 'scripts', 'tools', 'all'],
        help='Batch migration mode'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be migrated without making changes'
    )

    args = parser.parse_args()

    if not args.file and not args.batch:
        parser.error("Must specify either --file or --batch")

    migrator = ConfigMigrator(dry_run=args.dry_run)

    if args.file:
        # Migrate single file
        migrator.migrate_file(args.file)
    elif args.batch:
        # Batch migration
        files = migrator.get_file_list(args.batch)
        print(f"📋 Found {len(files)} files to process in '{args.batch}' batch")

        if args.dry_run:
            print("\n🔍 DRY RUN MODE - No files will be modified\n")

        for file_path in files:
            migrator.migrate_file(file_path)

    migrator.print_summary()


if __name__ == '__main__':
    main()
