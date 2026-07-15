# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Telegram Platform Adapter for Message Gateway"""

from typing import Any, Dict, Optional

from autobot_shared.logging_manager import get_logger

from .base_adapter import BaseAdapter, GatewayMessage, NormalizedResponse

logger = get_logger(__name__)


class TelegramAdapter(BaseAdapter):
    """Telegram platform adapter using python-telegram-bot Bot API."""

    def __init__(self) -> None:
        super().__init__("telegram")

    async def normalize_message(self, raw_message: Dict[str, Any]) -> GatewayMessage:
        """
        Convert Telegram Update/Message object to unified schema.

        Handles:
        - Text messages and commands
        - File/document attachments
        - Photos/images
        - Group chat threads
        """
        message = raw_message.get("message") or raw_message
        metadata = await self.extract_metadata(raw_message)

        chat = message.get("chat", {})
        from_user = message.get("from", {})
        reply_to = message.get("reply_to_message")

        metadata["message_id"] = message.get("message_id")
        metadata["chat_type"] = chat.get("type", "private")
        metadata["reply_to_message_id"] = reply_to.get("message_id") if reply_to else None
        metadata["is_reply"] = reply_to is not None
        metadata["thread_id"] = message.get("message_thread_id")

        # Extract file attachments (MVA-2075)
        file_info = self._extract_file_info(message)
        if file_info:
            metadata["has_file"] = True
            metadata["file_id"] = file_info.get("file_id")
            metadata["file_type"] = file_info.get("file_type")
            metadata["file_name"] = file_info.get("file_name")
            metadata["file_size"] = file_info.get("file_size")
            metadata["mime_type"] = file_info.get("mime_type")

        # Parse bot commands (MVA-2075)
        text = message.get("text", "") or message.get("caption", "")
        command_info = self._parse_command(text)
        if command_info:
            metadata["is_command"] = True
            metadata["command"] = command_info["command"]
            metadata["command_args"] = command_info["args"]

        return GatewayMessage(
            user_id=str(from_user.get("id", "")),
            platform="telegram",
            channel_id=str(chat.get("id", "")),
            message=text,
            timestamp=float(message.get("date", 0)),
            metadata=metadata,
        )

    def _extract_file_info(self, message: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Extract file information from Telegram message.

        Supports: photo, document, video, audio, voice, video_note
        """
        # Photo (array of sizes, take largest)
        if "photo" in message:
            photos = message["photo"]
            if photos:
                largest = max(photos, key=lambda p: p.get("file_size", 0))
                return {
                    "file_id": largest.get("file_id"),
                    "file_type": "photo",
                    "file_size": largest.get("file_size"),
                    "mime_type": "image/jpeg",
                }

        # Document
        if "document" in message:
            doc = message["document"]
            return {
                "file_id": doc.get("file_id"),
                "file_type": "document",
                "file_name": doc.get("file_name"),
                "file_size": doc.get("file_size"),
                "mime_type": doc.get("mime_type"),
            }

        # Video
        if "video" in message:
            video = message["video"]
            return {
                "file_id": video.get("file_id"),
                "file_type": "video",
                "file_name": video.get("file_name"),
                "file_size": video.get("file_size"),
                "mime_type": video.get("mime_type", "video/mp4"),
            }

        # Audio
        if "audio" in message:
            audio = message["audio"]
            return {
                "file_id": audio.get("file_id"),
                "file_type": "audio",
                "file_name": audio.get("file_name"),
                "file_size": audio.get("file_size"),
                "mime_type": audio.get("mime_type", "audio/mpeg"),
            }

        # Voice
        if "voice" in message:
            voice = message["voice"]
            return {
                "file_id": voice.get("file_id"),
                "file_type": "voice",
                "file_size": voice.get("file_size"),
                "mime_type": voice.get("mime_type", "audio/ogg"),
            }

        return None

    def _parse_command(self, text: str) -> Optional[Dict[str, Any]]:
        """
        Parse Telegram bot commands (/command arg1 arg2).

        Returns:
            Dict with 'command' and 'args' if text starts with '/', else None
        """
        if not text or not text.startswith("/"):
            return None

        parts = text.split()
        command = parts[0][1:]  # Remove leading '/'

        # Remove @botname if present (group chat commands)
        if "@" in command:
            command = command.split("@")[0]

        args = parts[1:] if len(parts) > 1 else []

        return {"command": command, "args": args}

    async def denormalize_response(self, unified_response: NormalizedResponse) -> Dict[str, Any]:
        """
        Convert unified response to Telegram API payload.

        Supports:
        - Text messages (sendMessage)
        - Photos (sendPhoto)
        - Documents (sendDocument)
        """
        payload: Dict[str, Any] = {
            "chat_id": unified_response.channel_id,
        }

        # Handle file/photo sending (MVA-2075)
        file_id = unified_response.metadata.get("file_id")
        file_type = unified_response.metadata.get("file_type", "text")

        if file_id and file_type == "photo":
            payload["photo"] = file_id
            payload["caption"] = unified_response.content
            payload["parse_mode"] = "Markdown"
            payload["_api_method"] = "sendPhoto"
        elif file_id and file_type == "document":
            payload["document"] = file_id
            payload["caption"] = unified_response.content
            payload["parse_mode"] = "Markdown"
            payload["_api_method"] = "sendDocument"
        else:
            # Text message
            payload["text"] = unified_response.content
            payload["parse_mode"] = "Markdown"
            payload["_api_method"] = "sendMessage"

        # Thread reply support
        if unified_response.response_type == "thread_reply":
            reply_id = unified_response.metadata.get("message_id")
            if reply_id:
                payload["reply_to_message_id"] = reply_id

        # Group chat thread support
        thread_id = unified_response.metadata.get("thread_id")
        if thread_id:
            payload["message_thread_id"] = thread_id

        return payload

    def get_rate_limit(self) -> Dict[str, int]:
        """Telegram Bot API: 30 messages/second globally, 1/second per chat."""
        return {"requests_per_second": 30, "burst_size": 30}
