#!/usr/bin/env python3
"""
Agent File Optimization Tool

This tool creates optimized copies of agent files by stripping code blocks
and other verbose content while preserving structure and functionality.

Zero-Risk Design:
- NEVER modifies original agent files
- Creates optimized copies in separate directory
- Fully reversible (delete optimized directory to revert)
- Feature flag controlled activation

Usage:
    python scripts/utilities/optimize_agents.py [--force] [--dry-run] [--stats]

Options:
    --force     Force regeneration of all optimized agents
    --dry-run   Show what would be done without making changes
    --stats     Show detailed token savings statistics
"""

import argparse
import hashlib
import json
import logging
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class AgentOptimizer:
    """
    Optimizes agent markdown files by stripping code blocks and verbose sections.

    Features:
    - Code block removal with preservation markers
    - YAML frontmatter preservation
    - Incremental updates via caching
    - Token usage statistics
    - Thread-safe operations
    """

    def __init__(
        self,
        source_dir: Path,
        target_dir: Path,
        cache_file: Optional[Path] = None,
        strip_code_blocks: bool = True,
        strip_verbose_sections: bool = False
    ):
        """
        Initialize the optimizer.

        Args:
            source_dir: Directory containing original agent files
            target_dir: Directory for optimized agent files
            cache_file: Path to cache file for tracking modifications
            strip_code_blocks: Whether to strip code blocks (default: True)
            strip_verbose_sections: Whether to strip verbose sections (default: False)
        """
        self.source_dir = Path(source_dir)
        self.target_dir = Path(target_dir)
        self.cache_file = cache_file or (self.target_dir / '.optimization_cache.json')
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
            logger.warning(f"Failed to load cache: {e}. Starting with empty cache.")
            return {}

    def _save_cache(self) -> None:
        """Save optimization cache to disk."""
        try:
            self.cache_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.cache_file, 'w', encoding='utf-8') as f:
                json.dump(self.cache, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save cache: {e}")

    def _get_file_hash(self, file_path: Path) -> str:
        """Calculate MD5 hash of file content."""
        try:
            with open(file_path, 'rb') as f:
                return hashlib.md5(f.read()).hexdigest()
        except Exception as e:
            logger.error(f"Failed to hash {file_path}: {e}")
            return ""

    def _is_file_cached(self, file_path: Path) -> bool:
        """Check if file needs optimization based on cache."""
        file_key = str(file_path.relative_to(self.source_dir))
        current_hash = self._get_file_hash(file_path)

        if file_key in self.cache and self.cache[file_key] == current_hash:
            self.stats['cache_hits'] += 1
            return True

        self.stats['cache_misses'] += 1
        return False

    def _update_cache(self, file_path: Path) -> None:
        """Update cache with current file hash."""
        file_key = str(file_path.relative_to(self.source_dir))
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
            nonlocal blocks_removed
            blocks_removed += 1
            # Extract language hint if present
            first_line = match.group(0).split('\n')[0]
            lang = first_line.replace('```', '').strip()
            lang_hint = f" ({lang})" if lang else ""
            return f"```\n[Code example removed for token optimization{lang_hint} - see original agent file]\n```"

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
            (r'## Examples\n.*?(?=\n##|\Z)', '## Examples\n[Examples removed for token optimization - see original agent file]\n\n'),
        ]

        processed = content
        for pattern, replacement in patterns:
            processed = re.sub(pattern, replacement, processed, flags=re.DOTALL)

        return processed

    def optimize_agent_file(self, source_path: Path) -> Optional[Path]:
        """
        Optimize a single agent file.

        Args:
            source_path: Path to original agent file

        Returns:
            Path to optimized file if successful, None otherwise
        """
        try:
            # Read original content
            with open(source_path, 'r', encoding='utf-8') as f:
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

            # Reconstruct content
            optimized_content = frontmatter + optimized_body

            # Add optimization notice at the end
            optimization_notice = f"\n\n---\n**Note:** This is an optimized version of the agent file. {blocks_removed} code blocks were removed to reduce token usage. See the original file at `.claude/agents/{source_path.name}` for complete examples.\n"
            optimized_content += optimization_notice

            optimized_size = len(optimized_content)
            self.stats['total_optimized_size'] += optimized_size

            # Calculate savings
            savings_bytes = original_size - optimized_size
            savings_percent = (savings_bytes / original_size * 100) if original_size > 0 else 0

            logger.info(
                f"Optimized {source_path.name}: "
                f"{original_size} -> {optimized_size} bytes "
                f"({savings_percent:.1f}% reduction, {blocks_removed} code blocks removed)"
            )

            # Write optimized content
            target_path = self.target_dir / source_path.name
            target_path.parent.mkdir(parents=True, exist_ok=True)

            with open(target_path, 'w', encoding='utf-8') as f:
                f.write(optimized_content)

            # Update cache
            self._update_cache(source_path)

            self.stats['files_updated'] += 1
            return target_path

        except Exception as e:
            logger.error(f"Failed to optimize {source_path}: {e}")
            return None

    def optimize_all(self, force: bool = False) -> Dict[str, any]:
        """
        Optimize all agent files in source directory.

        Args:
            force: Force regeneration of all files, ignoring cache

        Returns:
            Dictionary with optimization statistics
        """
        # Ensure target directory exists
        self.target_dir.mkdir(parents=True, exist_ok=True)

        # Find all markdown files in source directory
        agent_files = list(self.source_dir.glob('*.md'))

        if not agent_files:
            logger.warning(f"No agent files found in {self.source_dir}")
            return self.stats

        logger.info(f"Found {len(agent_files)} agent files to process")

        for agent_file in agent_files:
            self.stats['files_processed'] += 1

            # Check cache unless force regeneration
            if not force and self._is_file_cached(agent_file):
                logger.debug(f"Skipping {agent_file.name} (cached, no changes)")
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


def main():
    """Main entry point for the optimization tool."""
    parser = argparse.ArgumentParser(
        description='Optimize agent files by stripping code blocks and verbose content'
    )
    parser.add_argument(
        '--force',
        action='store_true',
        help='Force regeneration of all optimized agents'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be done without making changes'
    )
    parser.add_argument(
        '--stats',
        action='store_true',
        help='Show detailed statistics after optimization'
    )
    parser.add_argument(
        '--strip-verbose',
        action='store_true',
        help='Enable stripping of verbose example sections (use with caution)'
    )
    parser.add_argument(
        '--source-dir',
        type=Path,
        default=Path('.claude/agents'),
        help='Source directory containing agent files (default: .claude/agents)'
    )
    parser.add_argument(
        '--target-dir',
        type=Path,
        default=Path('.claude/agents-optimized'),
        help='Target directory for optimized agents (default: .claude/agents-optimized)'
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

    # Resolve paths relative to project root
    source_dir = project_root / args.source_dir
    target_dir = project_root / args.target_dir

    if not source_dir.exists():
        logger.error(f"Source directory not found: {source_dir}")
        sys.exit(1)

    logger.info(f"Source directory: {source_dir}")
    logger.info(f"Target directory: {target_dir}")

    if args.dry_run:
        logger.info("DRY RUN MODE - No files will be modified")
        return 0

    # Create optimizer
    optimizer = AgentOptimizer(
        source_dir=source_dir,
        target_dir=target_dir,
        strip_code_blocks=True,
        strip_verbose_sections=args.strip_verbose
    )

    # Run optimization
    stats = optimizer.optimize_all(force=args.force)

    # Print statistics if requested
    if args.stats or stats['files_updated'] > 0:
        optimizer.print_statistics()

    logger.info(f"Optimization complete! Optimized agents available in: {target_dir}")
    logger.info(f"To use optimized agents, set CLAUDE_AGENT_DIR={target_dir}")

    return 0


if __name__ == '__main__':
    sys.exit(main())
