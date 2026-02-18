# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Conversation history management for chat workflow.

Handles Redis-backed conversation persistence, file-based transcripts,
and conversation history loading/saving with deduplication.
"""

import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List

import aiofiles

from .models import WorkflowSession

logger = logging.getLogger(__name__)


class ConversationHandlerMixin:
    """Mixin for conversation history management."""

    def _get_conversation_key(self, session_id: str) -> str:
        """Generate Redis key for conversation history."""
        return f"chat:conversation:{session_id}"

    async def _try_redis_history(self, session_id: str) -> List[Dict[str, str]] | None:
        """Try to load conversation history from Redis (Issue #332 - extracted helper).

        Returns:
            History list if found, None if not found or error
        """
        if self.redis_client is None:
            return None

        key = self._get_conversation_key(session_id)
        try:
            history_json = await asyncio.wait_for(
                self.redis_client.get(key), timeout=2.0
            )
            if history_json:
                logger.debug(
                    "Loaded conversation history from Redis for session %s", session_id
                )
                return json.loads(history_json)
        except asyncio.TimeoutError:
            logger.warning(
                "Redis get timeout after 2s for session %s, falling back to file",
                session_id,
            )
        return None

    async def _load_conversation_history(self, session_id: str) -> List[Dict[str, str]]:
        """Load conversation history from Redis (short-term) or file (long-term)."""
        try:
            # Try Redis first (fast access for recent conversations)
            redis_history = await self._try_redis_history(session_id)
            if redis_history is not None:
                return redis_history

            # Fall back to file-based transcript (long-term storage)
            history = await self._load_transcript(session_id)
            if not history:
                return history

            logger.debug(
                "Loaded conversation history from file for session %s", session_id
            )
            # Repopulate Redis cache (non-blocking, fire-and-forget)
            if self.redis_client is not None:
                asyncio.create_task(
                    self._save_conversation_history(session_id, history)
                )

            return history

        except Exception as e:
            logger.error("Failed to load conversation history: %s", e)
            return []

    async def _save_conversation_history(
        self, session_id: str, history: List[Dict[str, str]]
    ):
        """Save conversation history to Redis with TTL."""
        try:
            if self.redis_client is None:
                return

            key = self._get_conversation_key(session_id)
            history_json = json.dumps(history)

            # Save with 24-hour expiration and 2s timeout
            try:
                await asyncio.wait_for(
                    self.redis_client.set(
                        key, history_json, ex=self.conversation_history_ttl
                    ),
                    timeout=2.0,
                )
                logger.debug(
                    "Saved conversation history for session %s to Redis", session_id
                )
            except asyncio.TimeoutError:
                logger.warning(
                    "Redis set timeout after 2s for session %s - data may not be cached",
                    session_id,
                )

        except Exception as e:
            logger.error("Failed to save conversation history to Redis: %s", e)

    def _get_transcript_path(self, session_id: str) -> Path:
        """Get file path for conversation transcript."""
        return Path(self.transcript_dir) / f"{session_id}.json"

    def _create_empty_transcript(self, session_id: str) -> Dict:
        """Create an empty transcript structure (Issue #332 - extracted helper)."""
        return {
            "session_id": session_id,
            "created_at": datetime.now().isoformat(),
            "messages": [],
        }

    async def _load_existing_transcript(
        self, transcript_path: Path, session_id: str
    ) -> Dict:
        """Load existing transcript or create new on error (Issue #332 - extracted helper)."""
        try:
            async with aiofiles.open(transcript_path, "r", encoding="utf-8") as f:
                content = await asyncio.wait_for(f.read(), timeout=5.0)
                return json.loads(content)
        except asyncio.TimeoutError:
            logger.warning(
                f"File read timeout after 5s for {transcript_path}, creating new transcript"
            )
        except OSError as os_err:
            logger.warning(
                f"Failed to read transcript file {transcript_path}: {os_err}, "
                f"creating new transcript"
            )
        except json.JSONDecodeError as json_err:
            logger.warning(
                f"Corrupted transcript file {transcript_path}: {json_err}, "
                f"creating fresh transcript"
            )
            await self._backup_corrupted_file(transcript_path)

        return self._create_empty_transcript(session_id)

    async def _backup_corrupted_file(self, transcript_path: Path) -> None:
        """Backup corrupted transcript file (Issue #332 - extracted helper)."""
        backup_path = transcript_path.with_suffix(".json.corrupted")
        try:
            await asyncio.to_thread(transcript_path.rename, backup_path)
            logger.info("Backed up corrupted file to %s", backup_path)
        except Exception as backup_err:
            logger.warning("Could not backup corrupted file: %s", backup_err)

    async def _write_transcript_atomic(
        self, transcript_path: Path, transcript: Dict, session_id: str
    ) -> None:
        """Write transcript atomically via temp file (Issue #332 - extracted helper)."""
        temp_path = transcript_path.with_suffix(".tmp")
        try:
            async with aiofiles.open(temp_path, "w", encoding="utf-8") as f:
                await asyncio.wait_for(
                    f.write(json.dumps(transcript, indent=2, ensure_ascii=False)),
                    timeout=5.0,
                )
            await asyncio.to_thread(temp_path.rename, transcript_path)
            logger.debug(
                f"Appended to transcript for session {session_id} "
                f"({transcript['message_count']} total messages)"
            )
        except asyncio.TimeoutError:
            logger.warning("File write timeout after 5s for %s", transcript_path)
            # Issue #358 - avoid blocking
            if await asyncio.to_thread(temp_path.exists):
                await asyncio.to_thread(temp_path.unlink)
        except OSError as os_err:
            logger.error(
                "Failed to write transcript file %s: %s", transcript_path, os_err
            )

    async def _append_to_transcript(
        self, session_id: str, user_message: str, assistant_message: str
    ):
        """Append message exchange to long-term transcript file (async with aiofiles)."""
        try:
            # Ensure transcript directory exists
            transcript_dir = Path(self.transcript_dir)
            # Issue #358 - avoid blocking
            await asyncio.to_thread(transcript_dir.mkdir, parents=True, exist_ok=True)

            transcript_path = self._get_transcript_path(session_id)

            # Load existing transcript or create new
            # Issue #358 - avoid blocking
            if await asyncio.to_thread(transcript_path.exists):
                transcript = await self._load_existing_transcript(
                    transcript_path, session_id
                )
            else:
                transcript = self._create_empty_transcript(session_id)

            # Append new exchange
            transcript["messages"].append(
                {
                    "timestamp": datetime.now().isoformat(),
                    "user": user_message,
                    "assistant": assistant_message,
                }
            )
            transcript["updated_at"] = datetime.now().isoformat()
            transcript["message_count"] = len(transcript["messages"])

            # Write atomically
            await self._write_transcript_atomic(transcript_path, transcript, session_id)

        except Exception as e:
            logger.error("Failed to append to transcript file: %s", e)

    async def _load_transcript(self, session_id: str) -> List[Dict[str, str]]:
        """Load conversation history from transcript file (async with aiofiles)."""
        try:
            transcript_path = self._get_transcript_path(session_id)

            # Issue #358 - avoid blocking
            if not await asyncio.to_thread(transcript_path.exists):
                return []

            # Async file read with timeout
            try:
                # Open file first, then apply timeout to read operation
                async with aiofiles.open(transcript_path, "r", encoding="utf-8") as f:
                    content = await asyncio.wait_for(f.read(), timeout=5.0)
                    transcript = json.loads(content)

                # Convert to simple history format (last 10 messages)
                messages = transcript.get("messages", [])[-10:]
                return [
                    {"user": msg["user"], "assistant": msg["assistant"]}
                    for msg in messages
                ]

            except asyncio.TimeoutError:
                logger.warning(
                    f"File read timeout after 5s for {transcript_path}, returning empty history"
                )
                return []
            except OSError as os_err:
                logger.warning(
                    "Failed to read transcript file %s: %s", transcript_path, os_err
                )
                return []

        except Exception as e:
            logger.error("Failed to load transcript file: %s", e)
            return []

    def _handle_existing_user_entry(
        self,
        last_entry: Dict[str, str],
        llm_response: str,
        session_id: str,
    ) -> None:
        """Handle case where last entry has same user message.

        Issue #620.

        Args:
            last_entry: The last entry in conversation history
            llm_response: New LLM response to merge
            session_id: Session identifier for logging
        """
        existing_response = last_entry.get("assistant", "")
        if not existing_response:
            last_entry["assistant"] = llm_response
            logger.debug(
                "[_persist_conversation] Filled placeholder entry for session %s",
                session_id,
            )
        elif llm_response not in existing_response:
            last_entry["assistant"] = f"{existing_response}\n\n{llm_response}"
            logger.debug(
                "[_persist_conversation] Appended to existing entry for session %s (deduplication)",
                session_id,
            )
        else:
            logger.debug(
                "[_persist_conversation] Skipped duplicate response for session %s",
                session_id,
            )

    def _update_conversation_history(
        self,
        session: WorkflowSession,
        message: str,
        llm_response: str,
        session_id: str,
    ) -> None:
        """Update session conversation history with deduplication.

        Issue #620.

        Args:
            session: Workflow session object
            message: User message
            llm_response: LLM response
            session_id: Session identifier for logging
        """
        if session.conversation_history:
            last_entry = session.conversation_history[-1]
            if last_entry.get("user") == message:
                self._handle_existing_user_entry(last_entry, llm_response, session_id)
            else:
                session.conversation_history.append(
                    {"user": message, "assistant": llm_response}
                )
        else:
            session.conversation_history.append(
                {"user": message, "assistant": llm_response}
            )

        if len(session.conversation_history) > 10:
            session.conversation_history = session.conversation_history[-10:]

    async def _persist_conversation(
        self,
        session_id: str,
        session: WorkflowSession,
        message: str,
        llm_response: str,
    ):
        """Persist conversation to Redis cache and file storage.

        Issue #620.

        Args:
            session_id: Session identifier
            session: Workflow session object
            message: User message
            llm_response: LLM response
        """
        self._update_conversation_history(session, message, llm_response, session_id)

        await asyncio.gather(
            self._save_conversation_history(session_id, session.conversation_history),
            self._append_to_transcript(session_id, message, llm_response),
        )

    def _register_user_message_in_history(
        self, session: WorkflowSession, message: str
    ) -> None:
        """
        Register user message in session history immediately (before LLM call).

        Issue #715: Fixes race condition where concurrent messages don't see
        each other's context. By adding the user message to conversation_history
        immediately (with empty assistant placeholder), subsequent concurrent
        messages will at least see the user part of previous messages in context.

        This is called before the LLM generates a response. The placeholder
        assistant response will be updated by _persist_conversation once the
        actual response is ready.

        Args:
            session: Workflow session object
            message: User message to register
        """
        # Check if this message is already registered (deduplication)
        if session.conversation_history:
            last_entry = session.conversation_history[-1]
            if last_entry.get("user") == message:
                # Already registered (possibly from a retry or rapid double-send)
                logger.debug(
                    "[_register_user_message] Message already in history, skipping"
                )
                return

        # Add user message with empty placeholder for assistant response
        # The placeholder will be filled by _persist_conversation
        session.conversation_history.append(
            {
                "user": message,
                "assistant": "",  # Placeholder, will be updated when response is ready
            }
        )
        logger.debug(
            "[_register_user_message] Registered user message in history "
            "(history length: %d)",
            len(session.conversation_history),
        )
