# backend/chat_api.py - Separate chat management API
import json
import logging
import os
import shutil
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class Message(BaseModel):
    sender: str
    text: str
    timestamp: str
    type: str
    final: Optional[bool] = None

    class Config:
        extra = "allow"


class ChatSave(BaseModel):
    messages: List[Message]


class ChatAPI:
    def __init__(self, chat_data_dir: str = "data/chats"):
        self.chat_data_dir = Path(chat_data_dir)
        self.chat_data_dir.mkdir(parents=True, exist_ok=True)
        self.messages_dir = Path("data/messages")

    def get_chat_file_path(self, chat_id: str) -> Path:
        return self.chat_data_dir / f"chat_{chat_id}.json"

    async def create_new_chat(self) -> Dict[str, str]:
        """Create a new chat with unique ID"""
        chat_id = str(uuid.uuid4())
        chat_file = self.get_chat_file_path(chat_id)
        initial_message = [
            {
                "sender": "bot",
                "text": "Hello! How can I assist you today?",
                "timestamp": datetime.now().strftime("%H:%M:%S"),
                "type": "response",
            }
        ]
        with open(chat_file, "w") as f:
            json.dump(initial_message, f, indent=2)
        logger.info(f"Created new chat {chat_id}")
        return {"chatId": chat_id}

    async def get_chat_list(self) -> Dict[str, List[Dict]]:
        """Get list of all chats"""
        chats = []
        if not self.chat_data_dir.exists():
            self.chat_data_dir.mkdir(parents=True, exist_ok=True)
            return {"chats": []}

        for file_path in self.chat_data_dir.glob("chat_*.json"):
            chat_id = file_path.stem[5:]  # Remove 'chat_' prefix
            chats.append({"chatId": chat_id, "name": ""})

        logger.info(f"Returning chat list with {len(chats)} chats")
        return {"chats": chats}

    async def get_chat_messages(self, chat_id: str) -> List[Dict]:
        """Get messages for a specific chat"""
        try:
            chat_file = self.get_chat_file_path(chat_id)
            logger.info(f"Looking for chat file: {chat_file}")

            if chat_file.exists():
                try:
                    with open(chat_file, "r") as f:
                        messages = json.load(f)
                    logger.info(f"Found {len(messages)} messages for chat {chat_id}")
                    return messages
                except json.JSONDecodeError as e:
                    logger.error(f"Invalid JSON in chat file {chat_file}: {str(e)}")
                    return []
                except Exception as e:
                    logger.error(f"Error reading chat file {chat_file}: {str(e)}")
                    return []
            else:
                logger.info(
                    f"Chat file {chat_file} does not exist, returning empty list"
                )
                return []
        except Exception as e:
            logger.error(f"Error loading chat messages for {chat_id}: {str(e)}")
            return []

    async def save_chat_messages(
        self, chat_id: str, messages: List[Dict]
    ) -> Dict[str, str]:
        """Save messages for a chat"""
        try:
            # Validate and clean messages
            cleaned_messages = []
            for i, msg in enumerate(messages):
                try:
                    cleaned_msg = {
                        "sender": msg.get("sender", "unknown"),
                        "text": msg.get("text", ""),
                        "timestamp": msg.get(
                            "timestamp", datetime.now().strftime("%H:%M:%S")
                        ),
                        "type": msg.get("type", "message"),
                    }

                    if "final" in msg:
                        cleaned_msg["final"] = msg["final"]

                    cleaned_messages.append(cleaned_msg)
                except Exception as msg_error:
                    logger.warning(
                        f"Skipping invalid message at index {i}: {str(msg_error)}"
                    )
                    continue

            # Save to file
            chat_file = self.get_chat_file_path(chat_id)
            with open(chat_file, "w") as f:
                json.dump(cleaned_messages, f, indent=2)
            logger.info(
                f"Saved {len(cleaned_messages)} cleaned messages for chat {chat_id}"
            )
            return {"status": "success"}
        except Exception as e:
            logger.error(f"Error saving chat data for {chat_id}: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Error saving chat: {str(e)}")

    async def reset_chat(self, chat_id: str) -> Dict[str, str]:
        """Reset a chat to initial state"""
        try:
            chat_file = self.get_chat_file_path(chat_id)
            initial_message = [
                {
                    "sender": "bot",
                    "text": "Hello! How can I assist you today?",
                    "timestamp": datetime.now().strftime("%H:%M:%S"),
                    "type": "response",
                }
            ]
            with open(chat_file, "w") as f:
                json.dump(initial_message, f, indent=2)
            logger.info(f"Reset chat {chat_id}")
            return {"status": "success"}
        except Exception as e:
            logger.error(f"Error resetting chat {chat_id}: {str(e)}")
            raise HTTPException(
                status_code=500, detail=f"Error resetting chat: {str(e)}"
            )

    async def delete_chat(self, chat_id: str) -> Dict[str, str]:
        """Delete a chat and cleanup associated files"""
        try:
            chat_file = self.get_chat_file_path(chat_id)
            if chat_file.exists():
                chat_file.unlink()
                logger.info(f"Deleted chat {chat_id}")
            else:
                logger.info(f"Chat {chat_id} not found for deletion")

            # Clean up leftover message files from unified message logger
            await self._cleanup_chat_message_files(chat_id)

            return {"status": "success"}
        except Exception as e:
            logger.error(f"Error deleting chat {chat_id}: {str(e)}")
            raise HTTPException(
                status_code=500, detail=f"Error deleting chat: {str(e)}"
            )

    async def _cleanup_chat_message_files(self, chat_id: str):
        """Clean up message files associated with a chat"""
        if not self.messages_dir.exists():
            return

        current_time = time.time()

        for session_dir in self.messages_dir.iterdir():
            if session_dir.is_dir():
                try:
                    # Check if directory is older than 1 hour or empty
                    dir_mtime = session_dir.stat().st_mtime
                    is_old = (current_time - dir_mtime) > 3600  # 1 hour
                    is_empty = len(list(session_dir.iterdir())) == 0

                    if is_old or is_empty or chat_id in session_dir.name:
                        shutil.rmtree(session_dir)
                        logger.info(f"Cleaned up message directory: {session_dir}")
                except Exception as cleanup_error:
                    logger.warning(
                        f"Failed to cleanup message directory {session_dir}: "
                        f"{cleanup_error}"
                    )

    async def cleanup_all_message_files(self) -> Dict[str, Any]:
        """Clean up all leftover message files"""
        try:
            if not self.messages_dir.exists():
                return {
                    "status": "success",
                    "message": "No message directory to clean up",
                    "cleaned_count": 0,
                }

            cleaned_count = 0
            total_size = 0

            # Remove all session directories and their contents
            for session_dir in self.messages_dir.iterdir():
                if session_dir.is_dir():
                    try:
                        # Calculate size before deletion
                        for root, dirs, files in os.walk(session_dir):
                            for file in files:
                                file_path = os.path.join(root, file)
                                total_size += os.path.getsize(file_path)

                        shutil.rmtree(session_dir)
                        cleaned_count += 1
                        logger.info(f"Cleaned up message directory: {session_dir}")
                    except Exception as cleanup_error:
                        logger.error(
                            f"Failed to cleanup message directory {session_dir}: "
                            f"{cleanup_error}"
                        )

            # Remove the messages directory itself if it's empty
            try:
                if self.messages_dir.exists() and not any(self.messages_dir.iterdir()):
                    self.messages_dir.rmdir()
                    logger.info(
                        f"Removed empty messages directory: {self.messages_dir}"
                    )
            except Exception as e:
                logger.warning(f"Could not remove messages directory: {e}")

            return {
                "status": "success",
                "message": f"Cleaned up {cleaned_count} message directories",
                "cleaned_count": cleaned_count,
                "freed_space_bytes": total_size,
            }
        except Exception as e:
            logger.error(f"Error cleaning up message files: {str(e)}")
            raise HTTPException(
                status_code=500, detail=f"Error cleaning up message files: {str(e)}"
            )

    async def cleanup_all_chat_data(self) -> Dict[str, Any]:
        """Clean up all chat data and message files"""
        try:
            cleaned_chats = 0
            total_size = 0

            # Clean up chat files
            if self.chat_data_dir.exists():
                for chat_file in self.chat_data_dir.glob("chat_*.json"):
                    try:
                        total_size += chat_file.stat().st_size
                        chat_file.unlink()
                        cleaned_chats += 1
                        logger.info(f"Deleted chat file: {chat_file.name}")
                    except Exception as e:
                        logger.error(
                            f"Failed to delete chat file {chat_file.name}: {e}"
                        )

            # Clean up message files
            cleanup_result = await self.cleanup_all_message_files()
            cleaned_messages = cleanup_result.get("cleaned_count", 0)
            total_size += cleanup_result.get("freed_space_bytes", 0)

            return {
                "status": "success",
                "message": (
                    f"Cleaned up {cleaned_chats} chat files and "
                    f"{cleaned_messages} message directories"
                ),
                "cleaned_chats": cleaned_chats,
                "cleaned_messages": cleaned_messages,
                "freed_space_bytes": total_size,
            }
        except Exception as e:
            logger.error(f"Error in comprehensive cleanup: {str(e)}")
            raise HTTPException(
                status_code=500, detail=f"Error in comprehensive cleanup: {str(e)}"
            )
