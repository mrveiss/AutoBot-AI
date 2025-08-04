import json
import os
import time
import logging
from typing import List, Dict, Any, Optional

# Import the centralized ConfigManager and Redis client utility
from src.config import config as global_config_manager
from src.utils.redis_client import get_redis_client


class ChatHistoryManager:
    def __init__(
        self,
        history_file: Optional[str] = None,
        use_redis: Optional[bool] = None,
        redis_host: Optional[str] = None,
        redis_port: Optional[int] = None,
    ):
        """
        Initializes the ChatHistoryManager.

        Args:
            history_file (str): Path to the JSON file for persistent storage.
            use_redis (bool): If True, attempts to use Redis for active memory storage for performance.
            redis_host (str): Hostname for Redis server.
            redis_port (int): Port for Redis server.
        """
        # Load configuration from centralized config manager
        data_config = global_config_manager.get("data", {})
        redis_config = global_config_manager.get_redis_config()

        # Set values using configuration with environment variable overrides
        self.history_file = history_file or data_config.get(
            "chat_history_file",
            os.getenv("AUTOBOT_CHAT_HISTORY_FILE", "data/chat_history.json"),
        )
        self.use_redis = (
            use_redis if use_redis is not None else redis_config.get("enabled", False)
        )
        self.redis_host = redis_host or redis_config.get("host", "localhost")
        self.redis_port = redis_port or redis_config.get("port", 6379)

        self.history: List[Dict[str, Any]] = []
        self.redis_client = None

        if self.use_redis:
            # Use centralized Redis client utility
            self.redis_client = get_redis_client(async_client=False)
            if self.redis_client:
                logging.info(
                    "Redis connection established via centralized utility for active memory storage."
                )
            else:
                logging.error(
                    "Failed to get Redis client from centralized utility. Falling back to file storage."
                )
                self.use_redis = False

        self._ensure_data_directory_exists()
        self._load_history()

    def _ensure_data_directory_exists(self):
        """Ensures the directory for the history file exists."""
        data_dir = os.path.dirname(self.history_file)
        if data_dir and not os.path.exists(data_dir):
            os.makedirs(data_dir, exist_ok=True)

    def _get_chats_directory(self) -> str:
        """Get the chats directory path from configuration."""
        data_config = global_config_manager.get("data", {})
        return data_config.get(
            "chats_directory", os.getenv("AUTOBOT_CHATS_DIRECTORY", "data/chats")
        )

    def _load_history(self):
        """
        Loads chat history from the JSON file or Redis if enabled.

        If using Redis, it attempts to load active session data from Redis.
        If the file exists but cannot be decoded or read properly, it starts with an empty history.
        If the file does not exist, it initializes an empty history.
        """
        if self.use_redis and self.redis_client:
            try:
                # Attempt to load active session from Redis
                history_data = self.redis_client.get("autobot:chat_history")
                if isinstance(history_data, str):
                    self.history = json.loads(history_data)
                    logging.info("Loaded chat history from Redis.")
                    return
                elif history_data is not None:
                    logging.warning(
                        f"Received non-string data from Redis for chat history: type={type(history_data)}"
                    )
            except Exception as e:
                logging.error(
                    f"Error loading history from Redis: {str(e)}. Falling back to file storage."
                )

        # Default to file storage
        if os.path.exists(self.history_file):
            try:
                with open(self.history_file, "r") as f:
                    self.history = json.load(f)
            except json.JSONDecodeError as e:
                self.history = []
                logging.warning(
                    f"Could not decode JSON from {self.history_file}: {str(e)}. Starting with empty history."
                )
            except Exception as e:
                self.history = []
                logging.error(
                    f"Error loading chat history from {self.history_file}: {str(e)}. Starting with empty history."
                )
        else:
            self.history = []
            logging.info(
                f"No history file found at {self.history_file}. Starting with empty history."
            )

    def _save_history(self):
        """
        Saves current chat history to the JSON file and optionally to Redis if enabled.

        Logs an error if the save operation fails.
        """
        # Save to file for persistence
        try:
            with open(self.history_file, "w") as f:
                json.dump(self.history, f, indent=2)
        except Exception as e:
            logging.error(f"Error saving chat history to {self.history_file}: {str(e)}")

        # Also save to Redis if enabled for fast access
        if self.use_redis and self.redis_client:
            try:
                self.redis_client.set("autobot:chat_history", json.dumps(self.history))
                # Optionally set an expiration time (e.g., 1 day) to clean up old data
                self.redis_client.expire("autobot:chat_history", 86400)
            except Exception as e:
                logging.error(f"Error saving chat history to Redis: {str(e)}")

    def add_message(
        self,
        sender: str,
        text: str,
        message_type: str = "default",
        raw_data: Any = None,
    ):
        """
        Adds a new message to the history and saves it to file.

        Args:
            sender (str): The sender of the message (e.g., 'user', 'bot').
            text (str): The content of the message.
            message_type (str): The type of message (default is 'default').
            raw_data (Any): Additional raw data associated with the message.
        """
        message = {
            "sender": sender,
            "text": text,
            "messageType": message_type,
            "rawData": raw_data,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        self.history.append(message)
        self._save_history()
        logging.debug(f"Added message from {sender} with type {message_type}")

    def get_all_messages(self) -> List[Dict[str, Any]]:
        """Returns the entire chat history."""
        return self.history

    def clear_history(self):
        """
        Clears the entire chat history and saves the empty history to file.
        """
        self.history = []
        self._save_history()
        logging.info("Chat history cleared.")

    def list_sessions(self) -> List[Dict[str, Any]]:
        """Lists available chat sessions with their metadata."""
        try:
            sessions = []
            chats_directory = self._get_chats_directory()

            # Ensure chats directory exists
            if not os.path.exists(chats_directory):
                os.makedirs(chats_directory, exist_ok=True)
                return sessions

            # Look for chat files in the chats directory
            for filename in os.listdir(chats_directory):
                if filename.startswith("chat_") and filename.endswith(".json"):
                    chat_id = filename.replace("chat_", "").replace(".json", "")
                    chat_path = os.path.join(chats_directory, filename)

                    try:
                        with open(chat_path, "r") as f:
                            chat_data = json.load(f)

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
                        logging.error(f"Error reading chat file {filename}: {str(e)}")
                        continue

            # Sort by last modified time (most recent first)
            sessions.sort(key=lambda x: x.get("lastModified", ""), reverse=True)
            return sessions

        except Exception as e:
            logging.error(f"Error listing chat sessions: {str(e)}")
            return []

    def load_session(self, session_id: str) -> List[Dict[str, Any]]:
        """Loads a specific chat session."""
        try:
            chats_directory = self._get_chats_directory()
            chat_file = f"{chats_directory}/chat_{session_id}.json"

            if not os.path.exists(chat_file):
                logging.warning(f"Chat session {session_id} not found")
                return []

            with open(chat_file, "r") as f:
                chat_data = json.load(f)

            return chat_data.get("messages", [])

        except Exception as e:
            logging.error(f"Error loading chat session {session_id}: {str(e)}")
            return []

    def save_session(
        self,
        session_id: str,
        messages: Optional[List[Dict[str, Any]]] = None,
        name: str = "",
    ):
        """
        Saves a chat session with messages and metadata.

        Args:
            session_id (str): The identifier for the session to save.
            messages (Optional[List[Dict[str, Any]]]): The messages to save (defaults to current history).
            name (str): Optional name for the chat session.
        """
        try:
            # Ensure chats directory exists
            chats_directory = self._get_chats_directory()
            if not os.path.exists(chats_directory):
                os.makedirs(chats_directory, exist_ok=True)

            chat_file = f"{chats_directory}/chat_{session_id}.json"
            current_time = time.strftime("%Y-%m-%d %H:%M:%S")

            # Use provided messages or current history
            session_messages = self.history if messages is None else messages

            # Load existing chat data if it exists to preserve metadata
            chat_data = {}
            if os.path.exists(chat_file):
                try:
                    with open(chat_file, "r") as f:
                        chat_data = json.load(f)
                except Exception as e:
                    logging.warning(
                        f"Could not load existing chat data for {session_id}: {str(e)}"
                    )

            # Update chat data
            chat_data.update(
                {
                    "chatId": session_id,
                    "name": name or chat_data.get("name", ""),
                    "messages": session_messages,
                    "last_modified": current_time,
                    "created_time": chat_data.get("created_time", current_time),
                }
            )

            # Save to file
            with open(chat_file, "w") as f:
                json.dump(chat_data, f, indent=2)

            logging.info(f"Chat session '{session_id}' saved successfully")

        except Exception as e:
            logging.error(f"Error saving chat session {session_id}: {str(e)}")

    def delete_session(self, session_id: str) -> bool:
        """
        Deletes a chat session.

        Args:
            session_id (str): The identifier for the session to delete.

        Returns:
            bool: True if deletion was successful, False otherwise.
        """
        try:
            chats_directory = self._get_chats_directory()
            chat_file = f"{chats_directory}/chat_{session_id}.json"

            if not os.path.exists(chat_file):
                logging.warning(f"Chat session {session_id} not found for deletion")
                return False

            os.remove(chat_file)
            logging.info(f"Chat session '{session_id}' deleted successfully")
            return True

        except Exception as e:
            logging.error(f"Error deleting chat session {session_id}: {str(e)}")
            return False

    def update_session_name(self, session_id: str, name: str) -> bool:
        """
        Updates the name of a chat session.

        Args:
            session_id (str): The identifier for the session to update.
            name (str): The new name for the session.

        Returns:
            bool: True if update was successful, False otherwise.
        """
        try:
            chats_directory = self._get_chats_directory()
            chat_file = f"{chats_directory}/chat_{session_id}.json"

            if not os.path.exists(chat_file):
                logging.warning(f"Chat session {session_id} not found for name update")
                return False

            # Load existing chat data
            with open(chat_file, "r") as f:
                chat_data = json.load(f)

            # Update name and last modified time
            chat_data["name"] = name
            chat_data["last_modified"] = time.strftime("%Y-%m-%d %H:%M:%S")

            # Save updated data
            with open(chat_file, "w") as f:
                json.dump(chat_data, f, indent=2)

            logging.info(f"Chat session '{session_id}' name updated to '{name}'")
            return True

        except Exception as e:
            logging.error(f"Error updating chat session {session_id} name: {str(e)}")
            return False


# Example Usage (for testing)
if __name__ == "__main__":
    # Use a temporary file for testing
    test_file = "data/test_chat_history.json"
    if os.path.exists(test_file):
        os.remove(test_file)

    manager = ChatHistoryManager(test_file)
    print("Initial history:", manager.get_all_messages())

    manager.add_message("user", "Hello there!")
    manager.add_message("bot", "Hi! How can I help?")
    manager.add_message(
        "thought", '{"tool_name": "greet"}', "thought", {"tool_name": "greet"}
    )
    print("History after adding messages:", manager.get_all_messages())

    new_manager = ChatHistoryManager(test_file)  # Simulate new instance loading
    print("History loaded by new manager:", new_manager.get_all_messages())

    new_manager.clear_history()
    print("History after clearing:", new_manager.get_all_messages())

    if os.path.exists(test_file):
        os.remove(test_file)
