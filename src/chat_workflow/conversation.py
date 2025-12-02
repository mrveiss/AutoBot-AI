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

    async def _load_conversation_history(self, session_id: str) -> List[Dict[str, str]]:
        """Load conversation history from Redis (short-term) or file (long-term)."""
        try:
            # Try Redis first (fast access for recent conversations) with 2s timeout
            if self.redis_client is not None:
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
                    # Fall through to file-based fallback

            # Fall back to file-based transcript (long-term storage)
            history = await self._load_transcript(session_id)
            if history:
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

    async def _append_to_transcript(
        self, session_id: str, user_message: str, assistant_message: str
    ):
        """Append message exchange to long-term transcript file (async with aiofiles)."""
        try:
            # Ensure transcript directory exists
            transcript_dir = Path(self.transcript_dir)
            transcript_dir.mkdir(parents=True, exist_ok=True)

            transcript_path = self._get_transcript_path(session_id)

            # Load existing transcript or create new (async read with timeout)
            if transcript_path.exists():
                try:
                    # Open file first, then apply timeout to read operation
                    async with aiofiles.open(
                        transcript_path, "r", encoding="utf-8"
                    ) as f:
                        content = await asyncio.wait_for(f.read(), timeout=5.0)
                        transcript = json.loads(content)
                except asyncio.TimeoutError:
                    logger.warning(
                        f"File read timeout after 5s for {transcript_path}, creating new transcript"
                    )
                    transcript = {
                        "session_id": session_id,
                        "created_at": datetime.now().isoformat(),
                        "messages": [],
                    }
                except OSError as os_err:
                    logger.warning(
                        f"Failed to read transcript file {transcript_path}: {os_err}, "
                        f"creating new transcript"
                    )
                    transcript = {
                        "session_id": session_id,
                        "created_at": datetime.now().isoformat(),
                        "messages": [],
                    }
                except json.JSONDecodeError as json_err:
                    # Handle corrupted JSON files - backup and create fresh
                    logger.warning(
                        f"Corrupted transcript file {transcript_path}: {json_err}, "
                        f"creating fresh transcript"
                    )
                    # Backup corrupted file for debugging
                    backup_path = transcript_path.with_suffix(".json.corrupted")
                    try:
                        await asyncio.to_thread(transcript_path.rename, backup_path)
                        logger.info(f"Backed up corrupted file to {backup_path}")
                    except Exception as backup_err:
                        logger.warning(f"Could not backup corrupted file: {backup_err}")
                    transcript = {
                        "session_id": session_id,
                        "created_at": datetime.now().isoformat(),
                        "messages": [],
                    }
            else:
                transcript = {
                    "session_id": session_id,
                    "created_at": datetime.now().isoformat(),
                    "messages": [],
                }

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

            # Atomic write pattern: write to temp file then rename (with timeout)
            temp_path = transcript_path.with_suffix(".tmp")
            try:
                # Open file first, then apply timeout to write operation
                async with aiofiles.open(temp_path, "w", encoding="utf-8") as f:
                    await asyncio.wait_for(
                        f.write(json.dumps(transcript, indent=2, ensure_ascii=False)),
                        timeout=5.0,
                    )

                # Atomic rename (sync operation, very fast)
                await asyncio.to_thread(temp_path.rename, transcript_path)

                logger.debug(
                    f"Appended to transcript for session {session_id} "
                    f"({transcript['message_count']} total messages)"
                )

            except asyncio.TimeoutError:
                logger.warning(f"File write timeout after 5s for {transcript_path}")
                # Clean up temp file if it exists
                if temp_path.exists():
                    temp_path.unlink()
            except OSError as os_err:
                logger.error(f"Failed to write transcript file {transcript_path}: {os_err}")

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
