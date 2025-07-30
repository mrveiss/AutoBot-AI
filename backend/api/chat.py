from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import os
import json
import uuid
from datetime import datetime
import logging
import requests

from src.config import global_config_manager

router = APIRouter()

logger = logging.getLogger(__name__)

# Directory to store chat data
CHAT_DATA_DIR = global_config_manager.get_nested('backend.chat_data_dir', 'data/chats')
os.makedirs(CHAT_DATA_DIR, exist_ok=True)

# Ollama configuration
OLLAMA_ENDPOINT = global_config_manager.get_nested('backend.ollama_endpoint', 'http://localhost:11434/api/generate')

class ChatMessage(BaseModel):
    message: str

class ChatSave(BaseModel):
    messages: list

def get_chat_file_path(chat_id):
    return os.path.join(CHAT_DATA_DIR, f"chat_{chat_id}.json")

def communicate_with_ollama(prompt):
    """Function to communicate with Ollama LLM"""
    try:
        logger.info(f"Sending request to Ollama with prompt: {prompt}")
        payload = {
            "model": global_config_manager.get_nested('backend.ollama_model', 'llama2'),
            "prompt": prompt,
            "stream": global_config_manager.get_nested('backend.streaming', False)
        }
        logger.info(f"Ollama request payload: {json.dumps(payload, indent=2)}")

        response = requests.post(OLLAMA_ENDPOINT, json=payload, timeout=global_config_manager.get_nested('backend.timeout', 30), stream=global_config_manager.get_nested('backend.streaming', False))

        if response.ok:
            if global_config_manager.get_nested('backend.streaming', False):
                def stream_response():
                    full_text = ""
                    thought_text = ""
                    json_text = ""
                    for chunk in response.iter_lines():
                        if chunk:
                            data = json.loads(chunk)
                            if 'response' in data:
                                response_text = data['response']
                                full_text += response_text
                                message_type = 'response'

                                # Simple logic to detect thoughts in the response
                                if "think" in response_text.lower() or "thought" in response_text.lower():
                                    thought_text += response_text
                                    message_type = 'thought'
                                # Simple logic to detect JSON in the response
                                elif "{" in response_text and "}" in response_text:
                                    json_text += response_text
                                    message_type = 'json'

                                # Use Server-Sent Events format
                                event_data = json.dumps({
                                    "text": response_text,
                                    "full_text": full_text if message_type == 'response' else (thought_text if message_type == 'thought' else json_text),
                                    "type": message_type,
                                    "done": data.get('done', False)
                                })
                                yield f"data: {event_data}\n\n"

                return StreamingResponse(stream_response(), media_type="text/event-stream")
            else:
                result = response.json()
                logger.info(f"Ollama response: {json.dumps(result, indent=2)}")
                if 'response' in result:
                    return result['response']
                else:
                    logger.error("No 'response' field in Ollama response")
                    return "Error: Invalid response format from Ollama"
        else:
            error_msg = f"Error from Ollama: Status {response.status_code} - {response.text}"
            logger.error(error_msg)
            return error_msg
    except Exception as e:
        error_msg = f"Error communicating with Ollama: {str(e)}"
        logger.error(error_msg)
        return error_msg

@router.post("/api/chat")
async def chat(request: ChatMessage):
    try:
        message_text = request.message.strip()
        logger.info(f"Received message: '{request.message}'")

        # Check if Ollama is available
        try:
            ollama_response = communicate_with_ollama(message_text)
            if isinstance(ollama_response, StreamingResponse):
                return ollama_response
            elif ollama_response.startswith("Error"):
                logger.warning(f"Falling back to default response due to Ollama error: {ollama_response}")
                response_text = f"Hello, I'm here to help with '{message_text}'. How can I assist further?"
                return {
                    "text": response_text,
                    "type": "response",
                    "llm_request": {"prompt": message_text},
                    "llm_response": {"error": ollama_response}
                }
            else:
                return {
                    "text": ollama_response,
                    "type": "response",
                    "llm_request": {"prompt": message_text},
                    "llm_response": {"text": ollama_response}
                }
        except Exception as e:
            logger.error(f"Error processing with Ollama: {str(e)}")
            response_text = f"Hello, I'm here to help with '{message_text}'. How can I assist further?"
            return {
                "text": response_text,
                "type": "response",
                "llm_request": {"prompt": message_text},
                "llm_response": {"error": str(e)}
            }
    except Exception as e:
        error_msg = f"Error processing chat: {str(e)}"
        logger.error(error_msg)
        raise HTTPException(status_code=500, detail=error_msg)

@router.post("/api/chats/new")
async def create_new_chat():
    chat_id = str(uuid.uuid4())
    chat_file = get_chat_file_path(chat_id)
    initial_message = [{
        "sender": "bot",
        "text": "Hello! How can I assist you today?",
        "timestamp": datetime.now().strftime("%H:%M:%S"),
        "type": "response"
    }]
    with open(chat_file, 'w') as f:
        json.dump(initial_message, f, indent=2)
    logger.info(f"Created new chat {chat_id}")
    return {"chatId": chat_id}

@router.get("/api/chats")
async def get_chat_list():
    chats = []
    chat_dir = os.path.join(CHAT_DATA_DIR)
    if not os.path.exists(chat_dir):
        os.makedirs(chat_dir, exist_ok=True)
        logger.info(f"Created chat directory {chat_dir}")
        return {"chats": []}
    for filename in os.listdir(chat_dir):
        if filename.startswith("chat_") and filename.endswith(".json"):
            chat_id = filename[5:-5]
            chats.append({"chatId": chat_id, "name": ""})
    logger.info(f"Returning chat list with {len(chats)} chats")
    return {"chats": chats}

@router.post("/api/chats/{chat_id}")
async def save_chat_messages(chat_id: str, messages: list):
    try:
        chat_file = get_chat_file_path(chat_id)
        with open(chat_file, 'w') as f:
            json.dump(messages, f, indent=2)
        logger.info(f"Saved messages for chat {chat_id}")
        return {"status": "success"}
    except Exception as e:
        logger.error(f"Error saving chat messages for {chat_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error saving chat messages: {str(e)}")

@router.get("/api/chats/{chat_id}")
async def get_chat_messages(chat_id: str):
    try:
        chat_file = get_chat_file_path(chat_id)
        if os.path.exists(chat_file):
            with open(chat_file, 'r') as f:
                return json.load(f)
        logger.info(f"No messages found for chat {chat_id}, returning empty list")
        return []
    except Exception as e:
        logger.error(f"Error loading chat messages for {chat_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error loading chat messages: {str(e)}")

@router.delete("/api/chats/{chat_id}")
async def delete_chat(chat_id: str):
    try:
        chat_file = get_chat_file_path(chat_id)
        if os.path.exists(chat_file):
            os.remove(chat_file)
            logger.info(f"Deleted chat {chat_id}")
            return {"status": "success"}
        else:
            logger.info(f"Chat {chat_id} not found for deletion")
            return {"status": "success", "message": "Chat not found"}
    except Exception as e:
        logger.error(f"Error deleting chat {chat_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error deleting chat: {str(e)}")

@router.post("/api/chats/{chat_id}/save")
async def save_chat(chat_id: str, chat_data: ChatSave):
    try:
        chat_file = get_chat_file_path(chat_id)
        with open(chat_file, 'w') as f:
            json.dump(chat_data.messages, f, indent=2)
        logger.info(f"Saved chat data for {chat_id}")
        return {"status": "success"}
    except Exception as e:
        logger.error(f"Error saving chat data for {chat_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error saving chat: {str(e)}")

@router.post("/api/chats/{chat_id}/reset")
async def reset_chat(chat_id: str):
    try:
        chat_file = get_chat_file_path(chat_id)
        initial_message = [{
            "sender": "bot",
            "text": "Hello! How can I assist you today?",
            "timestamp": datetime.now().strftime("%H:%M:%S"),
            "type": "response"
        }]
        with open(chat_file, 'w') as f:
            json.dump(initial_message, f, indent=2)
        logger.info(f"Reset chat {chat_id}")
        return {"status": "success"}
    except Exception as e:
        logger.error(f"Error resetting chat {chat_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error resetting chat: {str(e)}")

@router.post("/api/chats/cleanup_messages")
async def cleanup_messages():
    """Clean up all leftover message files including json_output, llm_response, planning and debug messages"""
    try:
        result = cleanup_message_files()
        logger.info(f"Message cleanup completed: {result}")
        return result
    except Exception as e:
        logger.error(f"Error during message cleanup: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error during message cleanup: {str(e)}")

@router.post("/api/chats/cleanup_all")
async def cleanup_all_chat_data():
    """Clean up all chat data and message files completely"""
    try:
        cleaned_files = []
        freed_space = 0

        # First run the message file cleanup
        message_cleanup_result = cleanup_message_files()
        if message_cleanup_result["status"] == "success":
            cleaned_files.extend(message_cleanup_result["cleaned_files"])
            freed_space += int(message_cleanup_result.get("freed_space_bytes", 0))

        # Remove all chat JSON files
        if os.path.exists(CHAT_DATA_DIR):
            for filename in os.listdir(CHAT_DATA_DIR):
                filepath = os.path.join(CHAT_DATA_DIR, filename)
                if os.path.isfile(filepath) and filename.startswith("chat_") and filename.endswith(".json"):
                    try:
                        file_size = os.path.getsize(filepath)
                        os.remove(filepath)
                        cleaned_files.append(filepath)
                        freed_space += file_size
                        logger.info(f"Removed chat file: {filepath}")
                    except Exception as e:
                        logger.error(f"Error removing chat file {filepath}: {str(e)}")

        # Remove entire messages directory if it exists
        messages_dir = "data/messages"
        if os.path.exists(messages_dir):
            try:
                dir_size = sum(os.path.getsize(os.path.join(dirpath, filename))
                              for dirpath, dirnames, filenames in os.walk(messages_dir)
                              for filename in filenames)
                shutil.rmtree(messages_dir)
                cleaned_files.append(f"Removed entire directory: {messages_dir}")
                freed_space += dir_size
                logger.info(f"Removed messages directory: {messages_dir}")
            except Exception as e:
                logger.error(f"Error removing messages directory: {str(e)}")

        result = {
            "status": "success",
            "message": f"Complete cleanup finished - removed {len(cleaned_files)} files/folders",
            "cleaned_files": cleaned_files,
            "freed_space_bytes": freed_space
        }

        logger.info(f"Complete chat cleanup completed: {result}")
        return result
    except Exception as e:
        logger.error(f"Error during complete chat cleanup: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error during complete chat cleanup: {str(e)}")

def cleanup_message_files():
    """Clean up all leftover message files including json_output, llm_response, planning and debug messages"""
    try:
        cleaned_files = []
        freed_space = 0

        # Expanded file patterns to catch more leftover files
        file_patterns = [
            "json_output*", "llm_response*", "planning*", "debug*",
            "*.tmp", "*.log", "*.cache", "*.bak",
            "*_response", "*_output", "*_debug", "*_planning",
            "response_*", "output_*", "debug_*", "planning_*",
            "*.txt", "*.json"  # Be more thorough with potential leftover files
        ]

        # Look for message directories in data/messages/
        messages_dir = "data/messages"
        if os.path.exists(messages_dir):
            logger.info(f"Scanning messages directory: {messages_dir}")
            for chat_folder in os.listdir(messages_dir):
                chat_folder_path = os.path.join(messages_dir, chat_folder)
                if os.path.isdir(chat_folder_path):
                    logger.info(f"Processing chat folder: {chat_folder_path}")
                    folder_cleaned = False

                    # Look for leftover files in each chat folder
                    for file_pattern in file_patterns:
                        for filepath in glob.glob(os.path.join(chat_folder_path, file_pattern)):
                            if os.path.isfile(filepath):
                                try:
                                    file_size = os.path.getsize(filepath)
                                    os.remove(filepath)
                                    cleaned_files.append(filepath)
                                    freed_space += file_size
                                    folder_cleaned = True
                                    logger.info(f"Removed leftover file: {filepath}")
                                except Exception as e:
                                    logger.error(f"Error removing file {filepath}: {str(e)}")

                    # Remove empty chat folders or folders that only contained leftover files
                    try:
                        remaining_files = os.listdir(chat_folder_path)
                        if not remaining_files:
                            os.rmdir(chat_folder_path)
                            cleaned_files.append(f"Empty folder: {chat_folder_path}")
                            logger.info(f"Removed empty chat folder: {chat_folder_path}")
                        elif folder_cleaned:
                            logger.info(f"Cleaned files from chat folder: {chat_folder_path}, remaining files: {remaining_files}")
                    except Exception as e:
                        logger.error(f"Error removing empty folder {chat_folder_path}: {str(e)}")

        # Also clean up any leftover files in the main chat data directory
        if os.path.exists(CHAT_DATA_DIR):
            logger.info(f"Scanning main chat data directory: {CHAT_DATA_DIR}")
            for file_pattern in file_patterns:
                for filepath in glob.glob(os.path.join(CHAT_DATA_DIR, file_pattern)):
                    if os.path.isfile(filepath):
                        # Skip legitimate chat JSON files
                        filename = os.path.basename(filepath)
                        if filename.startswith("chat_") and filename.endswith(".json"):
                            continue
                        try:
                            file_size = os.path.getsize(filepath)
                            os.remove(filepath)
                            cleaned_files.append(filepath)
                            freed_space += file_size
                            logger.info(f"Removed leftover file: {filepath}")
                        except Exception as e:
                            logger.error(f"Error removing file {filepath}: {str(e)}")

        # Clean up any leftover files in project root that might be message-related
        root_patterns = ["json_output*", "llm_response*", "planning*", "debug*", "*.tmp"]
        for file_pattern in root_patterns:
            for filepath in glob.glob(file_pattern):
                if os.path.isfile(filepath):
                    try:
                        file_size = os.path.getsize(filepath)
                        os.remove(filepath)
                        cleaned_files.append(filepath)
                        freed_space += file_size
                        logger.info(f"Removed leftover file from root: {filepath}")
                    except Exception as e:
                        logger.error(f"Error removing root file {filepath}: {str(e)}")

        return {
            "status": "success",
            "message": f"Cleaned up {len(cleaned_files)} leftover files",
            "cleaned_files": cleaned_files,
            "freed_space_bytes": freed_space
        }
    except Exception as e:
        logger.error(f"Error during message cleanup: {str(e)}")
        return {
            "status": "error",
            "message": f"Error during cleanup: {str(e)}"
        }
