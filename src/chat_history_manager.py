import json
import os
import time
from typing import List, Dict, Any

class ChatHistoryManager:
    def __init__(self, history_file: str = "data/chat_history.json"):
        self.history_file = history_file
        self.history: List[Dict[str, Any]] = []
        self._ensure_data_directory_exists()
        self._load_history()

    def _ensure_data_directory_exists(self):
        """Ensures the directory for the history file exists."""
        data_dir = os.path.dirname(self.history_file)
        if data_dir and not os.path.exists(data_dir):
            os.makedirs(data_dir, exist_ok=True)

    def _load_history(self):
        """Loads chat history from the JSON file."""
        if os.path.exists(self.history_file):
            try:
                with open(self.history_file, 'r') as f:
                    self.history = json.load(f)
            except json.JSONDecodeError:
                self.history = []
                print(f"Warning: Could not decode JSON from {self.history_file}. Starting with empty history.")
            except Exception as e:
                self.history = []
                print(f"Error loading chat history from {self.history_file}: {e}. Starting with empty history.")
        else:
            self.history = []

    def _save_history(self):
        """Saves current chat history to the JSON file."""
        try:
            with open(self.history_file, 'w') as f:
                json.dump(self.history, f, indent=2)
        except Exception as e:
            print(f"Error saving chat history to {self.history_file}: {e}")

    def add_message(self, sender: str, text: str, message_type: str = 'default', raw_data: Any = None):
        """Adds a new message to the history."""
        message = {
            "sender": sender,
            "text": text,
            "messageType": message_type,
            "rawData": raw_data,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
        }
        self.history.append(message)
        self._save_history()

    def get_all_messages(self) -> List[Dict[str, Any]]:
        """Returns the entire chat history."""
        return self.history

    def clear_history(self):
        """Clears the entire chat history."""
        self.history = []
        self._save_history()
        print("Chat history cleared.")

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
        """Saves the current chat history as a named session."""
        # For now, saving just overwrites the default history
        self._save_history()
        print(f"Current chat saved as '{session_id}'.")

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
