import json
import os
import time
import logging
from typing import List, Dict, Any

class ChatHistoryManager:
    def __init__(self, history_file: str = "data/chat_history.json", use_redis: bool = False, redis_host: str = "localhost", redis_port: int = 6379):
        """
        Initializes the ChatHistoryManager.
        
        Args:
            history_file (str): Path to the JSON file for persistent storage.
            use_redis (bool): If True, attempts to use Redis for active memory storage for performance.
            redis_host (str): Hostname for Redis server.
            redis_port (int): Port for Redis server.
        """
        self.history_file = history_file
        self.history: List[Dict[str, Any]] = []
        self.use_redis = use_redis
        self.redis_host = redis_host
        self.redis_port = redis_port
        self.redis_client = None
        
        if use_redis:
            try:
                import redis
                self.redis_client = redis.Redis(host=redis_host, port=redis_port, decode_responses=True)
                # Test connection
                self.redis_client.ping()
                logging.info("Redis connection established for active memory storage.")
            except ImportError:
                logging.error("Redis library not installed. Falling back to file storage. Install with 'pip install redis'")
                self.use_redis = False
            except redis.ConnectionError as e:
                logging.error(f"Failed to connect to Redis at {redis_host}:{redis_port}: {str(e)}. Falling back to file storage.")
                self.use_redis = False
        
        self._ensure_data_directory_exists()
        self._load_history()

    def _ensure_data_directory_exists(self):
        """Ensures the directory for the history file exists."""
        data_dir = os.path.dirname(self.history_file)
        if data_dir and not os.path.exists(data_dir):
            os.makedirs(data_dir, exist_ok=True)

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
                if history_data:
                    self.history = json.loads(history_data)
                    logging.info("Loaded chat history from Redis.")
                    return
            except Exception as e:
                logging.error(f"Error loading history from Redis: {str(e)}. Falling back to file storage.")
        
        # Default to file storage
        if os.path.exists(self.history_file):
            try:
                with open(self.history_file, 'r') as f:
                    self.history = json.load(f)
            except json.JSONDecodeError as e:
                self.history = []
                logging.warning(f"Could not decode JSON from {self.history_file}: {str(e)}. Starting with empty history.")
            except Exception as e:
                self.history = []
                logging.error(f"Error loading chat history from {self.history_file}: {str(e)}. Starting with empty history.")
        else:
            self.history = []
            logging.info(f"No history file found at {self.history_file}. Starting with empty history.")

    def _save_history(self):
        """
        Saves current chat history to the JSON file and optionally to Redis if enabled.
        
        Logs an error if the save operation fails.
        """
        # Save to file for persistence
        try:
            with open(self.history_file, 'w') as f:
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

    def add_message(self, sender: str, text: str, message_type: str = 'default', raw_data: Any = None):
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
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
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

    # Placeholder for session management (will be expanded later)
    def list_sessions(self) -> List[str]:
        """Lists available chat sessions."""
        # For now, only one session (the current history) is supported
        return ["default_session"]

    def load_session(self, session_id: str) -> List[Dict[str, Any]]:
        """Loads a specific chat session."""
        # For now, only default session is supported
        if session_id == "default_session":
            self._load_history()
            return self.history
        return []

    def save_session(self, session_id: str):
        """
        Saves the current chat history as a named session.
        
        Args:
            session_id (str): The identifier for the session to save.
        """
        # For now, saving just overwrites the default history
        self._save_history()
        logging.info(f"Current chat saved as '{session_id}'.")

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
    manager.add_message("thought", '{"tool_name": "greet"}', "thought", {"tool_name": "greet"})
    print("History after adding messages:", manager.get_all_messages())

    new_manager = ChatHistoryManager(test_file) # Simulate new instance loading
    print("History loaded by new manager:", new_manager.get_all_messages())

    new_manager.clear_history()
    print("History after clearing:", new_manager.get_all_messages())

    if os.path.exists(test_file):
        os.remove(test_file)
