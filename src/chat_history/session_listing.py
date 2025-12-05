# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Chat History Session Listing Mixin - Session listing operations.

Provides session listing functionality:
- Full session listing with metadata
- Fast session listing using file metadata only
- Orphaned terminal file detection and recovery
"""

import asyncio
import json
import logging
import os
from datetime import datetime
from typing import Any, Dict, List

import aiofiles

logger = logging.getLogger(__name__)


class SessionListingMixin:
    """
    Mixin providing session listing operations for chat history.

    Requires base class to have:
    - self._get_chats_directory(): method
    - self._decrypt_data(): method
    - self._cleanup_old_session_files(): method
    """

    async def list_sessions(self) -> List[Dict[str, Any]]:
        """List available chat sessions with their metadata."""
        try:
            sessions = []
            chats_directory = self._get_chats_directory()

            # Ensure chats directory exists
            dir_exists = await asyncio.to_thread(os.path.exists, chats_directory)
            if not dir_exists:
                await asyncio.to_thread(os.makedirs, chats_directory, exist_ok=True)
                return sessions

            # Clean up old session files if needed
            await self._cleanup_old_session_files()

            # Look for chat files in the chats directory (both old and new formats)
            filenames = await asyncio.to_thread(os.listdir, chats_directory)
            for filename in filenames:
                # Support both formats: chat_{uuid}.json and {uuid}_chat.json
                chat_id = None
                if filename.startswith("chat_") and filename.endswith(".json"):
                    # Old format: chat_{uuid}.json
                    chat_id = filename.replace("chat_", "").replace(".json", "")
                elif filename.endswith("_chat.json"):
                    # New format: {uuid}_chat.json
                    chat_id = filename.replace("_chat.json", "")

                if not chat_id:
                    continue

                chat_path = os.path.join(chats_directory, filename)

                try:
                    async with aiofiles.open(chat_path, "r", encoding="utf-8") as f:
                        file_content = await f.read()
                        chat_data = self._decrypt_data(file_content)

                        # Get chat metadata
                        chat_name = chat_data.get("name", "")
                        chat_messages = chat_data.get("messages", [])
                        created_time = chat_data.get("created_time", "")
                        last_modified = chat_data.get("last_modified", "")

                        sessions.append(
                            {
                                "chatId": chat_id,
                                "name": chat_name,
                                "messageCount": len(chat_messages),
                                "createdTime": created_time,
                                "lastModified": last_modified,
                            }
                        )
                except Exception as e:
                    logger.error(f"Error reading chat file {filename}: {str(e)}")
                    continue

            # Sort by last modified time (most recent first)
            sessions.sort(key=lambda x: x.get("lastModified", ""), reverse=True)
            return sessions

        except Exception as e:
            logger.error(f"Error listing chat sessions: {str(e)}")
            return []

    async def list_sessions_fast(self) -> List[Dict[str, Any]]:
        """Fast listing of chat sessions using file metadata only (no decryption)."""
        try:
            sessions = []
            chats_directory = self._get_chats_directory()

            # Ensure chats directory exists
            dir_exists = await asyncio.to_thread(os.path.exists, chats_directory)
            if not dir_exists:
                await asyncio.to_thread(os.makedirs, chats_directory, exist_ok=True)
                return sessions

            # Use file system metadata for performance - avoid decryption
            filenames = await asyncio.to_thread(os.listdir, chats_directory)
            for filename in filenames:
                chat_id = None
                if filename.startswith("chat_") and filename.endswith(".json"):
                    # Old format: chat_{uuid}.json
                    chat_id = filename.replace("chat_", "").replace(".json", "")
                elif filename.endswith("_chat.json"):
                    # New format: {uuid}_chat.json
                    chat_id = filename.replace("_chat.json", "")

                if not chat_id:
                    continue

                chat_path = os.path.join(chats_directory, filename)

                try:
                    # Get file stats for metadata
                    stat = await asyncio.to_thread(os.stat, chat_path)
                    created_time = datetime.fromtimestamp(stat.st_ctime).isoformat()
                    last_modified = datetime.fromtimestamp(stat.st_mtime).isoformat()
                    file_size = stat.st_size

                    # Read chat name and message count from file (lightweight)
                    chat_name = None
                    message_count = 0
                    try:
                        async with aiofiles.open(chat_path, "r", encoding="utf-8") as f:
                            content = await f.read()
                            chat_data = json.loads(content)
                            chat_name = chat_data.get("name", "").strip()
                            messages = chat_data.get("messages", [])
                            message_count = len(messages) if isinstance(messages, list) else 0
                    except Exception as read_err:
                        logger.debug(
                            f"Could not read chat file content for {filename}: {read_err}"
                        )

                    # Create unique chat names using timestamp or full UUID
                    if not chat_name:
                        if chat_id.startswith("chat-") and len(chat_id) > 15:
                            unique_part = chat_id[-8:]
                            chat_name = f"Chat {unique_part}"
                        elif len(chat_id) >= 8:
                            chat_name = f"Chat {chat_id[:8]}"
                        else:
                            chat_name = f"Chat {chat_id}"

                    sessions.append(
                        {
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
                    )
                except Exception as e:
                    logger.error(f"Error reading file stats for {filename}: {str(e)}")
                    continue

            # Detect orphaned terminal files and auto-create chat sessions
            existing_chat_ids = {session["id"] for session in sessions}
            sessions = await self._recover_orphaned_terminal_sessions(
                chats_directory, existing_chat_ids, sessions
            )

            # Sort by last modified time (most recent first)
            sessions.sort(key=lambda x: x.get("lastModified", ""), reverse=True)
            return sessions

        except Exception as e:
            logger.error(f"Error listing chat sessions (fast mode): {str(e)}")
            return []

    async def _recover_orphaned_terminal_sessions(
        self,
        chats_directory: str,
        existing_chat_ids: set,
        sessions: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """
        Detect and recover orphaned terminal files by creating chat sessions.

        Args:
            chats_directory: Path to chats directory
            existing_chat_ids: Set of existing chat IDs
            sessions: Current list of sessions

        Returns:
            Updated sessions list with recovered sessions
        """
        orphaned_sessions_created = 0

        try:
            orphan_filenames = await asyncio.to_thread(os.listdir, chats_directory)
            for filename in orphan_filenames:
                session_id = None

                # Check for terminal log files
                if filename.endswith("_terminal.log"):
                    session_id = filename.replace("_terminal.log", "")
                # Check for terminal transcript files
                elif filename.endswith("_terminal_transcript.txt"):
                    session_id = filename.replace("_terminal_transcript.txt", "")

                # If we found a terminal file and no corresponding chat exists
                if session_id and session_id not in existing_chat_ids:
                    try:
                        # Create minimal empty chat.json for this orphaned terminal session
                        chat_file = os.path.join(
                            chats_directory, f"{session_id}_chat.json"
                        )

                        # Only create if it doesn't already exist
                        chat_file_exists = await asyncio.to_thread(
                            os.path.exists, chat_file
                        )
                        if not chat_file_exists:
                            empty_chat = {
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

                            async with aiofiles.open(
                                chat_file, "w", encoding="utf-8"
                            ) as f:
                                await f.write(
                                    json.dumps(empty_chat, indent=2, ensure_ascii=False)
                                )

                            # Add to existing_chat_ids to prevent duplicates
                            existing_chat_ids.add(session_id)
                            orphaned_sessions_created += 1

                            # Get file stats for the newly created chat
                            stat = await asyncio.to_thread(os.stat, chat_file)
                            created_time = datetime.fromtimestamp(
                                stat.st_ctime
                            ).isoformat()
                            last_modified = datetime.fromtimestamp(
                                stat.st_mtime
                            ).isoformat()

                            # Add to sessions list
                            sessions.append(
                                {
                                    "id": session_id,
                                    "chatId": session_id,
                                    "title": f"Terminal Session {session_id[:8]}",
                                    "name": f"Terminal Session {session_id[:8]}",
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
                            )

                            logger.info(
                                f"Auto-created chat session for orphaned terminal "
                                f"file: {session_id} (from {filename})"
                            )

                    except Exception as create_err:
                        logger.error(
                            f"Failed to auto-create chat session for orphaned "
                            f"{filename}: {create_err}"
                        )
                        continue

            if orphaned_sessions_created > 0:
                logger.info(
                    f"✅ Auto-created {orphaned_sessions_created} chat sessions "
                    f"for orphaned terminal files"
                )

        except Exception as e:
            logger.error(f"Error recovering orphaned terminal sessions: {e}")

        return sessions
