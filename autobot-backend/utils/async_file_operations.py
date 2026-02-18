# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Async File Operations - Eliminates Synchronous File I/O Blocking

This module provides non-blocking file operations to prevent async event loop blocking
in the chat workflow and other async contexts.

ROOT CAUSE FIX: Replaces sync file I/O with proper async operations using asyncio.to_thread
"""

import asyncio
import functools
import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import aiofiles

logger = logging.getLogger(__name__)


class AsyncFileOperations:
    """
    Non-blocking file operations for async contexts

    ELIMINATES BLOCKING BY:
    - Using aiofiles for true async I/O
    - Wrapping sync operations with asyncio.to_thread()
    - Providing immediate returns with proper error handling
    - Caching frequently accessed files
    """

    def __init__(self):
        """Initialize async file operations with cache and TTL settings."""
        self.file_cache: Dict[str, Dict] = {}
        self.cache_ttl = 300  # 5 minutes

    async def read_text_file(
        self, file_path: Union[str, Path], encoding: str = "utf-8"
    ) -> str:
        """
        Read text file asynchronously without blocking

        ROOT CAUSE FIX: Uses aiofiles instead of sync open()
        """
        try:
            file_path = str(file_path)

            # Check cache first
            if await self._is_cached_and_fresh(file_path):
                logger.debug("📋 Using cached content for %s", file_path)
                return self.file_cache[file_path]["content"]

            # Read file asynchronously
            async with aiofiles.open(file_path, mode="r", encoding=encoding) as f:
                content = await f.read()

            # Cache the content
            self._cache_file_content(file_path, content)

            logger.debug("📖 Read %s chars from %s", len(content), file_path)
            return content

        except FileNotFoundError:
            logger.warning("📁 File not found: %s", file_path)
            return ""
        except OSError as e:
            logger.error("📖 Failed to read file %s: %s", file_path, e)
            return ""
        except Exception as e:
            logger.error("📖 Error reading %s: %s", file_path, e)
            return ""

    async def write_text_file(
        self,
        file_path: Union[str, Path],
        content: str,
        encoding: str = "utf-8",
        create_dirs: bool = True,
    ) -> bool:
        """
        Write text file asynchronously without blocking

        ROOT CAUSE FIX: Uses aiofiles instead of sync write operations
        """
        try:
            file_path = Path(file_path)

            # Create directories if needed
            if create_dirs and file_path.parent:
                await asyncio.to_thread(
                    file_path.parent.mkdir, parents=True, exist_ok=True
                )

            # Write file asynchronously
            async with aiofiles.open(file_path, mode="w", encoding=encoding) as f:
                await f.write(content)

            # Update cache
            self._cache_file_content(str(file_path), content)

            logger.debug("📝 Wrote %s chars to %s", len(content), file_path)
            return True

        except OSError as e:
            logger.error("📝 Failed to write to file %s: %s", file_path, e)
            return False
        except Exception as e:
            logger.error("📝 Error writing to %s: %s", file_path, e)
            return False

    async def read_json_file(self, file_path: Union[str, Path]) -> Dict[str, Any]:
        """
        Read JSON file asynchronously without blocking

        ROOT CAUSE FIX: Uses async file read + async JSON parsing
        """
        try:
            content = await self.read_text_file(file_path)
            if not content:
                return {}

            # Parse JSON in thread to avoid blocking
            json_data = await asyncio.to_thread(json.loads, content)

            logger.debug("📊 Loaded JSON from %s", file_path)
            return json_data

        except json.JSONDecodeError as e:
            logger.error("📊 JSON decode error in %s: %s", file_path, e)
            return {}
        except Exception as e:
            logger.error("📊 Error loading JSON from %s: %s", file_path, e)
            return {}

    async def write_json_file(
        self, file_path: Union[str, Path], data: Dict[str, Any], indent: int = 2
    ) -> bool:
        """
        Write JSON file asynchronously without blocking

        ROOT CAUSE FIX: Uses async JSON serialization + async file write
        """
        try:
            # Serialize JSON in thread to avoid blocking
            content = await asyncio.to_thread(
                json.dumps, data, indent=indent, ensure_ascii=False
            )

            # Write asynchronously
            result = await self.write_text_file(file_path, content)

            if result:
                logger.debug("📊 Saved JSON to %s", file_path)

            return result

        except Exception as e:
            logger.error("📊 Error saving JSON to %s: %s", file_path, e)
            return False

    async def file_exists(self, file_path: Union[str, Path]) -> bool:
        """
        Check if file exists asynchronously without blocking

        ROOT CAUSE FIX: Uses asyncio.to_thread for filesystem operations
        """
        try:
            return await asyncio.to_thread(os.path.exists, str(file_path))
        except Exception as e:
            logger.error("📁 Error checking file existence %s: %s", file_path, e)
            return False

    async def get_file_size(self, file_path: Union[str, Path]) -> int:
        """
        Get file size asynchronously without blocking

        ROOT CAUSE FIX: Uses asyncio.to_thread for stat operations
        """
        try:
            stat_result = await asyncio.to_thread(os.stat, str(file_path))
            return stat_result.st_size
        except Exception as e:
            logger.error("📏 Error getting file size %s: %s", file_path, e)
            return 0

    async def list_directory(
        self, dir_path: Union[str, Path], pattern: Optional[str] = None
    ) -> List[str]:
        """
        List directory contents asynchronously without blocking

        ROOT CAUSE FIX: Uses asyncio.to_thread for directory operations
        """
        try:
            dir_path = Path(dir_path)

            if pattern:
                # Use glob pattern
                # Issue #358 - use lambda for proper glob() execution in thread
                files = await asyncio.to_thread(lambda: list(dir_path.glob(pattern)))
                return [str(f) for f in files]
            else:
                # List all files
                # Issue #358 - use lambda for proper iterdir() execution in thread
                files = await asyncio.to_thread(lambda: list(dir_path.iterdir()))
                return [str(f) for f in files]

        except Exception as e:
            logger.error("📁 Error listing directory %s: %s", dir_path, e)
            return []

    async def create_temp_file(
        self, content: str, suffix: str = ".tmp", prefix: str = "autobot_"
    ) -> Optional[str]:
        """
        Create temporary file asynchronously without blocking

        ROOT CAUSE FIX: Uses asyncio.to_thread for temp file creation
        """
        try:
            # Create temp file in thread
            fd, temp_path = await asyncio.to_thread(
                tempfile.mkstemp, suffix=suffix, prefix=prefix
            )

            # Close file descriptor and write content asynchronously
            await asyncio.to_thread(os.close, fd)

            success = await self.write_text_file(temp_path, content)
            if success:
                logger.debug("🗂️ Created temp file: %s", temp_path)
                return temp_path
            else:
                await asyncio.to_thread(os.unlink, temp_path)
                return None

        except Exception as e:
            logger.error("🗂️ Error creating temp file: %s", e)
            return None

    async def copy_file(self, src: Union[str, Path], dst: Union[str, Path]) -> bool:
        """
        Copy file asynchronously without blocking

        ROOT CAUSE FIX: Uses async read/write operations
        """
        try:
            # Read source file
            content = await self.read_text_file(src)
            if not content:
                # Try binary mode for non-text files
                async with aiofiles.open(src, mode="rb") as src_file:
                    binary_content = await src_file.read()

                async with aiofiles.open(dst, mode="wb") as dst_file:
                    await dst_file.write(binary_content)
            else:
                # Write as text
                await self.write_text_file(dst, content)

            logger.debug("📋 Copied %s to %s", src, dst)
            return True

        except OSError as e:
            logger.error("📋 Failed to copy file %s to %s: %s", src, dst, e)
            return False
        except Exception as e:
            logger.error("📋 Error copying %s to %s: %s", src, dst, e)
            return False

    def _cache_file_content(self, file_path: str, content: str):
        """Cache file content with timestamp"""
        import time

        self.file_cache[file_path] = {"content": content, "timestamp": time.time()}

    async def _is_cached_and_fresh(self, file_path: str) -> bool:
        """Check if file is cached and still fresh"""
        if file_path not in self.file_cache:
            return False

        import time

        cache_age = time.time() - self.file_cache[file_path]["timestamp"]
        return cache_age < self.cache_ttl

    async def clear_cache(self):
        """Clear file cache"""
        self.file_cache.clear()
        logger.debug("🗑️ File cache cleared")


# Global instance for easy access (thread-safe)
import asyncio as _asyncio_lock

_async_file_ops = None
_async_file_ops_lock = _asyncio_lock.Lock()


async def get_async_file_operations() -> AsyncFileOperations:
    """Get global async file operations instance (thread-safe)"""
    global _async_file_ops
    if not _async_file_ops:
        async with _async_file_ops_lock:
            # Double-check after acquiring lock
            if not _async_file_ops:
                _async_file_ops = AsyncFileOperations()
    return _async_file_ops


# Convenience functions for common operations
async def read_file_async(file_path: Union[str, Path], encoding: str = "utf-8") -> str:
    """Read text file asynchronously - ROOT CAUSE FIX for sync file I/O"""
    ops = await get_async_file_operations()
    return await ops.read_text_file(file_path, encoding)


async def write_file_async(
    file_path: Union[str, Path], content: str, encoding: str = "utf-8"
) -> bool:
    """Write text file asynchronously - ROOT CAUSE FIX for sync file I/O"""
    ops = await get_async_file_operations()
    return await ops.write_text_file(file_path, content, encoding)


async def read_json_async(file_path: Union[str, Path]) -> Dict[str, Any]:
    """Read JSON file asynchronously - ROOT CAUSE FIX for sync file I/O"""
    ops = await get_async_file_operations()
    return await ops.read_json_file(file_path)


async def write_json_async(file_path: Union[str, Path], data: Dict[str, Any]) -> bool:
    """Write JSON file asynchronously - ROOT CAUSE FIX for sync file I/O"""
    ops = await get_async_file_operations()
    return await ops.write_json_file(file_path, data)


async def file_exists_async(file_path: Union[str, Path]) -> bool:
    """Check file existence asynchronously - ROOT CAUSE FIX for sync file I/O"""
    ops = await get_async_file_operations()
    return await ops.file_exists(file_path)


# Decorator to convert sync file operations to async
def make_async_file_operation(func):
    """
    Decorator to convert synchronous file operations to async

    ROOT CAUSE FIX: Converts blocking file I/O to non-blocking
    """

    @functools.wraps(func)
    async def async_wrapper(*args, **kwargs):
        """Execute wrapped sync function in thread pool for async compatibility."""
        return await asyncio.to_thread(func, *args, **kwargs)

    return async_wrapper
