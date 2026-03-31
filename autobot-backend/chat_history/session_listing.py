# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Chat History Session Listing Mixin - Session listing operations.

Provides session listing functionality:
- Full session listing with metadata
- Fast session listing using file metadata only
- Orphaned terminal file detection and recovery

Issue #718: Uses dedicated thread pool for file I/O to prevent blocking
when the main asyncio thread pool is saturated by indexing operations.
"""

import json
import logging
import os
from datetime import datetime
from typing import Any, Dict, List

import aiofiles

from chat_history.file_io import run_in_chat_io_executor

logger = logging.getLogger(__name__)


def _extract_chat_id_from_filename(filename: str) -> str | None:
    """Extract chat ID from filename (Issue #315: extracted).

    Args:
        filename: Chat filename to parse

    Returns:
        Chat ID string or None if not a valid chat file
    """
    if filename.startswith("chat_") and filename.endswith(".json"):
        return filename.replace("chat_", "").replace(".json", "")
    if filename.endswith("_chat.json"):
        return filename.replace("_chat.json", "")
    return None


def _generate_chat_name(chat_id: str) -> str:
    """Generate a display name for a chat (Issue #315: extracted).

    Args:
        chat_id: The chat's unique identifier

    Returns:
        Human-readable chat name
    """
    if chat_id.startswith("chat-") and len(chat_id) > 15:
        return f"Chat {chat_id[-8:]}"
    if len(chat_id) >= 8:
        return f"Chat {chat_id[:8]}"
    return f"Chat {chat_id}"


class SessionListingMixin:
    """
    Mixin providing session listing operations for chat history.

    Requires base class to have:
    - self._get_chats_directory(): method
    - self._decrypt_data(): method
    - self._cleanup_old_session_files(): method
    """

    async def _ensure_chats_directory_exists(self, chats_directory: str) -> bool:
        """Ensure chats directory exists, creating if necessary. Issue #620.

        Args:
            chats_directory: Path to the chats directory

        Returns:
            True if directory existed or was created, False if newly created
        """
        dir_exists = await run_in_chat_io_executor(os.path.exists, chats_directory)
        if not dir_exists:
            await run_in_chat_io_executor(os.makedirs, chats_directory, exist_ok=True)
            return False
        return True

    async def _process_chat_file_for_listing(
        self, chat_path: str, chat_id: str, filename: str
    ) -> Dict[str, Any] | None:
        """Process a single chat file and extract session metadata. Issue #620.

        Args:
            chat_path: Full path to the chat file
            chat_id: The chat identifier
            filename: Filename for error logging

        Returns:
            Session dict or None on error
        """
        try:
            async with aiofiles.open(chat_path, "r", encoding="utf-8") as f:
                file_content = await f.read()
                chat_data = self._decrypt_data(file_content)

                return {
                    "chatId": chat_id,
                    "name": chat_data.get("name", ""),
                    "messageCount": len(chat_data.get("messages", [])),
                    "createdTime": chat_data.get("created_time", ""),
                    "lastModified": chat_data.get("last_modified", ""),
                }
        except Exception as e:
            logger.error("Error reading chat file %s: %s", filename, str(e))
            return None

    async def list_sessions(self) -> List[Dict[str, Any]]:
        """List available chat sessions with their metadata."""
        try:
            sessions = []
            chats_directory = self._get_chats_directory()

            if not await self._ensure_chats_directory_exists(chats_directory):
                return sessions

            await self._cleanup_old_session_files()

            filenames = await run_in_chat_io_executor(os.listdir, chats_directory)
            for filename in filenames:
                chat_id = _extract_chat_id_from_filename(filename)
                if not chat_id:
                    continue

                chat_path = os.path.join(chats_directory, filename)
                session = await self._process_chat_file_for_listing(
                    chat_path, chat_id, filename
                )
                if session:
                    sessions.append(session)

            sessions.sort(key=lambda x: x.get("lastModified", ""), reverse=True)
            return sessions

        except Exception as e:
            logger.error("Error listing chat sessions: %s", str(e))
            return []

    async def _read_chat_file_metadata(self, chat_path: str) -> tuple[str | None, int]:
        """Read chat name and message count from file (Issue #315: extracted).

        Args:
            chat_path: Path to chat JSON file

        Returns:
            Tuple of (chat_name or None, message_count)
        """
        try:
            async with aiofiles.open(chat_path, "r", encoding="utf-8") as f:
                content = await f.read()
                chat_data = json.loads(content)
                chat_name = chat_data.get("name", "").strip() or None
                messages = chat_data.get("messages", [])
                message_count = len(messages) if isinstance(messages, list) else 0
                return chat_name, message_count
        except Exception as read_err:
            logger.debug("Could not read chat file content: %s", read_err)
            return None, 0

    async def _build_session_entry(
        self, chat_id: str, chat_path: str, filename: str
    ) -> Dict[str, Any] | None:
        """Build a session entry from file metadata (Issue #315: extracted).

        Args:
            chat_id: Chat identifier
            chat_path: Full path to chat file
            filename: Filename for error logging

        Returns:
            Session dict or None on error
        """
        try:
            stat = await run_in_chat_io_executor(os.stat, chat_path)
            created_time = datetime.fromtimestamp(stat.st_ctime).isoformat()
            last_modified = datetime.fromtimestamp(stat.st_mtime).isoformat()
            file_size = stat.st_size

            chat_name, message_count = await self._read_chat_file_metadata(chat_path)
            if not chat_name:
                chat_name = _generate_chat_name(chat_id)

            return {
                "id": chat_id,
                "chatId": chat_id,
                "title": chat_name,
                "name": chat_name,
                "messages": [],
                "messageCount": message_count,
                "createdAt": created_time,
                "createdTime": created_time,
                "updatedAt": last_modified,
                "lastModified": last_modified,
                "isActive": False,
                "fileSize": file_size,
                "fast_mode": True,
            }
        except Exception as e:
            logger.error("Error reading file stats for %s: %s", filename, str(e))
            return None

    async def list_sessions_fast(self) -> List[Dict[str, Any]]:
        """Fast listing of chat sessions using file metadata only (no decryption).

        Issue #315: Refactored to use helper methods for reduced nesting.
        """
        try:
            sessions = []
            chats_directory = self._get_chats_directory()

            # Ensure chats directory exists
            dir_exists = await run_in_chat_io_executor(os.path.exists, chats_directory)
            if not dir_exists:
                await run_in_chat_io_executor(
                    os.makedirs, chats_directory, exist_ok=True
                )
                return sessions

            # Process each chat file
            filenames = await run_in_chat_io_executor(os.listdir, chats_directory)
            for filename in filenames:
                chat_id = _extract_chat_id_from_filename(filename)
                if not chat_id:
                    continue

                chat_path = os.path.join(chats_directory, filename)
                session = await self._build_session_entry(chat_id, chat_path, filename)
                if session:
                    sessions.append(session)

            # Detect orphaned terminal files and auto-create chat sessions
            existing_chat_ids = {session["id"] for session in sessions}
            sessions = await self._recover_orphaned_terminal_sessions(
                chats_directory, existing_chat_ids, sessions
            )

            # Sort by last modified time (most recent first)
            sessions.sort(key=lambda x: x.get("lastModified", ""), reverse=True)
            return sessions

        except Exception as e:
            logger.error("Error listing chat sessions (fast mode): %s", str(e))
            return []

    def _extract_session_id_from_terminal_file(self, filename: str) -> str | None:
        """Extract session ID from terminal file (Issue #315: extracted).

        Args:
            filename: Terminal filename to parse

        Returns:
            Session ID or None if not a terminal file
        """
        if filename.endswith("_terminal.log"):
            return filename.replace("_terminal.log", "")
        if filename.endswith("_terminal_transcript.txt"):
            return filename.replace("_terminal_transcript.txt", "")
        return None

    def _build_empty_chat_data(self, session_id: str, filename: str) -> Dict[str, Any]:
        """Build empty chat data structure for orphaned terminal. Issue #620.

        Args:
            session_id: Session identifier
            filename: Source terminal filename

        Returns:
            Empty chat data dictionary
        """
        return {
            "id": session_id,
            "name": f"Terminal Session {session_id[:8]}",
            "messages": [],
            "created_at": datetime.now().isoformat(),
            "metadata": {
                "auto_created": True,
                "reason": "orphaned_terminal_files",
                "source": f"Found {filename}",
            },
        }

    def _build_orphaned_session_dict(
        self, session_id: str, stat: os.stat_result
    ) -> Dict[str, Any]:
        """Build session dictionary from stat result for orphaned session. Issue #620.

        Args:
            session_id: Session identifier
            stat: File stat result

        Returns:
            Session dictionary with all metadata
        """
        created_time = datetime.fromtimestamp(stat.st_ctime).isoformat()
        last_modified = datetime.fromtimestamp(stat.st_mtime).isoformat()
        session_name = f"Terminal Session {session_id[:8]}"

        return {
            "id": session_id,
            "chatId": session_id,
            "title": session_name,
            "name": session_name,
            "messages": [],
            "messageCount": 0,
            "createdAt": created_time,
            "createdTime": created_time,
            "updatedAt": last_modified,
            "lastModified": last_modified,
            "isActive": False,
            "fileSize": stat.st_size,
            "fast_mode": True,
            "auto_created": True,
        }

    async def _create_orphaned_session(
        self, session_id: str, filename: str, chats_directory: str
    ) -> Dict[str, Any] | None:
        """Create a chat session for orphaned terminal file (Issue #315: extracted).

        Args:
            session_id: Session identifier
            filename: Source terminal filename
            chats_directory: Path to chats directory

        Returns:
            Session dict or None on error
        """
        chat_file = os.path.join(chats_directory, f"{session_id}_chat.json")

        chat_file_exists = await run_in_chat_io_executor(os.path.exists, chat_file)
        if chat_file_exists:
            return None

        empty_chat = self._build_empty_chat_data(session_id, filename)
        async with aiofiles.open(chat_file, "w", encoding="utf-8") as f:
            await f.write(json.dumps(empty_chat, indent=2, ensure_ascii=False))

        stat = await run_in_chat_io_executor(os.stat, chat_file)
        logger.info(
            "Auto-created chat session for orphaned terminal file: %s (from %s)",
            session_id,
            filename,
        )

        return self._build_orphaned_session_dict(session_id, stat)

    async def _recover_orphaned_terminal_sessions(
        self,
        chats_directory: str,
        existing_chat_ids: set,
        sessions: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Detect and recover orphaned terminal files by creating chat sessions.

        Issue #315: Refactored to use helper methods for reduced nesting.
        """
        orphaned_sessions_created = 0

        try:
            orphan_filenames = await run_in_chat_io_executor(
                os.listdir, chats_directory
            )

            for filename in orphan_filenames:
                session_id = self._extract_session_id_from_terminal_file(filename)
                if not session_id or session_id in existing_chat_ids:
                    continue

                try:
                    session = await self._create_orphaned_session(
                        session_id, filename, chats_directory
                    )
                    if session:
                        existing_chat_ids.add(session_id)
                        sessions.append(session)
                        orphaned_sessions_created += 1
                except Exception as create_err:
                    logger.error(
                        "Failed to auto-create chat session for orphaned %s: %s",
                        filename,
                        create_err,
                    )

            if orphaned_sessions_created > 0:
                logger.info(
                    "✅ Auto-created %s chat sessions for orphaned terminal files",
                    orphaned_sessions_created,
                )

        except Exception as e:
            logger.error("Error recovering orphaned terminal sessions: %s", e)

        return sessions
