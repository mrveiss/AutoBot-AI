# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Terminal Chat Integration Module

Handles integration between terminal output and chat history.
"""

import asyncio
import logging
import time
from pathlib import Path
from typing import Optional

import aiofiles

from chat_history import ChatHistoryManager
from utils.encoding_utils import is_terminal_prompt, strip_ansi_codes

logger = logging.getLogger(__name__)


class TerminalChatIntegrator:
    """Manages terminal output integration with chat history"""

    def __init__(
        self,
        conversation_id: Optional[str],
        chat_history_manager: Optional[ChatHistoryManager] = None,
        data_dir: str = "data/chats",
    ):
        """Initialize chat integrator with conversation and history manager."""
        self.conversation_id = conversation_id
        self.chat_history_manager = chat_history_manager or (
            ChatHistoryManager() if conversation_id else None
        )
        self.data_dir = Path(data_dir)

        # Output buffering for chat integration
        self._output_buffer = ""
        self._last_output_save_time = time.time()
        self._output_lock = asyncio.Lock()

    async def save_command_to_chat(self, command: str) -> bool:
        """Save a command to chat history"""
        if not self.chat_history_manager or not self.conversation_id:
            return False

        try:
            logger.info("[CHAT INTEGRATION] Saving command to chat: %s", command[:50])
            await self.chat_history_manager.add_message(
                sender="terminal",
                text=f"$ {command}",
                message_type="terminal_command",
                session_id=self.conversation_id,
            )
            logger.info("[CHAT INTEGRATION] Command saved successfully")
            return True
        except Exception as e:
            logger.error("Failed to save command to chat: %s", e)
            return False

    async def buffer_output(self, content: str) -> None:
        """Buffer terminal output and save to chat when appropriate"""
        if not self.chat_history_manager or not self.conversation_id or not content:
            return

        async with self._output_lock:
            # Accumulate output in buffer
            self._output_buffer += content
            current_time = time.time()

            # Save to chat when:
            # 1. Buffer is large enough (>500 chars) OR
            # 2. Enough time has passed (>2 seconds) OR
            # 3. Output contains a newline (command completed)
            should_save = (
                len(self._output_buffer) > 500
                or (current_time - self._last_output_save_time) > 2.0
                or "\n" in content
            )

            if should_save and self._output_buffer.strip():
                await self._save_buffered_output(current_time)

    async def _save_buffered_output(self, current_time: float) -> None:
        """Save buffered output to chat history"""
        clean_content = strip_ansi_codes(self._output_buffer).strip()

        # Check if this is a terminal prompt (not real output)
        is_prompt = is_terminal_prompt(clean_content)

        # Only save if there's actual text content AND it's not a terminal prompt
        if clean_content and not is_prompt:
            try:
                logger.info(
                    f"[CHAT INTEGRATION] Saving output to chat: "
                    f"{len(self._output_buffer)} chars (clean: {len(clean_content)} chars)"
                )
                await self.chat_history_manager.add_message(
                    sender="terminal",
                    text=clean_content,
                    message_type="terminal_output",
                    session_id=self.conversation_id,
                )
                logger.info("[CHAT INTEGRATION] Output saved successfully")
            except Exception as e:
                logger.error("Failed to save output to chat: %s", e)
        else:
            skip_reason = "terminal prompt" if is_prompt else "only ANSI codes"
            logger.debug(
                f"[CHAT INTEGRATION] Skipping save - buffer is {skip_reason} "
                f"({len(self._output_buffer)} chars)"
            )

        # Reset buffer
        self._output_buffer = ""
        self._last_output_save_time = current_time

    async def flush_buffer(self) -> None:
        """Flush any remaining buffered output to chat"""
        if not self.chat_history_manager or not self.conversation_id:
            return

        try:
            async with self._output_lock:
                if self._output_buffer.strip():
                    clean_content = strip_ansi_codes(self._output_buffer).strip()
                    logger.info(
                        f"[CHAT INTEGRATION] Flushing remaining output buffer: "
                        f"{len(self._output_buffer)} chars (clean: {len(clean_content)} chars)"
                    )
                    if clean_content:
                        await self.chat_history_manager.add_message(
                            sender="terminal",
                            text=clean_content,
                            message_type="terminal_output",
                            session_id=self.conversation_id,
                        )
                    self._output_buffer = ""
                    logger.info("[CHAT INTEGRATION] Buffer flushed successfully")
        except Exception as e:
            logger.error("Failed to flush output buffer: %s", e)

    async def write_to_transcript(self, content: str) -> bool:
        """Write content to terminal transcript file"""
        if not self.conversation_id or not content:
            return False

        try:
            # Strip ANSI escape codes before writing to transcript
            clean_content = strip_ansi_codes(content)
            if not clean_content:
                return False

            transcript_file = f"{self.conversation_id}_terminal_transcript.txt"
            transcript_path = self.data_dir / transcript_file
            async with aiofiles.open(transcript_path, "a", encoding="utf-8") as f:
                await f.write(clean_content)
            return True
        except OSError as e:
            logger.error("Failed to write to transcript (I/O error): %s", e)
            return False
        except Exception as e:
            logger.error("Failed to write to transcript: %s", e)
            return False
