from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import os
import json
import yaml
from datetime import datetime, timedelta
import requests
import logging
import uuid
from functools import lru_cache

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Simple TTL Cache implementation for performance optimization
class TTLCache:
    def __init__(self, ttl_seconds=300):  # 5 minute default TTL
        self.cache = {}
        self.ttl = ttl_seconds
    
    def get(self, key):
        if key in self.cache:
            value, timestamp = self.cache[key]
            if datetime.now() - timestamp < timedelta(seconds=self.ttl):
                return value
            else:
                del self.cache[key]
        return None
    
    def set(self, key, value):
        self.cache[key] = (value, datetime.now())
    
    def clear(self):
        self.cache.clear()

# Global cache instances
settings_cache = TTLCache(ttl_seconds=300)  # 5 minutes
prompts_cache = TTLCache(ttl_seconds=600)   # 10 minutes

# Import ChatHistoryManager and ChatAPI
import sys
import os
import shutil
import glob
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from src.chat_history_manager import ChatHistoryManager
from src.config import global_config_manager
from backend.chat_api import ChatAPI

app = FastAPI()

# Initialize chat history manager with Redis support from config
redis_config = global_config_manager.get_nested('memory.redis', {})
use_redis = redis_config.get('enabled', False)
redis_host = redis_config.get('host', 'localhost')
redis_port = redis_config.get('port', 6379)

chat_history_manager = ChatHistoryManager(use_redis=use_redis, redis_host=redis_host, redis_port=redis_port)
logger.info(f"ChatHistoryManager initialized: use_redis={use_redis}, host={redis_host}, port={redis_port}")

# Initialize ChatAPI
chat_api = ChatAPI(chat_data_dir=global_config_manager.get_nested('backend.chat_data_dir', 'data/chats'))

# Initialize app state for health checks
@app.on_event("startup")
async def startup_event():
    """Initialize application state on startup"""
    # Initialize empty state objects to prevent health check errors
    app.state.chat_history_manager = chat_history_manager
    logger.info(f"DEBUG: ChatHistoryManager in app.state: {app.state.chat_history_manager is not None}")
    
    # Initialize orchestrator
    try:
        from src.orchestrator import Orchestrator
        app.state.orchestrator = Orchestrator()
        await app.state.orchestrator.startup()
        logger.info("Orchestrator initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize orchestrator: {str(e)}")
        app.state.orchestrator = None
    
    # Initialize diagnostics
    try:
        from src.diagnostics import Diagnostics
        app.state.diagnostics = Diagnostics()
        logger.info("Diagnostics initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize diagnostics: {str(e)}")
        app.state.diagnostics = None
    
    logger.info("Application startup completed - app.state initialized")
    
    # Initialize knowledge base on startup
    await init_knowledge_base()

# Configure CORS
cors_origins = global_config_manager.get_nested('backend.cors_origins', ['http://localhost:5173'])
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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

def _stream_response(response):
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
                return StreamingResponse(_stream_response(response), media_type="text/event-stream")
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

# Old /api/chat endpoint removed - now using /api/chats/{chat_id}/message for better organization
# This ensures all messages are properly associated with specific chats and automatically saved

# Chat endpoints are now handled by the chat router included at the bottom

# Path for settings file
SETTINGS_FILE = "config/settings.json"

class Settings(BaseModel):
    settings: dict

# Settings endpoints moved to backend/api/settings.py router

# Redis Configuration API Endpoints
@app.get("/api/redis/config")
async def get_redis_config():
    """Get current Redis configuration"""
    try:
        task_transport_config = global_config_manager.get('task_transport', {})
        redis_config = task_transport_config.get('redis', {})
        
        return {
            "type": task_transport_config.get('type', 'local'),
            "host": redis_config.get('host', 'localhost'),
            "port": redis_config.get('port', 6379),
            "channels": redis_config.get('channels', {}),
            "priority": redis_config.get('priority', 10)
        }
    except Exception as e:
        logger.error(f"Error getting Redis config: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error getting Redis config: {str(e)}")

@app.post("/api/redis/config")
async def update_redis_config(config_data: dict):
    """Update Redis configuration"""
    try:
        # Load current config
        current_config = global_config_manager.to_dict()
        
        # Update task transport configuration
        if 'task_transport' not in current_config:
            current_config['task_transport'] = {}
        
        # Update transport type
        if 'type' in config_data:
            current_config['task_transport']['type'] = config_data['type']
        
        # Update Redis-specific settings
        if 'task_transport' not in current_config:
            current_config['task_transport'] = {}
        if 'redis' not in current_config['task_transport']:
            current_config['task_transport']['redis'] = {}
            
        redis_config = current_config['task_transport']['redis']
        
        if 'host' in config_data:
            redis_config['host'] = config_data['host']
        if 'port' in config_data:
            redis_config['port'] = int(config_data['port'])
        if 'channels' in config_data:
            redis_config['channels'] = config_data['channels']
        if 'priority' in config_data:
            redis_config['priority'] = int(config_data['priority'])
        
        # Save updated config to file
        config_file_path = 'config/config.yaml'
        os.makedirs(os.path.dirname(config_file_path), exist_ok=True)
        with open(config_file_path, 'w') as f:
            yaml.dump(current_config, f, default_flow_style=False)
        
        # Reload the global config manager
        global_config_manager.reload()
        
        logger.info(f"Updated Redis configuration: {config_data}")
        return {"status": "success", "message": "Redis configuration updated successfully"}
    except Exception as e:
        logger.error(f"Error updating Redis config: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error updating Redis config: {str(e)}")

@app.post("/api/redis/test_connection")
async def test_redis_connection():
    """Test Redis connection with current configuration"""
    try:
        import redis
        task_transport_config = global_config_manager.get('task_transport', {})
        
        if task_transport_config.get('type') != 'redis':
            return {
                "status": "not_configured",
                "message": "Redis transport is not configured (type is not 'redis')"
            }
        
        redis_config = task_transport_config.get('redis', {})
        redis_host = redis_config.get('host', 'localhost')
        redis_port = redis_config.get('port', 6379)
        
        redis_client = redis.Redis(host=redis_host, port=redis_port, decode_responses=True)
        redis_client.ping()
        
        # Check if RediSearch module is loaded
        redis_search_module_loaded = False
        try:
            modules = redis_client.module_list()
            redis_search_module_loaded = any(module[b'name'] == b'search' or module.get('name') == 'search' for module in modules)
        except:
            redis_search_module_loaded = False
        
        return {
            "status": "connected",
            "message": f"Successfully connected to Redis at {redis_host}:{redis_port}",
            "host": redis_host,
            "port": redis_port,
            "redis_search_module_loaded": redis_search_module_loaded
        }
    except Exception as e:
        logger.error(f"Redis connection test failed: {str(e)}")
        return {
            "status": "disconnected",
            "message": f"Failed to connect to Redis: {str(e)}"
        }

# LLM endpoints moved to backend/api/llm.py router

# Prompts endpoints moved to backend/api/prompts.py router

# Health and restart endpoints moved to backend/api/system.py router

def cleanup_message_files():
    """Clean up all leftover message files including json_output, llm_response, planning, debug and utility messages"""
    try:
        cleaned_files = []
        freed_space = 0
        
        # Comprehensive file patterns to catch all types of leftover files
        file_patterns = [
            # Core message types mentioned in the issue
            "json_output*", "llm_response*", "planning*", "debug*",
            # Utility and orchestrator files
            "*_utility*", "utility_*", "*_orchestrator*", "orchestrator_*",
            # Response and output variations
            "*_response*", "*_output*", "*_debug*", "*_planning*",
            "response_*", "output_*", "debug_*", "planning_*",
            # Temporary and cache files
            "*.tmp", "*.log", "*.cache", "*.bak", "*.temp",
            # LLM and AI related files
            "*_llm*", "llm_*", "*_ai*", "ai_*", "*_model*", "model_*",
            # Session and task files
            "*_session*", "session_*", "*_task*", "task_*",
            # Memory and state files
            "*_memory*", "memory_*", "*_state*", "state_*",
            # Processing and analysis files
            "*_analysis*", "analysis_*", "*_processing*", "processing_*",
            # Catch all JSON and text files (but preserve legitimate chat files)
            "*.txt", "*.json"
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

# Import knowledge base
KnowledgeBase = None
knowledge_base = None

try:
    from src.knowledge_base import KnowledgeBase
    knowledge_base = None  # Will be initialized after server starts
    logger.info("KnowledgeBase class imported successfully")
except ImportError as e:
    logger.error(f"Failed to import KnowledgeBase: {str(e)}")
    KnowledgeBase = None
    knowledge_base = None

# Initialize knowledge base
async def init_knowledge_base():
    global knowledge_base
    if knowledge_base is None and KnowledgeBase is not None:
        try:
            knowledge_base = KnowledgeBase()
            await knowledge_base.ainit()
            logger.info("Knowledge base initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize knowledge base: {str(e)}")
            knowledge_base = None

# Knowledge base endpoints moved to backend/api/knowledge.py router

# Include API routers
from backend.api import chat as chat_router
from backend.api import system as system_router
from backend.api import settings as settings_router
from backend.api import prompts as prompts_router
from backend.api import knowledge as knowledge_router
from backend.api import llm as llm_router

app.include_router(chat_router.router, prefix="/api", tags=["chat"])
app.include_router(system_router.router, prefix="/api/system", tags=["system"])
app.include_router(settings_router.router, prefix="/api/settings", tags=["settings"])
app.include_router(prompts_router.router, prefix="/api/prompts", tags=["prompts"])
app.include_router(knowledge_router.router, prefix="/api/knowledge", tags=["knowledge"])
app.include_router(llm_router.router, prefix="/api/llm", tags=["llm"])

if __name__ == "__main__":
    import uvicorn
    server_host = global_config_manager.get_nested('backend.server_host', '0.0.0.0')
    server_port = global_config_manager.get_nested('backend.server_port', 8001)
    logger.info(f"Starting FastAPI server on {server_host}:{server_port}")
    uvicorn.run(app, host=server_host, port=server_port)
