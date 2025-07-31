from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import os
import json
import uuid
import time
import logging
import traceback
import glob
import shutil

router = APIRouter()

logger = logging.getLogger(__name__)

class ChatMessage(BaseModel):
    message: str

class ChatSave(BaseModel):
    messages: list

@router.post("/chats/new")
async def create_new_chat(request: Request):
    """Create a new chat session ID (POST method)."""
    try:
        # Try to get chat_history_manager from app.state
        chat_history_manager = getattr(request.app.state, 'chat_history_manager', None)
        
        if chat_history_manager is None:
            logging.error("chat_history_manager not found in app.state")
            return JSONResponse(status_code=500, content={"error": "Chat history manager not initialized"})
        
        chat_id = str(uuid.uuid4())
        # Create initial message for new chat
        initial_message = {
            "sender": "bot",
            "text": "Hello! How can I assist you today?",
            "messageType": "response",
            "rawData": None,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
        }
        chat_history_manager.save_session(chat_id, messages=[initial_message], name=f"Chat {chat_id[:8]}")
        return JSONResponse(status_code=200, content={"chatId": chat_id, "status": "success"})
    except Exception as e:
        logging.error(f"Error creating new chat: {str(e)}")
        logging.error(f"Traceback: {traceback.format_exc()}")
        return JSONResponse(status_code=500, content={"error": f"Error creating new chat: {str(e)}"})

@router.get("/chats")
async def list_chats(request: Request):
    """List all available chat sessions."""
    try:
        chat_history_manager = getattr(request.app.state, 'chat_history_manager', None)
        if chat_history_manager is None:
            logging.error("chat_history_manager not found in app.state")
            return JSONResponse(status_code=500, content={"error": "Chat history manager not initialized"})
        
        sessions = chat_history_manager.list_sessions()
        return JSONResponse(status_code=200, content={"chats": sessions})
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

@router.get("/chats/{chat_id}")
async def get_chat(chat_id: str, request: Request):
    """Get a specific chat session."""
    try:
        chat_history_manager = getattr(request.app.state, 'chat_history_manager', None)
        if chat_history_manager is None:
            logging.error("chat_history_manager not found in app.state")
            return JSONResponse(status_code=500, content={"error": "Chat history manager not initialized"})
        
        history = chat_history_manager.load_session(chat_id)
        if history is not None:
            return JSONResponse(status_code=200, content={"chat_id": chat_id, "history": history})
        else:
            return JSONResponse(status_code=404, content={"error": "Chat not found"})
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

@router.delete("/chats/{chat_id}")
async def delete_chat(chat_id: str, request: Request):
    """Delete a specific chat session."""
    chat_history_manager = request.app.state.chat_history_manager
    try:
        if chat_history_manager.delete_session(chat_id):
            return JSONResponse(status_code=200, content={"message": "Chat deleted successfully"})
        else:
            return JSONResponse(status_code=404, content={"error": "Chat not found"})
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

@router.post("/chats/{chat_id}")
async def save_chat_messages(chat_id: str, messages: list, request: Request):
    """Save messages for a specific chat session."""
    chat_history_manager = request.app.state.chat_history_manager
    try:
        chat_history_manager.save_session(chat_id, messages=messages)
        return JSONResponse(status_code=200, content={"status": "success"})
    except Exception as e:
        logger.error(f"Error saving chat messages for {chat_id}: {str(e)}")
        return JSONResponse(status_code=500, content={"error": f"Error saving chat messages: {str(e)}"})

@router.post("/chats/{chat_id}/save")
async def save_chat(chat_id: str, chat_data: ChatSave, request: Request):
    """Save chat data for a specific session."""
    chat_history_manager = request.app.state.chat_history_manager
    try:
        chat_history_manager.save_session(chat_id, messages=chat_data.messages)
        return JSONResponse(status_code=200, content={"status": "success"})
    except Exception as e:
        logger.error(f"Error saving chat data for {chat_id}: {str(e)}")
        return JSONResponse(status_code=500, content={"error": f"Error saving chat: {str(e)}"})

@router.post("/chats/{chat_id}/reset")
async def reset_chat(chat_id: str, request: Request):
    """Reset a specific chat session."""
    chat_history_manager = request.app.state.chat_history_manager
    try:
        initial_message = {
            "sender": "bot",
            "text": "Hello! How can I assist you today?",
            "messageType": "response",
            "rawData": None,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
        }
        chat_history_manager.save_session(chat_id, messages=[initial_message])
        return JSONResponse(status_code=200, content={"status": "success"})
    except Exception as e:
        logger.error(f"Error resetting chat {chat_id}: {str(e)}")
        return JSONResponse(status_code=500, content={"error": f"Error resetting chat: {str(e)}"})

@router.post("/chats/{chat_id}/message")
async def send_chat_message(chat_id: str, chat_message: ChatMessage, request: Request):
    """Send a message to a specific chat and get a response."""
    try:
        # Get the orchestrator and chat_history_manager from app state
        orchestrator = getattr(request.app.state, 'orchestrator', None)
        chat_history_manager = getattr(request.app.state, 'chat_history_manager', None)
        
        if orchestrator is None:
            logging.error("orchestrator not found in app.state")
            return JSONResponse(status_code=500, content={"error": "Orchestrator not initialized"})
        
        if chat_history_manager is None:
            logging.error("chat_history_manager not found in app.state")
            return JSONResponse(status_code=500, content={"error": "Chat history manager not initialized"})
        
        message = chat_message.message
        logging.info(f"Received chat message for chat {chat_id}: {message}")
        
        # Add user message to chat history
        user_message = {
            "sender": "user",
            "text": message,
            "messageType": "user",
            "rawData": None,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
        }
        
        # Load existing chat history
        existing_history = chat_history_manager.load_session(chat_id) or []
        existing_history.append(user_message)
        
        # Execute the goal using the orchestrator
        orchestrator_result = await orchestrator.execute_goal(message, [{"role": "user", "content": message}])
        
        # Process the result similar to the /goal endpoint
        if isinstance(orchestrator_result, dict):
            result_dict = orchestrator_result
        else:
            result_dict = {"message": str(orchestrator_result)}

        response_message = "An unexpected response format was received."
        tool_name = result_dict.get("tool_name")
        tool_args = result_dict.get("tool_args", {})
        
        # Ensure tool_args is a dictionary
        if not isinstance(tool_args, dict):
            tool_args = {}
        
        if tool_name == "respond_conversationally":
            response_message = result_dict.get("response_text") or tool_args.get("response_text", "No response text provided.")
        elif tool_name == "execute_system_command":
            command_output = tool_args.get("output", "")
            command_error = tool_args.get("error", "")
            command_status = tool_args.get("status", "unknown")
            
            if command_status == "success":
                response_message = f"Command executed successfully.\nOutput:\n{command_output}"
            else:
                response_message = f"Command failed ({command_status}).\nError:\n{command_error}\nOutput:\n{command_output}"
        elif tool_name:
            tool_output_content = tool_args.get("output", tool_args.get("message", str(tool_args)))
            response_message = f"Tool Used: {tool_name}\nOutput: {tool_output_content}"
        elif result_dict.get("output"):
            response_message = result_dict["output"]
        elif result_dict.get("message"):
            response_message = result_dict["message"]
        else:
            response_message = str(result_dict)
        
        # Add bot response to chat history
        bot_message = {
            "sender": "bot",
            "text": response_message,
            "messageType": "response",
            "rawData": result_dict,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
        }
        existing_history.append(bot_message)
        
        # Save updated chat history
        chat_history_manager.save_session(chat_id, messages=existing_history)
        
        return JSONResponse(status_code=200, content={
            "response": response_message, 
            "status": "success",
            "chat_id": chat_id,
            "message_count": len(existing_history)
        })
        
    except Exception as e:
        logging.error(f"Error processing chat message for {chat_id}: {str(e)}")
        logging.error(f"Traceback: {traceback.format_exc()}")
        return JSONResponse(status_code=500, content={"error": f"Error processing message: {str(e)}"})

@router.post("/chats/cleanup_messages")
async def cleanup_messages():
    """Clean up all leftover message files including json_output, llm_response, planning and debug messages"""
    try:
        cleaned_files = []
        freed_space = 0
        
        # Enhanced file patterns to catch ALL leftover files mentioned in the task
        file_patterns = [
            # Specific patterns mentioned in the task
            "json_output*", "llm_response*", "planning*", "debug*",
            
            # Variations and related patterns
            "*json_output*", "*llm_response*", "*planning*", "*debug*",
            "json_output", "llm_response", "planning", "debug",
            
            # Common temporary and output files
            "*.tmp", "*.log", "*.cache", "*.bak", "*.out",
            "*_response*", "*_output*", "*_debug*", "*_planning*",
            "response_*", "output_*", "debug_*", "planning_*",
            
            # Chat-related temporary files
            "chat_temp*", "temp_*", "*.temp",
            
            # Any .txt files that match leftover patterns
            "*.txt"  # Will be filtered to exclude legitimate chat files
        ]
        
        # Specific patterns found in search results
        specific_patterns = [
            "*_json_output.json", "*_planning_debug.json", "*_llm_response.json",
            "*_planning*.json", "*_debug*.json", "*_output*.json"
        ]
        
        # ONLY scan data/messages/ directory - NEVER touch prompts/ or other system directories
        messages_dir = "data/messages"
        if os.path.exists(messages_dir):
            logging.info(f"Scanning messages directory: {messages_dir}")
            for chat_folder in os.listdir(messages_dir):
                chat_folder_path = os.path.join(messages_dir, chat_folder)
                if os.path.isdir(chat_folder_path):
                    logging.info(f"Processing chat folder: {chat_folder_path}")
                    folder_cleaned = False
                    
                    # Look for leftover files in each chat folder - ONLY in data/messages/
                    for file_pattern in file_patterns:
                        for filepath in glob.glob(os.path.join(chat_folder_path, file_pattern)):
                            if os.path.isfile(filepath):
                                filename = os.path.basename(filepath)
                                
                                # SAFETY CHECK: Only process files in data/messages/ directory
                                if not filepath.startswith("data/messages/"):
                                    continue
                                
                                # Special handling for .txt files - only remove if they match leftover patterns
                                if filename.endswith('.txt'):
                                    # Only remove .txt files that match leftover patterns
                                    if any(pattern in filename.lower() for pattern in ['json_output', 'llm_response', 'planning', 'debug', 'temp']):
                                        pass  # Will be removed
                                    else:
                                        continue  # Skip legitimate .txt files
                                
                                try:
                                    file_size = os.path.getsize(filepath)
                                    os.remove(filepath)
                                    cleaned_files.append(filepath)
                                    freed_space += file_size
                                    folder_cleaned = True
                                    logging.info(f"Removed leftover file: {filepath}")
                                except Exception as e:
                                    logging.error(f"Error removing file {filepath}: {str(e)}")
                    
                    # Also check for any files with specific names mentioned in the task
                    specific_leftover_files = ['json_output', 'llm_response', 'planning', 'debug']
                    for specific_file in specific_leftover_files:
                        specific_filepath = os.path.join(chat_folder_path, specific_file)
                        if os.path.exists(specific_filepath):
                            try:
                                if os.path.isfile(specific_filepath):
                                    file_size = os.path.getsize(specific_filepath)
                                    os.remove(specific_filepath)
                                    cleaned_files.append(specific_filepath)
                                    freed_space += file_size
                                    folder_cleaned = True
                                    logging.info(f"Removed specific leftover file: {specific_filepath}")
                                elif os.path.isdir(specific_filepath):
                                    # Remove entire leftover directory
                                    dir_size = sum(os.path.getsize(os.path.join(dirpath, filename))
                                                  for dirpath, dirnames, filenames in os.walk(specific_filepath)
                                                  for filename in filenames)
                                    shutil.rmtree(specific_filepath)
                                    cleaned_files.append(f"Removed leftover directory: {specific_filepath}")
                                    freed_space += dir_size
                                    folder_cleaned = True
                                    logging.info(f"Removed leftover directory: {specific_filepath}")
                            except Exception as e:
                                logging.error(f"Error removing specific leftover file/dir {specific_filepath}: {str(e)}")
                    
                    # Scan for specific patterns found in search results
                    for pattern in specific_patterns:
                        for filepath in glob.glob(os.path.join(chat_folder_path, pattern)):
                            if os.path.isfile(filepath):
                                try:
                                    file_size = os.path.getsize(filepath)
                                    os.remove(filepath)
                                    cleaned_files.append(filepath)
                                    freed_space += file_size
                                    folder_cleaned = True
                                    logging.info(f"Removed specific pattern file: {filepath}")
                                except Exception as e:
                                    logging.error(f"Error removing specific pattern file {filepath}: {str(e)}")
                    
                    # Remove empty chat folders or folders that only contained leftover files
                    try:
                        remaining_files = os.listdir(chat_folder_path)
                        if not remaining_files:
                            os.rmdir(chat_folder_path)
                            cleaned_files.append(f"Empty folder: {chat_folder_path}")
                            logging.info(f"Removed empty chat folder: {chat_folder_path}")
                        elif folder_cleaned:
                            logging.info(f"Cleaned files from chat folder: {chat_folder_path}, remaining files: {remaining_files}")
                    except Exception as e:
                        logging.error(f"Error removing empty folder {chat_folder_path}: {str(e)}")
        
        # Also clean up any leftover files in the main chat data directory
        chat_data_dir = "data/chats"
        if os.path.exists(chat_data_dir):
            logging.info(f"Scanning main chat data directory: {chat_data_dir}")
            for file_pattern in file_patterns:
                for filepath in glob.glob(os.path.join(chat_data_dir, file_pattern)):
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
                            logging.info(f"Removed leftover file: {filepath}")
                        except Exception as e:
                            logging.error(f"Error removing file {filepath}: {str(e)}")
        
        message = f"Cleaned up {len(cleaned_files)} leftover files" if cleaned_files else "No leftover files found to clean up"
        logging.info(f"Cleanup completed: {message}")
        
        return {
            "status": "success",
            "message": message,
            "cleaned_files": cleaned_files,
            "freed_space_bytes": freed_space
        }
        
    except Exception as e:
        logging.error(f"Error during cleanup: {str(e)}")
        return JSONResponse(status_code=500, content={"error": f"Error during cleanup: {str(e)}"})
