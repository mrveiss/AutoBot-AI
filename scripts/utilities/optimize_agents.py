#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Agent File Optimization Tool - In-Place Edition

This tool optimizes agent files by stripping code blocks and other verbose content
while preserving structure and functionality. Uses git for backup and version control.

Git-Based Backup Design:
- Creates timestamped git tags before optimization
- Commits optimized files with detailed statistics
- Fully reversible via git restore
- No duplicate directories needed

Usage:
    python scripts/utilities/optimize_agents.py [--force] [--stats] [--restore [TAG]]

Options:
    --force         Force regeneration of all optimized agents
    --stats         Show detailed token savings statistics
    --restore       Restore agents from most recent backup tag
    --restore TAG   Restore agents from specific tag
    --list-backups  List all available backup tags
"""

import argparse
import hashlib
import json
import logging
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional, Tuple

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class AgentOptimizer:
    """
    Optimizes agent markdown files in-place by stripping code blocks and verbose sections.

    Features:
    - In-place optimization of .claude/agents/ directory
    - Git-based backup via tags before optimization
    - Automatic git commit after optimization
    - Code block removal with preservation markers
    - YAML frontmatter preservation
    - Incremental updates via caching
    - Token usage statistics
    - Full restore capability via git
    """

    def __init__(
        self,
        agent_dir: Path,
        cache_file: Optional[Path] = None,
        strip_code_blocks: bool = True,
        strip_verbose_sections: bool = False
    ):
        """
        Initialize the optimizer.

        Args:
            agent_dir: Directory containing agent files (will be modified in-place)
            cache_file: Path to cache file for tracking modifications
            strip_code_blocks: Whether to strip code blocks (default: True)
            strip_verbose_sections: Whether to strip verbose sections (default: False)
        """
        self.agent_dir = Path(agent_dir)
        self.cache_file = cache_file or (self.agent_dir / '.optimization_cache.json')
        self.strip_code_blocks = strip_code_blocks
        self.strip_verbose_sections = strip_verbose_sections

        # Statistics tracking
        self.stats = {
            'files_processed': 0,
            'files_skipped': 0,
            'files_updated': 0,
            'total_original_size': 0,
            'total_optimized_size': 0,
            'code_blocks_removed': 0,
            'cache_hits': 0,
            'cache_misses': 0
        }

        # Load cache
        self.cache = self._load_cache()

    def _load_cache(self) -> Dict[str, str]:
        """Load optimization cache from disk."""
        if not self.cache_file.exists():
            return {}

        try:
            with open(self.cache_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.warning("Failed to load cache: %s. Starting with empty cache.", e)
            return {}

    def _save_cache(self) -> None:
        """Save optimization cache to disk."""
        try:
            with open(self.cache_file, 'w', encoding='utf-8') as f:
                json.dump(self.cache, f, indent=2)
        except Exception as e:
            logger.error("Failed to save cache: %s", e)

    def _get_file_hash(self, file_path: Path) -> str:
        """Calculate MD5 hash of file content."""
        try:
            with open(file_path, 'rb') as f:
                return hashlib.md5(f.read()).hexdigest()
        except Exception as e:
            logger.error("Failed to hash %s: %s", file_path, e)
            return ""

    def _is_file_cached(self, file_path: Path) -> bool:
        """Check if file needs optimization based on cache."""
        file_key = str(file_path.name)
        current_hash = self._get_file_hash(file_path)

        if file_key in self.cache and self.cache[file_key] == current_hash:
            self.stats['cache_hits'] += 1
            return True

        self.stats['cache_misses'] += 1
        return False

    def _update_cache(self, file_path: Path) -> None:
        """Update cache with current file hash."""
        file_key = str(file_path.name)
        current_hash = self._get_file_hash(file_path)
        self.cache[file_key] = current_hash

    def _extract_frontmatter(self, content: str) -> Tuple[str, str]:
        """
        Extract YAML frontmatter from markdown content.

        Returns:
            Tuple of (frontmatter, body)
        """
        if not content.startswith('---'):
            return '', content

        # Find the closing ---
        parts = content.split('---', 2)
        if len(parts) >= 3:
            return f"---{parts[1]}---", parts[2]

        return '', content

    def _strip_code_blocks_from_content(self, content: str) -> Tuple[str, int]:
        """
        Strip code blocks from content while preserving structure.

        Returns:
            Tuple of (processed_content, num_blocks_removed)
        """
        if not self.strip_code_blocks:
            return content, 0

        # Pattern to match code blocks: ```...```
        code_block_pattern = re.compile(
            r'```[a-zA-Z]*\n.*?\n```',
            re.DOTALL
        )

        blocks_removed = 0

        def replace_code_block(match):
            """Replace code block with token-optimized placeholder."""
            nonlocal blocks_removed
            blocks_removed += 1
            # Extract language hint if present
            first_line = match.group(0).split('\n')[0]
            lang = first_line.replace('```', '').strip()
            lang_hint = f" ({lang})" if lang else ""
            return f"```\n[Code example removed for token optimization{lang_hint}]\n```"

        processed = code_block_pattern.sub(replace_code_block, content)
        return processed, blocks_removed

    def _strip_verbose_sections(self, content: str) -> str:
        """
        Strip verbose example sections while preserving key information.

        This is more aggressive and disabled by default for safety.
        """
        if not self.strip_verbose_sections:
            return content

        # Only strip sections explicitly marked as verbose
        # Be conservative to maintain agent functionality
        patterns = [
            (r'## Examples\n.*?(?=\n##|\Z)', '## Examples\n[Examples removed for token optimization]\n\n'),
        ]

        processed = content
        for pattern, replacement in patterns:
            processed = re.sub(pattern, replacement, processed, flags=re.DOTALL)

        return processed

    def optimize_agent_file(self, file_path: Path) -> bool:
        """
        Optimize a single agent file in-place.

        Args:
            file_path: Path to agent file to optimize

        Returns:
            True if file was modified, False if skipped or unchanged
        """
        try:
            # Read original content
            with open(file_path, 'r', encoding='utf-8') as f:
                original_content = f.read()

            original_size = len(original_content)
            self.stats['total_original_size'] += original_size

            # Extract frontmatter (YAML metadata)
            frontmatter, body = self._extract_frontmatter(original_content)

            # Apply optimizations to body only
            optimized_body = body

            # Strip code blocks
            optimized_body, blocks_removed = self._strip_code_blocks_from_content(optimized_body)
            self.stats['code_blocks_removed'] += blocks_removed

            # Strip verbose sections (if enabled)
            optimized_body = self._strip_verbose_sections(optimized_body)

            # Reconstruct content (no optimization notice needed for in-place)
            optimized_content = frontmatter + optimized_body

            optimized_size = len(optimized_content)
            self.stats['total_optimized_size'] += optimized_size

            # Check if content actually changed
            if optimized_content == original_content:
                logger.debug("No changes needed for %s", file_path.name)
                return False

            # Calculate savings
            savings_bytes = original_size - optimized_size
            savings_percent = (savings_bytes / original_size * 100) if original_size > 0 else 0

            logger.info(
                f"Optimized {file_path.name}: "
                f"{original_size} -> {optimized_size} bytes "
                f"({savings_percent:.1f}% reduction, {blocks_removed} code blocks removed)"
            )

            # Write optimized content back to same file
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(optimized_content)

            # Update cache
            self._update_cache(file_path)

            self.stats['files_updated'] += 1
            return True

        except Exception as e:
            logger.error("Failed to optimize %s: %s", file_path, e)
            return False

    def optimize_all(self, force: bool = False) -> Dict[str, any]:
        """
        Optimize all agent files in the directory.

        Args:
            force: Force regeneration of all files, ignoring cache

        Returns:
            Dictionary with optimization statistics
        """
        # Find all markdown files in agent directory
        agent_files = list(self.agent_dir.glob('*.md'))

        if not agent_files:
            logger.warning("No agent files found in %s", self.agent_dir)
            return self.stats

        logger.info("Found %s agent files to process", len(agent_files))

        for agent_file in agent_files:
            self.stats['files_processed'] += 1

            # Check cache unless force regeneration
            if not force and self._is_file_cached(agent_file):
                logger.debug("Skipping %s (cached, no changes)", agent_file.name)
                self.stats['files_skipped'] += 1
                continue

            # Optimize the file
            self.optimize_agent_file(agent_file)

        # Save cache
        self._save_cache()

        # Calculate final statistics
        if self.stats['total_original_size'] > 0:
            total_savings = self.stats['total_original_size'] - self.stats['total_optimized_size']
            total_savings_percent = (total_savings / self.stats['total_original_size']) * 100
            self.stats['total_savings_bytes'] = total_savings
            self.stats['total_savings_percent'] = total_savings_percent

        return self.stats

    def print_statistics(self) -> None:
        """Print detailed optimization statistics."""
        print("\n" + "=" * 70)
        print("AGENT OPTIMIZATION STATISTICS")
        print("=" * 70)
        print(f"Files processed:        {self.stats['files_processed']}")
        print(f"Files updated:          {self.stats['files_updated']}")
        print(f"Files skipped (cached): {self.stats['files_skipped']}")
        print(f"Cache hits:             {self.stats['cache_hits']}")
        print(f"Cache misses:           {self.stats['cache_misses']}")
        print("-" * 70)
        print(f"Code blocks removed:    {self.stats['code_blocks_removed']}")
        print(f"Original size:          {self.stats['total_original_size']:,} bytes")
        print(f"Optimized size:         {self.stats['total_optimized_size']:,} bytes")

        if 'total_savings_bytes' in self.stats:
            print(f"Total savings:          {self.stats['total_savings_bytes']:,} bytes "
                  f"({self.stats['total_savings_percent']:.1f}%)")

        print("=" * 70 + "\n")


def check_git_available() -> bool:
    """Check if git is available and we're in a git repository."""
    try:
        result = subprocess.run(
            ['git', 'rev-parse', '--git-dir'],
            capture_output=True,
            text=True,
            check=True
        )
        return result.returncode == 0
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


def create_backup_tag() -> str:
    """
    Create git tag before optimization.

    Returns:
        Tag name created
    """
    timestamp = datetime.now().strftime('%Y%m%d-%H%M%S')
    tag_name = f"agents-pre-optimization-{timestamp}"

    # Check for uncommitted changes in agents directory
    result = subprocess.run(
        ['git', 'status', '--porcelain', '.claude/agents/'],
        capture_output=True,
        text=True
    )

    if result.stdout.strip():
        logger.warning("⚠️  Uncommitted changes detected in .claude/agents/")
        logger.info("Creating backup tag anyway (recommended for safety)")

    # Create annotated tag
    try:
        subprocess.run(
            ['git', 'tag', '-a', tag_name, '-m',
             f'Backup before agent optimization {timestamp}'],
            check=True
        )
        logger.info("✅ Created backup tag: %s", tag_name)
        return tag_name
    except subprocess.CalledProcessError as e:
        logger.error("Failed to create git tag: %s", e)
        raise


def commit_optimization(stats: Dict[str, any]) -> None:
    """
    Commit optimized agent files.

    Args:
        stats: Optimization statistics dictionary
    """
    try:
        # Check if there are changes to commit
        result = subprocess.run(
            ['git', 'status', '--porcelain', '.claude/agents/'],
            capture_output=True,
            text=True
        )

        if not result.stdout.strip():
            logger.info("No changes to commit")
            return

        # Add modified files
        subprocess.run(['git', 'add', '.claude/agents/'], check=True)

        # Create detailed commit message
        reduction_pct = stats.get('total_savings_percent', 0)
        bytes_saved = stats.get('total_savings_bytes', 0)

        message = """chore(agents): optimize Claude Code agents for token efficiency

- Files optimized: {stats['files_updated']}
- Code blocks removed: {stats['code_blocks_removed']}
- Token reduction: {reduction_pct:.1f}%
- Bytes saved: {bytes_saved:,}

This optimization strips code examples from agent files to reduce
token usage while preserving all agent functionality and routing.
Generated by: scripts/utilities/optimize_agents.py"""

        # Commit changes
        subprocess.run(['git', 'commit', '-m', message], check=True)
        logger.info("✅ Changes committed to git")

    except subprocess.CalledProcessError as e:
        logger.error("Failed to commit changes: %s", e)
        raise


def restore_agents(tag_name: Optional[str] = None) -> None:
    """
    Restore agents from git tag.

    Args:
        tag_name: Specific tag to restore from, or None for most recent
    """
    try:
        if tag_name is None:
            # Find most recent backup tag
            result = subprocess.run(
                ['git', 'tag', '--list', 'agents-pre-optimization-*', '--sort=-creatordate'],
                capture_output=True,
                text=True,
                check=True
            )
            tags = [t for t in result.stdout.strip().split('\n') if t]
            if not tags:
                logger.error("❌ No backup tags found")
                logger.info("Available tags should match pattern: agents-pre-optimization-*")
                sys.exit(1)
            tag_name = tags[0]

        logger.info("Restoring from tag: %s", tag_name)

        # Restore files from tag
        subprocess.run(
            ['git', 'restore', '.claude/agents/', f'--source={tag_name}'],
            check=True
        )

        logger.info("✅ Agents restored from backup")
        logger.info("Restored from tag: %s", tag_name)

    except subprocess.CalledProcessError as e:
        logger.error("Failed to restore from git: %s", e)
        logger.info("Make sure the tag exists: git tag -l 'agents-pre-optimization-*'")
        sys.exit(1)


def list_backup_tags() -> None:
    """List all available backup tags."""
    try:
        result = subprocess.run(
            ['git', 'tag', '--list', 'agents-pre-optimization-*', '--sort=-creatordate'],
            capture_output=True,
            text=True,
            check=True
        )

        tags = [t for t in result.stdout.strip().split('\n') if t]

        if not tags:
            print("No backup tags found")
            return

        print("\nAvailable backup tags:")
        print("=" * 70)
        for tag in tags:
            # Get tag date
            result = subprocess.run(
                ['git', 'log', '-1', '--format=%ai', tag],
                capture_output=True,
                text=True
            )
            date = result.stdout.strip() if result.returncode == 0 else "unknown"
            print(f"  {tag:50s} {date}")
        print("=" * 70)

    except subprocess.CalledProcessError as e:
        logger.error("Failed to list tags: %s", e)


def main():
    """Main entry point for the optimization tool."""
    parser = argparse.ArgumentParser(
        description='Optimize agent files in-place with git-based backup'
    )
    parser.add_argument(
        '--force',
        action='store_true',
        help='Force regeneration of all optimized agents'
    )
    parser.add_argument(
        '--stats',
        action='store_true',
        help='Show detailed statistics after optimization'
    )
    parser.add_argument(
        '--restore',
        nargs='?',
        const='',
        metavar='TAG',
        help='Restore agents from backup tag (most recent if not specified)'
    )
    parser.add_argument(
        '--list-backups',
        action='store_true',
        help='List all available backup tags'
    )
    parser.add_argument(
        '--strip-verbose',
        action='store_true',
        help='Enable stripping of verbose example sections (use with caution)'
    )
    parser.add_argument(
        '--agent-dir',
        type=Path,
        default=Path('.claude/agents'),
        help='Agent directory to optimize (default: .claude/agents)'
    )

    args = parser.parse_args()

    # Find project root (directory containing .claude folder)
    current_dir = Path.cwd()
    project_root = current_dir

    while not (project_root / '.claude').exists() and project_root != project_root.parent:
        project_root = project_root.parent

    if not (project_root / '.claude').exists():
        logger.error("Could not find .claude directory. Run this script from AutoBot project root.")
        sys.exit(1)

    # Resolve agent directory relative to project root
    agent_dir = project_root / args.agent_dir

    if not agent_dir.exists():
        logger.error("Agent directory not found: %s", agent_dir)
        sys.exit(1)

    # Check git availability
    if not check_git_available():
        logger.error("Git is not available or not in a git repository")
        logger.error("This tool requires git for backup and version control")
        sys.exit(1)

    # Handle list backups
    if args.list_backups:
        list_backup_tags()
        return 0

    # Handle restore
    if args.restore is not None:
        tag_name = args.restore if args.restore else None
        restore_agents(tag_name)
        return 0

    # Run optimization
    logger.info("Agent directory: %s", agent_dir)
    logger.info("Optimization mode: IN-PLACE (files will be modified directly)")

    # Create backup tag before optimization
    backup_tag = create_backup_tag()
    logger.info("Backup tag created: %s", backup_tag)

    # Create optimizer
    optimizer = AgentOptimizer(
        agent_dir=agent_dir,
        strip_code_blocks=True,
        strip_verbose_sections=args.strip_verbose
    )

    # Run optimization
    stats = optimizer.optimize_all(force=args.force)

    # Print statistics if requested or if files were updated
    if args.stats or stats['files_updated'] > 0:
        optimizer.print_statistics()

    # Commit changes if files were updated
    if stats['files_updated'] > 0:
        commit_optimization(stats)
        logger.info("✅ Optimization complete and committed!")
        logger.info("To restore from backup: python %s --restore %s", __file__, backup_tag)
    else:
        logger.info("No files needed optimization (all up to date)")

    return 0


if __name__ == '__main__':
    sys.exit(main())
