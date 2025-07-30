from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import os
import json
import yaml
from datetime import datetime
import requests
import logging
import uuid

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Import ChatHistoryManager
import sys
import os
import shutil
import glob
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from src.chat_history_manager import ChatHistoryManager

app = FastAPI()

# Load configuration from YAML file or environment variables
CONFIG_FILE = "config/config.yaml"
def load_config():
    config = {
        "cors_origins": [
            "http://localhost",
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "http://localhost:8080",
            "http://127.0.0.1:8080",
            "*",  # Temporarily allow all origins for debugging
        ],
        "ollama_endpoint": os.getenv("OLLAMA_ENDPOINT", "http://localhost:11434/api/generate"),
        "ollama_model": os.getenv("OLLAMA_MODEL", "llama2"),
        "chat_data_dir": os.getenv("CHAT_DATA_DIR", "data/chats"),
        "server_host": os.getenv("SERVER_HOST", "0.0.0.0"),
        "server_port": int(os.getenv("SERVER_PORT", 8001)),
        "streaming": os.getenv("STREAMING", "false").lower() == "true",
        "timeout": int(os.getenv("TIMEOUT", 60))
    }
    
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                file_config = yaml.safe_load(f)
                if file_config:
                    config.update(file_config.get('backend', {}))
        except Exception as e:
            logger.error(f"Error loading config from {CONFIG_FILE}: {str(e)}")
    
    # Load settings from the frontend saved settings if available - this takes priority
    settings_file = "config/settings.json"
    if os.path.exists(settings_file):
        try:
            with open(settings_file, 'r') as f:
                settings = json.load(f)
                backend_settings = settings.get('backend', {})
                if backend_settings.get('ollama_endpoint'):
                    config['ollama_endpoint'] = backend_settings.get('ollama_endpoint')
                    logger.info(f"Overriding ollama_endpoint from frontend settings: {config['ollama_endpoint']}")
                if backend_settings.get('ollama_model'):
                    config['ollama_model'] = backend_settings.get('ollama_model')
                    logger.info(f"Overriding ollama_model from frontend settings: {config['ollama_model']}")
                if 'streaming' in backend_settings:
                    config['streaming'] = backend_settings.get('streaming')
                    logger.info(f"Overriding streaming from frontend settings: {config['streaming']}")
                if 'timeout' in backend_settings:
                    config['timeout'] = backend_settings.get('timeout')
                    logger.info(f"Overriding timeout from frontend settings: {config['timeout']}")
                if 'cors_origins' in backend_settings and backend_settings['cors_origins']:
                    config['cors_origins'] = backend_settings.get('cors_origins')
                    logger.info(f"Overriding cors_origins from frontend settings: {config['cors_origins']}")
                # Log memory settings if available to confirm they are loaded
                if 'memory' in settings:
                    logger.info(f"Memory settings loaded from frontend settings: {settings['memory']}")
        except Exception as e:
            logger.error(f"Error loading backend settings from {settings_file}: {str(e)}")
    
    return config

config = load_config()

# Initialize chat history manager with Redis support
chat_history_manager = ChatHistoryManager(use_redis=True, redis_host="localhost", redis_port=6379)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=config['cors_origins'],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Directory to store chat data
CHAT_DATA_DIR = config['chat_data_dir']
os.makedirs(CHAT_DATA_DIR, exist_ok=True)

# Ollama configuration
OLLAMA_ENDPOINT = config['ollama_endpoint']

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
            "model": config['ollama_model'],
            "prompt": prompt,
            "stream": config['streaming']
        }
        logger.info(f"Ollama request payload: {json.dumps(payload, indent=2)}")
        
        response = requests.post(OLLAMA_ENDPOINT, json=payload, timeout=config['timeout'], stream=config['streaming'])
        
        if response.ok:
            if config['streaming']:
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

@app.post("/api/chat")
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

@app.post("/api/chats/new")
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

@app.get("/api/chats")
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

@app.post("/api/chats/{chat_id}")
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

@app.get("/api/chats/{chat_id}")
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

@app.delete("/api/chats/{chat_id}")
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

@app.post("/api/chats/{chat_id}/save")
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

@app.post("/api/chats/{chat_id}/reset")
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

# Path for settings file
SETTINGS_FILE = "config/settings.json"

class Settings(BaseModel):
    settings: dict

@app.post("/api/settings")
async def save_settings(settings_data: Settings):
    try:
        os.makedirs(os.path.dirname(SETTINGS_FILE), exist_ok=True)
        with open(SETTINGS_FILE, 'w') as f:
            json.dump(settings_data.settings, f, indent=2)
        logger.info("Saved settings")
        # Reload config after settings are saved
        global config
        config = load_config()
        logger.info(f"Updated configuration: {json.dumps(config, indent=2)}")
        return {"status": "success"}
    except Exception as e:
        logger.error(f"Error saving settings: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error saving settings: {str(e)}")

@app.get("/api/settings")
async def get_settings():
    try:
        if os.path.exists(SETTINGS_FILE):
            with open(SETTINGS_FILE, 'r') as f:
                return json.load(f)
        logger.info("No settings file found, returning empty dict")
        return {}
    except Exception as e:
        logger.error(f"Error loading settings: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error loading settings: {str(e)}")

@app.post("/api/settings/backend")
async def update_backend_settings(settings_data: Settings):
    try:
        # Load current settings
        current_settings = {}
        if os.path.exists(SETTINGS_FILE):
            with open(SETTINGS_FILE, 'r') as f:
                current_settings = json.load(f)
        
        # Update only backend-related settings
        if 'backend' in settings_data.settings:
            current_settings['backend'] = settings_data.settings['backend']
            with open(SETTINGS_FILE, 'w') as f:
                json.dump(current_settings, f, indent=2)
            logger.info("Updated backend settings")
            # Reload config after settings are saved
            global config
            config = load_config()
            logger.info(f"Updated backend configuration: {json.dumps(config, indent=2)}")
            return {"status": "success"}
        else:
            logger.error("No backend settings provided")
            raise HTTPException(status_code=400, detail="No backend settings provided")
    except Exception as e:
        logger.error(f"Error updating backend settings: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error updating backend settings: {str(e)}")

@app.get("/api/settings/backend")
async def get_backend_settings():
    try:
        if os.path.exists(SETTINGS_FILE):
            with open(SETTINGS_FILE, 'r') as f:
                settings = json.load(f)
                return settings.get('backend', {})
        logger.info("No settings file found, returning empty dict for backend settings")
        return {}
    except Exception as e:
        logger.error(f"Error loading backend settings: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error loading backend settings: {str(e)}")

@app.get("/api/prompts")
async def get_prompts():
    try:
        # Adjust path to look for prompts directory at project root
        prompts_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "prompts"))
        default_prompts_dir = os.path.join(prompts_dir, "default")
        prompts = []
        defaults = {}
        
        # Function to read prompt files recursively
        def read_prompt_files(directory, base_path=""):
            for entry in os.listdir(directory):
                full_path = os.path.join(directory, entry)
                rel_path = os.path.join(base_path, entry) if base_path else entry
                if os.path.isdir(full_path):
                    read_prompt_files(full_path, rel_path)
                elif os.path.isfile(full_path) and (entry.endswith('.txt') or entry.endswith('.md')):
                    try:
                        with open(full_path, 'r', encoding='utf-8') as f:
                            content = f.read()
                        prompt_id = rel_path.replace('/', '_').replace('\\', '_').rsplit('.', 1)[0]
                        prompt_type = base_path if base_path else "custom"
                        prompts.append({
                            "id": prompt_id,
                            "name": entry.rsplit('.', 1)[0],
                            "type": prompt_type,
                            "path": rel_path,
                            "content": content
                        })
                        if "default" in directory:
                            defaults[prompt_id] = content
                    except Exception as e:
                        logger.error(f"Error reading prompt file {full_path}: {str(e)}")
        
        # Read prompts from the prompts directory
        if os.path.exists(prompts_dir):
            read_prompt_files(prompts_dir)
        else:
            logger.warning(f"Prompts directory {prompts_dir} not found")
        
        logger.info(f"Returning {len(prompts)} prompts")
        return {"prompts": prompts, "defaults": defaults}
    except Exception as e:
        logger.error(f"Error getting prompts: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error getting prompts: {str(e)}")

@app.post("/api/prompts/{prompt_id}")
async def save_prompt(prompt_id: str, request: dict):
    try:
        content = request.get("content", "")
        # Derive the file path from the prompt_id, relative to project root
        prompts_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "prompts"))
        file_path = os.path.join(prompts_dir, prompt_id.replace('_', '/'))
        # Ensure the directory exists
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        # Write the content to the file
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        logger.info(f"Saved prompt {prompt_id} to {file_path}")
        # Return the updated prompt data
        prompt_name = os.path.basename(file_path).rsplit('.', 1)[0]
        prompt_type = os.path.dirname(file_path).replace(prompts_dir + '/', '') if prompts_dir in file_path else os.path.dirname(file_path)
        return {
            "id": prompt_id,
            "name": prompt_name,
            "type": prompt_type if prompt_type else "custom",
            "path": file_path.replace(prompts_dir + '/', '') if prompts_dir in file_path else file_path,
            "content": content
        }
    except Exception as e:
        logger.error(f"Error saving prompt {prompt_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error saving prompt: {str(e)}")

@app.post("/api/prompts/{prompt_id}/revert")
async def revert_prompt(prompt_id: str):
    try:
        prompts_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "prompts"))
        # Check if there is a default version of this prompt
        default_file_path = os.path.join(prompts_dir, "default", prompt_id.replace('_', '/'))
        if os.path.exists(default_file_path):
            with open(default_file_path, 'r', encoding='utf-8') as f:
                default_content = f.read()
            # Save the default content to the custom prompt location
            custom_file_path = os.path.join(prompts_dir, prompt_id.replace('_', '/'))
            os.makedirs(os.path.dirname(custom_file_path), exist_ok=True)
            with open(custom_file_path, 'w', encoding='utf-8') as f:
                f.write(default_content)
            logger.info(f"Reverted prompt {prompt_id} to default")
            prompt_name = os.path.basename(custom_file_path).rsplit('.', 1)[0]
            prompt_type = os.path.dirname(custom_file_path).replace(prompts_dir + '/', '') if prompts_dir in custom_file_path else os.path.dirname(custom_file_path)
            return {
                "id": prompt_id,
                "name": prompt_name,
                "type": prompt_type if prompt_type else "custom",
                "path": custom_file_path.replace(prompts_dir + '/', '') if prompts_dir in custom_file_path else custom_file_path,
                "content": default_content
            }
        else:
            logger.warning(f"No default found for prompt {prompt_id}")
            raise HTTPException(status_code=404, detail=f"No default prompt found for {prompt_id}")
    except Exception as e:
        logger.error(f"Error reverting prompt {prompt_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error reverting prompt: {str(e)}")

@app.get("/api/health")
async def health_check():
    """Health check endpoint for connection status monitoring"""
    try:
        # Check if we can connect to Ollama
        ollama_healthy = False
        try:
            ollama_check_url = config['ollama_endpoint'].replace('/api/generate', '/api/tags')
            response = requests.get(ollama_check_url, timeout=5)
            ollama_healthy = response.status_code == 200
        except:
            ollama_healthy = False
        
        return {
            "status": "healthy", 
            "backend": "connected",
            "ollama": "connected" if ollama_healthy else "disconnected",
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Error in health check: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={
                "status": "unhealthy", 
                "backend": "connected",
                "ollama": "unknown",
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }
        )

@app.post("/api/restart")
async def restart():
    try:
        logger.info("Restart request received")
        return {"status": "success", "message": "Restart initiated."}
    except Exception as e:
        logger.error(f"Error processing restart request: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error processing restart request: {str(e)}")

def cleanup_message_files():
    """Clean up all leftover message files including json_output, llm_response, planning and debug messages"""
    try:
        cleaned_files = []
        freed_space = 0
        
        # Look for message directories in data/messages/
        messages_dir = "data/messages"
        if os.path.exists(messages_dir):
            for chat_folder in os.listdir(messages_dir):
                chat_folder_path = os.path.join(messages_dir, chat_folder)
                if os.path.isdir(chat_folder_path):
                    # Look for leftover files in each chat folder
                    for file_pattern in ["json_output*", "llm_response*", "planning*", "debug*", "*.tmp", "*.log"]:
                        for filepath in glob.glob(os.path.join(chat_folder_path, file_pattern)):
                            if os.path.isfile(filepath):
                                try:
                                    file_size = os.path.getsize(filepath)
                                    os.remove(filepath)
                                    cleaned_files.append(filepath)
                                    freed_space += file_size
                                    logger.info(f"Removed leftover file: {filepath}")
                                except Exception as e:
                                    logger.error(f"Error removing file {filepath}: {str(e)}")
                    
                    # Remove empty chat folders
                    try:
                        if not os.listdir(chat_folder_path):
                            os.rmdir(chat_folder_path)
                            cleaned_files.append(f"Empty folder: {chat_folder_path}")
                            logger.info(f"Removed empty chat folder: {chat_folder_path}")
                    except Exception as e:
                        logger.error(f"Error removing empty folder {chat_folder_path}: {str(e)}")
        
        # Also clean up any leftover files in the main chat data directory
        if os.path.exists(CHAT_DATA_DIR):
            for file_pattern in ["json_output*", "llm_response*", "planning*", "debug*", "*.tmp", "*.log"]:
                for filepath in glob.glob(os.path.join(CHAT_DATA_DIR, file_pattern)):
                    if os.path.isfile(filepath):
                        try:
                            file_size = os.path.getsize(filepath)
                            os.remove(filepath)
                            cleaned_files.append(filepath)
                            freed_space += file_size
                            logger.info(f"Removed leftover file: {filepath}")
                        except Exception as e:
                            logger.error(f"Error removing file {filepath}: {str(e)}")
        
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

# Chat cleanup endpoints
@app.post("/api/chats/cleanup_messages")
async def cleanup_messages():
    """Clean up all leftover message files including json_output, llm_response, planning and debug messages"""
    try:
        result = cleanup_message_files()
        logger.info(f"Message cleanup completed: {result}")
        return result
    except Exception as e:
        logger.error(f"Error during message cleanup: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error during message cleanup: {str(e)}")

@app.post("/api/chats/cleanup_all")
async def cleanup_all_chat_data():
    """Clean up all chat data and message files completely"""
    try:
        cleaned_files = []
        freed_space = 0
        
        # First run the message file cleanup
        message_cleanup_result = cleanup_message_files()
        if message_cleanup_result["status"] == "success":
            cleaned_files.extend(message_cleanup_result["cleaned_files"])
            freed_space += message_cleanup_result["freed_space_bytes"]
        
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

# Import knowledge base
try:
    from src.knowledge_base import KnowledgeBase
    knowledge_base = None  # Will be initialized after server starts
    logger.info("KnowledgeBase class imported successfully")
except ImportError as e:
    logger.error(f"Failed to import KnowledgeBase: {str(e)}")
    knowledge_base = None

# Initialize knowledge base
async def init_knowledge_base():
    global knowledge_base
    if knowledge_base is None:
        try:
            knowledge_base = KnowledgeBase()
            await knowledge_base.ainit()
            logger.info("Knowledge base initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize knowledge base: {str(e)}")
            knowledge_base = None

# Knowledge base endpoints
@app.post("/api/knowledge/search")
async def search_knowledge(request: dict):
    """Search knowledge base"""
    try:
        if knowledge_base is None:
            await init_knowledge_base()
        
        if knowledge_base is None:
            return {
                "results": [],
                "message": "Knowledge base not available",
                "query": request.get('query', ''),
                "limit": request.get('limit', 10)
            }
        
        query = request.get('query', '')
        limit = request.get('limit', 10)
        
        logger.info(f"Knowledge search request: {query} (limit: {limit})")
        
        results = await knowledge_base.search(query, limit)
        
        return {
            "results": results,
            "query": query,
            "limit": limit,
            "total_results": len(results)
        }
    except Exception as e:
        logger.error(f"Error in knowledge search: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error in knowledge search: {str(e)}")

@app.post("/api/knowledge/add_text")
async def add_text_to_knowledge(request: dict):
    """Add text to knowledge base"""
    try:
        if knowledge_base is None:
            await init_knowledge_base()
        
        if knowledge_base is None:
            raise HTTPException(status_code=503, detail="Knowledge base not available")
        
        text = request.get('text', '')
        title = request.get('title', '')
        source = request.get('source', 'Manual Entry')
        
        if not text.strip():
            raise HTTPException(status_code=400, detail="Text content is required")
        
        logger.info(f"Knowledge add text request: {title} ({len(text)} chars)")
        
        metadata = {
            "title": title,
            "source": source,
            "type": "text",
            "content_type": "manual_entry"
        }
        
        result = await knowledge_base.store_fact(text, metadata)
        
        return {
            "status": result.get("status"),
            "message": result.get("message", "Text added to knowledge base successfully"),
            "fact_id": result.get("fact_id"),
            "text_length": len(text),
            "title": title,
            "source": source
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error adding text to knowledge: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error adding text to knowledge: {str(e)}")

@app.post("/api/knowledge/add_url")
async def add_url_to_knowledge(request: dict):
    """Add URL to knowledge base"""
    try:
        if knowledge_base is None:
            await init_knowledge_base()
        
        if knowledge_base is None:
            raise HTTPException(status_code=503, detail="Knowledge base not available")
        
        url = request.get('url', '')
        method = request.get('method', 'fetch')
        
        if not url.strip():
            raise HTTPException(status_code=400, detail="URL is required")
        
        logger.info(f"Knowledge add URL request: {url} (method: {method})")
        
        if method == 'fetch':
            # For now, store as reference - actual fetching would require additional implementation
            metadata = {
                "url": url,
                "source": "URL",
                "type": "url_reference",
                "method": method,
                "content_type": "url"
            }
            
            content = f"URL Reference: {url}"
            result = await knowledge_base.store_fact(content, metadata)
            
            return {
                "status": result.get("status"),
                "message": result.get("message", "URL reference added to knowledge base"),
                "fact_id": result.get("fact_id"),
                "url": url,
                "method": method
            }
        else:
            # Store as reference only
            metadata = {
                "url": url,
                "source": "URL Reference",
                "type": "url_reference",
                "method": method,
                "content_type": "url"
            }
            
            content = f"URL Reference: {url}"
            result = await knowledge_base.store_fact(content, metadata)
            
            return {
                "status": result.get("status"),
                "message": result.get("message", "URL reference stored successfully"),
                "fact_id": result.get("fact_id"),
                "url": url,
                "method": method
            }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error adding URL to knowledge: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error adding URL to knowledge: {str(e)}")

from fastapi import UploadFile, File
import tempfile
import os as os_module

@app.post("/api/knowledge/add_file")
async def add_file_to_knowledge(file: UploadFile = File(...)):
    """Add file to knowledge base"""
    try:
        if knowledge_base is None:
            await init_knowledge_base()
        
        if knowledge_base is None:
            raise HTTPException(status_code=503, detail="Knowledge base not available")
        
        logger.info(f"Knowledge add file request: {file.filename} ({file.content_type})")
        
        # Get file extension
        file_ext = os_module.path.splitext(file.filename)[1].lower()
        supported_extensions = ['.txt', '.pdf', '.csv', '.docx', '.md']
        
        if file_ext not in supported_extensions:
            raise HTTPException(
                status_code=400, 
                detail=f"Unsupported file type: {file_ext}. Supported types: {', '.join(supported_extensions)}"
            )
        
        # Create temporary file
        with tempfile.NamedTemporaryFile(delete=False, suffix=file_ext) as temp_file:
            content = await file.read()
            temp_file.write(content)
            temp_file_path = temp_file.name
        
        try:
            # Determine file type
            file_type = file_ext[1:]  # Remove the dot
            
            # Add file to knowledge base
            metadata = {
                "filename": file.filename,
                "content_type": file.content_type,
                "file_size": len(content),
                "source": "File Upload",
                "type": "document"
            }
            
            result = await knowledge_base.add_file(temp_file_path, file_type, metadata)
            
            return {
                "status": result.get("status"),
                "message": result.get("message", "File added to knowledge base successfully"),
                "filename": file.filename,
                "file_type": file_type,
                "file_size": len(content)
            }
        finally:
            # Clean up temporary file
            try:
                os_module.unlink(temp_file_path)
            except Exception as cleanup_error:
                logger.warning(f"Failed to clean up temporary file {temp_file_path}: {cleanup_error}")
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error adding file to knowledge: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error adding file to knowledge: {str(e)}")

@app.get("/api/knowledge/export")
async def export_knowledge():
    """Export knowledge base"""
    try:
        if knowledge_base is None:
            await init_knowledge_base()
        
        if knowledge_base is None:
            return JSONResponse(
                content={"message": "Knowledge base not available"},
                media_type="application/json"
            )
        
        logger.info("Knowledge export request")
        
        # Get all facts and data
        export_data = await knowledge_base.export_all_data()
        
        # Create export object with metadata
        export_object = {
            "export_timestamp": datetime.now().isoformat(),
            "total_entries": len(export_data),
            "version": "1.0",
            "data": export_data
        }
        
        return JSONResponse(
            content=export_object,
            media_type="application/json"
        )
    except Exception as e:
        logger.error(f"Error exporting knowledge: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error exporting knowledge: {str(e)}")

@app.post("/api/knowledge/cleanup")
async def cleanup_knowledge():
    """Cleanup knowledge base"""
    try:
        if knowledge_base is None:
            await init_knowledge_base()
        
        if knowledge_base is None:
            raise HTTPException(status_code=503, detail="Knowledge base not available")
        
        logger.info("Knowledge cleanup request")
        
        # Default to 30 days cleanup
        days_to_keep = 30
        result = await knowledge_base.cleanup_old_entries(days_to_keep)
        
        return {
            "status": result.get("status"),
            "message": result.get("message", "Knowledge base cleanup completed"),
            "removed_count": result.get("removed_count", 0),
            "days_kept": days_to_keep
        }
    except Exception as e:
        logger.error(f"Error cleaning up knowledge: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error cleaning up knowledge: {str(e)}")

@app.get("/api/knowledge/stats")
async def get_knowledge_stats():
    """Get knowledge base statistics"""
    try:
        if knowledge_base is None:
            await init_knowledge_base()
        
        if knowledge_base is None:
            return {
                "total_facts": 0,
                "total_documents": 0,
                "total_vectors": 0,
                "db_size": 0,
                "message": "Knowledge base not available"
            }
        
        logger.info("Knowledge stats request")
        
        stats = await knowledge_base.get_stats()
        
        return stats
    except Exception as e:
        logger.error(f"Error getting knowledge stats: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error getting knowledge stats: {str(e)}")

@app.get("/api/knowledge/detailed_stats")
async def get_detailed_knowledge_stats():
    """Get detailed knowledge base statistics"""
    try:
        if knowledge_base is None:
            await init_knowledge_base()
        
        if knowledge_base is None:
            return {
                "message": "Knowledge base not available",
                "implementation_status": "unavailable"
            }
        
        logger.info("Detailed knowledge stats request")
        
        detailed_stats = await knowledge_base.get_detailed_stats()
        
        return detailed_stats
    except Exception as e:
        logger.error(f"Error getting detailed knowledge stats: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error getting detailed knowledge stats: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    logger.info(f"Starting FastAPI server on {config['server_host']}:{config['server_port']}")
    uvicorn.run(app, host=config['server_host'], port=config['server_port'])
