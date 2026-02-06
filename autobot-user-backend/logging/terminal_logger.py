# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Terminal Command Logger with Redis Caching

Provides detailed logging of terminal commands with:
- AUTOBOT vs MANUAL command tracking
- File-based persistence
- Redis caching for fast access
- Integration with chat message markers
"""

import asyncio
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, FrozenSet, List, Optional

import aiofiles

# Issue #765: Use centralized strip_ansi_codes from encoding_utils
from src.utils.encoding_utils import strip_ansi_codes

logger = logging.getLogger(__name__)

# Issue #380: Module-level frozenset for command statuses requiring command display
_COMMAND_DISPLAY_STATUSES: FrozenSet[str] = frozenset(
    {"EXECUTING", "PENDING_APPROVAL", "SUCCESS", "ERROR"}
)

# Issue #380: Module-level frozensets for status matching (case-insensitive)
_SUCCESS_STATUSES: FrozenSet[str] = frozenset({"success", "SUCCESS"})
_ERROR_STATUSES: FrozenSet[str] = frozenset({"error", "ERROR"})


class TerminalLogger:
    """
    Manages terminal command logging with AUTOBOT/MANUAL markers
    and Redis caching for historical processing.
    """

    def __init__(self, redis_client=None, data_dir: str = "data/chats"):
        """
        Initialize terminal logger.

        Args:
            redis_client: Redis client for caching
            data_dir: Base directory for log files
        """
        self.redis_client = redis_client
        self.data_dir = Path(data_dir)
        self.cache_ttl = 3600  # 1 hour cache
        self.max_cached_commands = 100  # Keep last 100 commands in Redis

        # Ensure data directory exists
        self.data_dir.mkdir(parents=True, exist_ok=True)

        logger.info(
            f"TerminalLogger initialized - data_dir: {self.data_dir}, "
            f"redis_enabled: {redis_client is not None}"
        )

    async def _ensure_chat_json_exists(self, session_id: str):
        """
        CRITICAL: Ensure chat.json exists before creating terminal.log.

        Terminal logs cannot exist without corresponding chat.json files
        because the frontend loads sessions by scanning for *_chat.json files.
        Without chat.json, the session is invisible in the UI.

        Args:
            session_id: Chat session ID
        """
        import json

        chat_file = self.data_dir / f"{session_id}_chat.json"

        # Only create if it doesn't exist
        # Issue #358 - avoid blocking
        if not await asyncio.to_thread(chat_file.exists):
            current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            chat_data = {
                "chatId": session_id,
                "name": "",
                "messages": [],
                "created_time": current_time,
                "last_modified": current_time,
            }

            try:
                async with aiofiles.open(chat_file, "w", encoding="utf-8") as f:
                    await f.write(json.dumps(chat_data, indent=2))
                logger.info("✅ Created chat.json for terminal session: %s", session_id)
            except OSError as e:
                logger.error(f"❌ Failed to write chat.json file {chat_file}: {e}")
                raise
            except Exception as e:
                logger.error(
                    f"❌ Failed to create chat.json for session {session_id}: {e}"
                )
                raise

    def _create_log_entry(
        self,
        command: str,
        run_type: str,
        status: str,
        result: Optional[Dict[str, Any]],
        user_id: Optional[str],
    ) -> Dict[str, Any]:
        """Create a structured log entry dictionary. Issue #620."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        log_entry = {
            "timestamp": timestamp,
            "run_type": run_type.upper(),
            "command": command,
            "status": status,
            "user_id": user_id,
        }
        if result:
            log_entry["result"] = result
        return log_entry

    async def _write_log_to_file(self, session_id: str, log_line: str) -> None:
        """Write a formatted log line to the session terminal log file. Issue #620."""
        log_file = self.data_dir / f"{session_id}_terminal.log"
        try:
            async with aiofiles.open(log_file, "a", encoding="utf-8") as f:
                await f.write(log_line + "\n")
        except OSError as e:
            logger.error("Failed to write to terminal log file %s: %s", log_file, e)
        except Exception as e:
            logger.error("Failed to log command to %s: %s", log_file, e)

    async def log_command(
        self,
        session_id: str,
        command: str,
        run_type: str,
        status: str = "executing",
        result: Optional[Dict[str, Any]] = None,
        user_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Log a terminal command execution. Issue #620."""
        # Ensure chat.json exists BEFORE creating/appending to terminal.log
        await self._ensure_chat_json_exists(session_id)

        log_entry = self._create_log_entry(command, run_type, status, result, user_id)
        log_line = self._format_log_line(log_entry)
        await self._write_log_to_file(session_id, log_line)

        if self.redis_client:
            await self._cache_command(session_id, log_entry)

        logger.debug(
            f"Logged {run_type} command for session {session_id}: {command[:50]}..."
        )
        return log_entry

    @staticmethod
    def _strip_ansi_codes(text: str) -> str:
        """Remove ANSI escape codes from text.

        Issue #765: Delegates to centralized strip_ansi_codes function.
        """
        if not text:
            return text
        return strip_ansi_codes(text)

    def _format_log_line(self, entry: Dict[str, Any]) -> str:
        """Format log entry as a readable log line (with ANSI codes stripped)."""
        timestamp = entry["timestamp"]
        run_type = entry["run_type"]
        command = self._strip_ansi_codes(entry["command"])
        status = entry["status"].upper()

        # Base log line
        line = f"[{timestamp}] [{run_type}] STATUS: {status}"

        # Add command if not just status update
        if status in _COMMAND_DISPLAY_STATUSES:
            line += f" | COMMAND: {command}"

        # Add user info if available
        if entry.get("user_id"):
            line += f" | USER: {entry['user_id']}"

        # Add result info
        if entry.get("result"):
            result = entry["result"]
            if result.get("return_code") is not None:
                line += f" | EXIT_CODE: {result['return_code']}"

            # Add truncated output (stripped of ANSI codes)
            if result.get("stdout"):
                stdout = self._strip_ansi_codes(result["stdout"])[:200].replace(
                    "\n", " "
                )
                line += f" | OUTPUT: {stdout}..."

            if result.get("stderr"):
                stderr = self._strip_ansi_codes(result["stderr"])[:200].replace(
                    "\n", " "
                )
                line += f" | ERROR: {stderr}..."

        return line

    async def _cache_command(self, session_id: str, entry: Dict[str, Any]):
        """Cache command in Redis for fast access."""
        try:
            import json

            cache_key = f"chat:session:{session_id}:terminal"

            # Add to list (newest first)
            await self.redis_client.lpush(cache_key, json.dumps(entry))

            # Trim to max cached commands
            await self.redis_client.ltrim(cache_key, 0, self.max_cached_commands - 1)

            # Set expiry
            await self.redis_client.expire(cache_key, self.cache_ttl)

            # Issue #379: Update active terminal sessions set in parallel
            await asyncio.gather(
                self.redis_client.sadd("chat:terminal:active", session_id),
                self.redis_client.expire("chat:terminal:active", self.cache_ttl),
            )

        except Exception as e:
            logger.error("Failed to cache command in Redis: %s", e)

    async def get_recent_commands(
        self, session_id: str, limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Get recent commands for a session.

        Args:
            session_id: Chat session ID
            limit: Maximum number of commands to return

        Returns:
            List of command log entries
        """
        # Try Redis cache first
        if self.redis_client:
            try:
                import json

                cache_key = f"chat:session:{session_id}:terminal"
                cached_commands = await self.redis_client.lrange(
                    cache_key, 0, limit - 1
                )

                if cached_commands:
                    logger.debug(
                        f"Cache HIT for terminal commands: session {session_id}"
                    )
                    return [json.loads(cmd) for cmd in cached_commands]

            except Exception as e:
                logger.error("Failed to read from Redis cache: %s", e)

        # Cache miss - read from file
        logger.debug("Cache MISS for terminal commands: session %s", session_id)
        return await self._read_from_file(session_id, limit)

    async def _read_from_file(
        self, session_id: str, limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Read recent commands from log file."""
        log_file = self.data_dir / f"{session_id}_terminal.log"

        # Issue #358 - avoid blocking
        if not await asyncio.to_thread(log_file.exists):
            return []

        try:
            async with aiofiles.open(log_file, "r", encoding="utf-8") as f:
                lines = await f.readlines()

            # Parse last N lines
            commands = []
            for line in reversed(lines[-limit:]):
                entry = self._parse_log_line(line.strip())
                if entry:
                    commands.append(entry)

            # Warm up Redis cache if available
            if self.redis_client and commands:
                await self._warm_cache(session_id, commands)

            return commands

        except OSError as e:
            logger.error("Failed to read terminal log file %s: %s", log_file, e)
            return []
        except Exception as e:
            logger.error("Failed to parse terminal log %s: %s", log_file, e)
            return []

    def _parse_log_line(self, line: str) -> Optional[Dict[str, Any]]:
        """Parse a log line back into structured data."""
        try:
            # Simple parsing - extract key components
            if not line or not line.startswith("["):
                return None

            parts = line.split("] ")
            if len(parts) < 3:
                return None

            timestamp = parts[0][1:]  # Remove leading [
            run_type = parts[1][1:]  # Remove leading [

            # Extract status and other fields
            remainder = " ".join(parts[2:])
            entry = {
                "timestamp": timestamp,
                "run_type": run_type,
            }

            # Parse STATUS
            if "STATUS:" in remainder:
                status_part = remainder.split("STATUS:")[1].split("|")[0].strip()
                entry["status"] = status_part.lower()

            # Parse COMMAND
            if "COMMAND:" in remainder:
                command_part = remainder.split("COMMAND:")[1].split("|")[0].strip()
                entry["command"] = command_part

            # Parse USER
            if "USER:" in remainder:
                user_part = remainder.split("USER:")[1].split("|")[0].strip()
                entry["user_id"] = user_part

            return entry

        except Exception as e:
            logger.error("Failed to parse log line: %s", e)
            return None

    async def _warm_cache(self, session_id: str, commands: List[Dict[str, Any]]):
        """Warm up Redis cache with file data."""
        try:
            import json

            cache_key = f"chat:session:{session_id}:terminal"

            # Clear existing cache
            await self.redis_client.delete(cache_key)

            # Add commands (in reverse order to maintain chronological order)
            for command in reversed(commands):
                await self.redis_client.rpush(cache_key, json.dumps(command))

            # Set expiry
            await self.redis_client.expire(cache_key, self.cache_ttl)

            logger.debug(
                f"Warmed cache for session {session_id}: {len(commands)} commands"
            )

        except Exception as e:
            logger.error("Failed to warm cache: %s", e)

    async def get_session_statistics(self, session_id: str) -> Dict[str, Any]:
        """
        Get statistics for a terminal session.

        Args:
            session_id: Chat session ID

        Returns:
            Statistics dictionary
        """
        commands = await self.get_recent_commands(session_id, limit=1000)

        autobot_count = sum(1 for cmd in commands if cmd.get("run_type") == "AUTOBOT")
        manual_count = sum(1 for cmd in commands if cmd.get("run_type") == "MANUAL")

        success_count = sum(
            1 for cmd in commands if cmd.get("status") in _SUCCESS_STATUSES
        )
        error_count = sum(1 for cmd in commands if cmd.get("status") in _ERROR_STATUSES)

        return {
            "total_commands": len(commands),
            "autobot_commands": autobot_count,
            "manual_commands": manual_count,
            "successful": success_count,
            "errors": error_count,
            "log_file": f"{session_id}_terminal.log",
        }

    async def clear_session_logs(self, session_id: str) -> bool:
        """
        Clear terminal logs for a session.

        Args:
            session_id: Chat session ID

        Returns:
            True if cleared successfully
        """
        try:
            # Delete file
            log_file = self.data_dir / f"{session_id}_terminal.log"
            # Issue #358 - avoid blocking
            if await asyncio.to_thread(log_file.exists):
                await asyncio.to_thread(log_file.unlink)

            # Issue #379: Clear Redis cache in parallel
            if self.redis_client:
                cache_key = f"chat:session:{session_id}:terminal"
                await asyncio.gather(
                    self.redis_client.delete(cache_key),
                    self.redis_client.srem("chat:terminal:active", session_id),
                )

            logger.info("Cleared terminal logs for session %s", session_id)
            return True

        except Exception as e:
            logger.error(
                "Failed to clear terminal logs for session %s: %s", session_id, e
            )
            return False
