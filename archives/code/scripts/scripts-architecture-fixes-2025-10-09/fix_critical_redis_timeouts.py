#!/usr/bin/env python3
"""
Fix Critical Redis Timeout Issues
=================================

This script addresses the most critical Redis timeout configuration issues
identified in the comprehensive timeout audit.

Focus areas:
1. Standardize Redis connection timeouts in analysis scripts
2. Fix hardcoded Redis timeout values
3. Update Redis pool configurations
4. Ensure consistency across all Redis connections
"""

import os
import re
import sys
import logging
from pathlib import Path
from typing import Dict, List, Tuple

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class RedisTimeoutFixer:
    """Fixes critical Redis timeout configuration issues"""

    def __init__(self, project_root: str):
        self.project_root = Path(project_root)
        self.standard_timeouts = {
            'socket_timeout': 5.0,
            'socket_connect_timeout': 5.0,
            'retry_on_timeout': True,
            'max_retries': 3
        }

        # Files with known Redis timeout issues
        self.redis_files = [
            'fix_analytics_redis_timeout.py',
            'reorganize_redis_databases.py',
            'create_code_vector_knowledge.py',
            'migrate_vectors_to_db0.py',
            'fix_index_dimensions.py',
            'analyze_code_vectors_for_issues.py'
        ]

    def fix_all_redis_timeouts(self, dry_run: bool = True) -> Dict[str, bool]:
        """Fix Redis timeouts in all identified files"""
        results = {}

        logger.info(f"Fixing Redis timeouts in {len(self.redis_files)} files...")

        for file_path in self.redis_files:
            full_path = self.project_root / file_path
            if full_path.exists():
                success = self.fix_file_redis_timeouts(full_path, dry_run)
                results[file_path] = success
                if success:
                    logger.info(f"✅ {'[DRY RUN] ' if dry_run else ''}Fixed: {file_path}")
                else:
                    logger.warning(f"❌ Could not fix: {file_path}")
            else:
                logger.warning(f"⚠️ File not found: {file_path}")
                results[file_path] = False

        return results

    def fix_file_redis_timeouts(self, file_path: Path, dry_run: bool = True) -> bool:
        """Fix Redis timeouts in a specific file"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()

            original_content = content

            # Fix common Redis timeout patterns
            content = self._fix_redis_connection_patterns(content)
            content = self._fix_redis_pool_patterns(content)
            content = self._add_timeout_imports_if_needed(content, file_path)

            if content != original_content:
                if not dry_run:
                    # Create backup
                    backup_path = f"{file_path}.redis_timeout_backup"
                    with open(backup_path, 'w', encoding='utf-8') as f:
                        f.write(original_content)

                    # Write fixed content
                    with open(file_path, 'w', encoding='utf-8') as f:
                        f.write(content)

                    logger.info(f"Fixed Redis timeouts in {file_path.name} (backup: {backup_path})")
                else:
                    logger.info(f"[DRY RUN] Would fix Redis timeouts in {file_path.name}")
                return True
            else:
                logger.info(f"No changes needed for {file_path.name}")
                return True

        except Exception as e:
            logger.error(f"Error processing {file_path}: {e}")
            return False

    def _fix_redis_connection_patterns(self, content: str) -> str:
        """Fix direct Redis connection timeout patterns"""

        # Pattern 1: socket_timeout=number
        content = re.sub(
            r'socket_timeout\s*=\s*\d+(?:\.\d+)?',
            f'socket_timeout={self.standard_timeouts["socket_timeout"]}',
            content
        )

        # Pattern 2: socket_connect_timeout=number
        content = re.sub(
            r'socket_connect_timeout\s*=\s*\d+(?:\.\d+)?',
            f'socket_connect_timeout={self.standard_timeouts["socket_connect_timeout"]}',
            content
        )

        # Pattern 3: Multi-line Redis connection with various timeouts
        redis_connection_pattern = re.compile(
            r'redis\.Redis\s*\(\s*([^)]+)\s*\)',
            re.MULTILINE | re.DOTALL
        )

        def fix_redis_constructor(match):
            params = match.group(1)

            # Update socket_timeout
            if 'socket_timeout' in params:
                params = re.sub(
                    r'socket_timeout\s*=\s*\d+(?:\.\d+)?',
                    f'socket_timeout={self.standard_timeouts["socket_timeout"]}',
                    params
                )
            else:
                # Add socket_timeout if not present
                params += f',\n                socket_timeout={self.standard_timeouts["socket_timeout"]}'

            # Update socket_connect_timeout
            if 'socket_connect_timeout' in params:
                params = re.sub(
                    r'socket_connect_timeout\s*=\s*\d+(?:\.\d+)?',
                    f'socket_connect_timeout={self.standard_timeouts["socket_connect_timeout"]}',
                    params
                )
            else:
                # Add socket_connect_timeout if not present
                params += f',\n                socket_connect_timeout={self.standard_timeouts["socket_connect_timeout"]}'

            return f'redis.Redis({params})'

        content = redis_connection_pattern.sub(fix_redis_constructor, content)

        return content

    def _fix_redis_pool_patterns(self, content: str) -> str:
        """Fix Redis pool configuration patterns"""

        # Fix ConnectionPool timeout configurations
        pool_pattern = re.compile(
            r'redis\.ConnectionPool\s*\(\s*([^)]+)\s*\)',
            re.MULTILINE | re.DOTALL
        )

        def fix_pool_constructor(match):
            params = match.group(1)

            # Update socket_timeout
            if 'socket_timeout' in params:
                params = re.sub(
                    r'socket_timeout\s*=\s*\d+(?:\.\d+)?',
                    f'socket_timeout={self.standard_timeouts["socket_timeout"]}',
                    params
                )

            # Update socket_connect_timeout
            if 'socket_connect_timeout' in params:
                params = re.sub(
                    r'socket_connect_timeout\s*=\s*\d+(?:\.\d+)?',
                    f'socket_connect_timeout={self.standard_timeouts["socket_connect_timeout"]}',
                    params
                )

            return f'redis.ConnectionPool({params})'

        content = pool_pattern.sub(fix_pool_constructor, content)

        return content

    def _add_timeout_imports_if_needed(self, content: str, file_path: Path) -> str:
        """Add timeout configuration imports if the file could benefit from them"""

        # Check if file uses Redis and could benefit from standardized config
        if 'redis.Redis(' in content and 'from src.config.timeout_config' not in content:

            # Add import after existing imports
            import_lines = []
            other_lines = []
            in_imports = True

            for line in content.split('\n'):
                if in_imports and (line.startswith('import ') or line.startswith('from ') or line.strip() == '' or line.startswith('#')):
                    import_lines.append(line)
                else:
                    in_imports = False
                    other_lines.append(line)

            # Add timeout config import
            if import_lines:
                import_lines.append('')
                import_lines.append('# Standardized timeout configuration')
                import_lines.append('try:')
                import_lines.append('    from src.config.timeout_config import get_redis_timeout_config')
                import_lines.append('    REDIS_TIMEOUTS = get_redis_timeout_config()')
                import_lines.append('except ImportError:')
                import_lines.append('    # Fallback for standalone scripts')
                import_lines.append('    REDIS_TIMEOUTS = {')
                import_lines.append(f'        "socket_timeout": {self.standard_timeouts["socket_timeout"]},')
                import_lines.append(f'        "socket_connect_timeout": {self.standard_timeouts["socket_connect_timeout"]},')
                import_lines.append(f'        "retry_on_timeout": {self.standard_timeouts["retry_on_timeout"]},')
                import_lines.append(f'        "max_retries": {self.standard_timeouts["max_retries"]}')
                import_lines.append('    }')

                content = '\n'.join(import_lines + other_lines)

        return content

    def create_redis_timeout_helper(self) -> str:
        """Create a helper module for standardized Redis connections"""
        helper_content = '''"""
Redis Connection Helper with Standardized Timeouts
=================================================

Helper module for creating Redis connections with standardized timeout
configurations across AutoBot.

Usage:
    from src.utils.redis_helper import get_redis_connection, get_async_redis_connection

    # Synchronous Redis connection
    redis_client = get_redis_connection(db=0)

    # Asynchronous Redis connection
    async_client = await get_async_redis_connection(db=0)
"""

import redis
import redis.asyncio as aioredis
from typing import Optional

try:
    from src.config.timeout_config import get_redis_timeout_config
    TIMEOUT_CONFIG = get_redis_timeout_config()
except ImportError:
    # Fallback configuration
    TIMEOUT_CONFIG = {
        'socket_timeout': 5.0,
        'socket_connect_timeout': 5.0,
        'retry_on_timeout': True,
        'max_retries': 3
    }


def get_redis_connection(
    host: str = "172.16.168.23",
    port: int = 6379,
    db: int = 0,
    password: Optional[str] = None,
    **kwargs
) -> redis.Redis:
    """
    Get a standardized synchronous Redis connection

    Args:
        host: Redis host (default: 172.16.168.23)
        port: Redis port (default: 6379)
        db: Database number (default: 0)
        password: Redis password if required
        **kwargs: Additional Redis connection parameters

    Returns:
        Configured Redis client
    """
    connection_params = {
        'host': host,
        'port': port,
        'db': db,
        'password': password,
        'socket_timeout': TIMEOUT_CONFIG['socket_timeout'],
        'socket_connect_timeout': TIMEOUT_CONFIG['socket_connect_timeout'],
        'retry_on_timeout': TIMEOUT_CONFIG['retry_on_timeout'],
        'decode_responses': True,
        **kwargs
    }

    # Remove None values
    connection_params = {k: v for k, v in connection_params.items() if v is not None}

    return redis.Redis(**connection_params)


async def get_async_redis_connection(
    host: str = "172.16.168.23",
    port: int = 6379,
    db: int = 0,
    password: Optional[str] = None,
    **kwargs
) -> aioredis.Redis:
    """
    Get a standardized asynchronous Redis connection

    Args:
        host: Redis host (default: 172.16.168.23)
        port: Redis port (default: 6379)
        db: Database number (default: 0)
        password: Redis password if required
        **kwargs: Additional Redis connection parameters

    Returns:
        Configured async Redis client
    """
    connection_params = {
        'host': host,
        'port': port,
        'db': db,
        'password': password,
        'socket_timeout': TIMEOUT_CONFIG['socket_timeout'],
        'socket_connect_timeout': TIMEOUT_CONFIG['socket_connect_timeout'],
        'retry_on_timeout': TIMEOUT_CONFIG['retry_on_timeout'],
        'decode_responses': True,
        **kwargs
    }

    # Remove None values
    connection_params = {k: v for k, v in connection_params.items() if v is not None}

    return aioredis.Redis(**connection_params)


def get_redis_pool(
    host: str = "172.16.168.23",
    port: int = 6379,
    db: int = 0,
    password: Optional[str] = None,
    max_connections: int = 20,
    **kwargs
) -> redis.ConnectionPool:
    """
    Get a standardized Redis connection pool

    Args:
        host: Redis host (default: 172.16.168.23)
        port: Redis port (default: 6379)
        db: Database number (default: 0)
        password: Redis password if required
        max_connections: Maximum connections in pool (default: 20)
        **kwargs: Additional pool parameters

    Returns:
        Configured Redis connection pool
    """
    pool_params = {
        'host': host,
        'port': port,
        'db': db,
        'password': password,
        'max_connections': max_connections,
        'socket_timeout': TIMEOUT_CONFIG['socket_timeout'],
        'socket_connect_timeout': TIMEOUT_CONFIG['socket_connect_timeout'],
        'retry_on_timeout': TIMEOUT_CONFIG['retry_on_timeout'],
        **kwargs
    }

    # Remove None values
    pool_params = {k: v for k, v in pool_params.items() if v is not None}

    return redis.ConnectionPool(**pool_params)


class RedisConnectionManager:
    """Managed Redis connections with automatic cleanup"""

    def __init__(self):
        self._connections = {}
        self._pools = {}

    def get_connection(self, db: int = 0, **kwargs) -> redis.Redis:
        """Get or create a Redis connection for the specified database"""
        if db not in self._connections:
            self._connections[db] = get_redis_connection(db=db, **kwargs)
        return self._connections[db]

    async def get_async_connection(self, db: int = 0, **kwargs) -> aioredis.Redis:
        """Get or create an async Redis connection for the specified database"""
        if db not in self._connections:
            self._connections[db] = await get_async_redis_connection(db=db, **kwargs)
        return self._connections[db]

    def close_all(self):
        """Close all managed connections"""
        for conn in self._connections.values():
            if hasattr(conn, 'close'):
                conn.close()
        self._connections.clear()

        for pool in self._pools.values():
            if hasattr(pool, 'disconnect'):
                pool.disconnect()
        self._pools.clear()


# Global connection manager instance
redis_manager = RedisConnectionManager()
'''

        helper_path = self.project_root / 'src' / 'utils' / 'redis_helper.py'
        helper_path.parent.mkdir(parents=True, exist_ok=True)

        with open(helper_path, 'w') as f:
            f.write(helper_content)

        logger.info(f"Created Redis helper module: {helper_path}")
        return str(helper_path)

    def validate_fixes(self) -> Dict[str, List[str]]:
        """Validate that fixes were applied correctly"""
        validation_results = {
            'passed': [],
            'failed': [],
            'warnings': []
        }

        for file_path in self.redis_files:
            full_path = self.project_root / file_path
            if full_path.exists():
                try:
                    with open(full_path, 'r') as f:
                        content = f.read()

                    # Check for standardized timeout values
                    has_standard_socket_timeout = f'socket_timeout={self.standard_timeouts["socket_timeout"]}' in content
                    has_standard_connect_timeout = f'socket_connect_timeout={self.standard_timeouts["socket_connect_timeout"]}' in content

                    if has_standard_socket_timeout and has_standard_connect_timeout:
                        validation_results['passed'].append(file_path)
                    elif has_standard_socket_timeout or has_standard_connect_timeout:
                        validation_results['warnings'].append(f"{file_path}: Partially fixed")
                    else:
                        validation_results['failed'].append(f"{file_path}: No standard timeouts found")

                except Exception as e:
                    validation_results['failed'].append(f"{file_path}: Error reading file - {e}")

        return validation_results


def main():
    """Main execution function"""
    import argparse

    parser = argparse.ArgumentParser(description='Fix Critical Redis Timeout Issues')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be changed without making changes')
    parser.add_argument('--validate', action='store_true', help='Validate that fixes were applied correctly')
    parser.add_argument('--create-helper', action='store_true', help='Create Redis connection helper module')
    parser.add_argument('--project-root', default='.', help='Project root directory')

    args = parser.parse_args()

    fixer = RedisTimeoutFixer(args.project_root)

    logger.info("Starting Redis timeout fixes...")

    if args.create_helper:
        helper_path = fixer.create_redis_timeout_helper()
        logger.info(f"Created Redis helper: {helper_path}")

    # Fix Redis timeouts
    results = fixer.fix_all_redis_timeouts(dry_run=args.dry_run)

    # Print results
    success_count = sum(1 for success in results.values() if success)
    logger.info(f"\n=== REDIS TIMEOUT FIX RESULTS ===")
    logger.info(f"Files processed: {len(results)}")
    logger.info(f"Successfully fixed: {success_count}")
    logger.info(f"Failed: {len(results) - success_count}")

    if args.validate:
        logger.info("\nValidating fixes...")
        validation = fixer.validate_fixes()
        logger.info(f"Validation passed: {len(validation['passed'])}")
        logger.info(f"Validation warnings: {len(validation['warnings'])}")
        logger.info(f"Validation failed: {len(validation['failed'])}")

        if validation['warnings']:
            logger.warning("Warnings:")
            for warning in validation['warnings']:
                logger.warning(f"  - {warning}")

        if validation['failed']:
            logger.error("Failed validations:")
            for failure in validation['failed']:
                logger.error(f"  - {failure}")

    if not args.dry_run:
        logger.info("\n✅ Redis timeout fixes completed!")
        logger.info("Next steps:")
        logger.info("1. Test Redis connections in development environment")
        logger.info("2. Update any remaining scripts to use src.utils.redis_helper")
        logger.info("3. Monitor Redis connection performance after deployment")
    else:
        logger.info("\n📋 Dry run completed - use --dry-run=false to apply fixes")


if __name__ == '__main__':
    main()
