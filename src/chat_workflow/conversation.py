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
                    f"Loaded conversation history from Redis for session {session_id}"
                )
                return json.loads(history_json)
        except asyncio.TimeoutError:
            logger.warning(
                f"Redis get timeout after 2s for session {session_id}, falling back to file"
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
                f"Loaded conversation history from file for session {session_id}"
            )
            # Repopulate Redis cache (non-blocking, fire-and-forget)
            if self.redis_client is not None:
                asyncio.create_task(
                    self._save_conversation_history(session_id, history)
                )

            return history

        except Exception as e:
            logger.error(f"Failed to load conversation history: {e}")
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
                    f"Saved conversation history for session {session_id} to Redis"
                )
            except asyncio.TimeoutError:
                logger.warning(
                    f"Redis set timeout after 2s for session {session_id} - data may not be cached"
                )

        except Exception as e:
            logger.error(f"Failed to save conversation history to Redis: {e}")

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
            logger.info(f"Backed up corrupted file to {backup_path}")
        except Exception as backup_err:
            logger.warning(f"Could not backup corrupted file: {backup_err}")

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
            logger.warning(f"File write timeout after 5s for {transcript_path}")
            if temp_path.exists():
                temp_path.unlink()
        except OSError as os_err:
            logger.error(f"Failed to write transcript file {transcript_path}: {os_err}")

    async def _append_to_transcript(
        self, session_id: str, user_message: str, assistant_message: str
    ):
        """Append message exchange to long-term transcript file (async with aiofiles)."""
        try:
            # Ensure transcript directory exists
            transcript_dir = Path(self.transcript_dir)
            transcript_dir.mkdir(parents=True, exist_ok=True)

            transcript_path = self._get_transcript_path(session_id)

            # Load existing transcript or create new
            if transcript_path.exists():
                transcript = await self._load_existing_transcript(transcript_path, session_id)
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
            logger.error(f"Failed to append to transcript file: {e}")

    async def _load_transcript(self, session_id: str) -> List[Dict[str, str]]:
        """Load conversation history from transcript file (async with aiofiles)."""
        try:
            transcript_path = self._get_transcript_path(session_id)

            if not transcript_path.exists():
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
                logger.warning(f"Failed to read transcript file {transcript_path}: {os_err}")
                return []

        except Exception as e:
            logger.error(f"Failed to load transcript file: {e}")
            return []

    async def _persist_conversation(
        self,
        session_id: str,
        session: WorkflowSession,
        message: str,
        llm_response: str,
    ):
        """
        Persist conversation to Redis cache and file storage.

        Handles deduplication: if the last entry has the same user message,
        appends the new response to avoid duplicate entries (Issue #177).

        Args:
            session_id: Session identifier
            session: Workflow session object
            message: User message
            llm_response: LLM response
        """
        # DEDUPLICATION FIX (Issue #177): Check if last entry has same user message
        # This prevents duplicate entries when both terminal service and chat flow persist
        if session.conversation_history:
            last_entry = session.conversation_history[-1]
            if last_entry.get("user") == message:
                # Same user message - append new response to existing assistant response
                existing_response = last_entry.get("assistant", "")
                # Only append if the new response is different and not already included
                if llm_response not in existing_response:
                    last_entry["assistant"] = f"{existing_response}\n\n{llm_response}"
                    logger.debug(
                        f"[_persist_conversation] Appended to existing entry for session "
                        f"{session_id} (deduplication)"
                    )
                else:
                    logger.debug(
                        f"[_persist_conversation] Skipped duplicate response for session "
                        f"{session_id}"
                    )
            else:
                # Different user message - append as new entry
                session.conversation_history.append(
                    {"user": message, "assistant": llm_response}
                )
        else:
            # Empty history - append as new entry
            session.conversation_history.append(
                {"user": message, "assistant": llm_response}
            )

        # Keep history manageable (max 10 exchanges)
        if len(session.conversation_history) > 10:
            session.conversation_history = session.conversation_history[-10:]

        # Persist to both Redis (short-term cache) and file (long-term storage)
        await self._save_conversation_history(session_id, session.conversation_history)
        await self._append_to_transcript(session_id, message, llm_response)
