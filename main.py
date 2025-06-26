from fastapi import FastAPI, WebSocket, WebSocketDisconnect, UploadFile, File, Form, Query # Removed Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
import os
import uvicorn
import yaml
import json
import asyncio
import subprocess
import logging # Import logging
import logging.config # Import logging.config
from typing import Optional, Dict, Any, List
from pydantic import BaseModel

class GoalPayload(BaseModel):
    goal: str
    use_phi2: bool = False
    user_role: str = "user"

from src.orchestrator import Orchestrator
from src.event_manager import event_manager
from src.knowledge_base import KnowledgeBase
from src.diagnostics import Diagnostics # Import Diagnostics
from src.security_layer import SecurityLayer # Import SecurityLayer
from src.voice_interface import VoiceInterface # Import VoiceInterface
from src.chat_history_manager import ChatHistoryManager # Import ChatHistoryManager

def _ensure_config_exists():
    """Ensures config.yaml exists, copying from template if necessary."""
    config_path = "config/config.yaml"
    template_path = "config/config.yaml.template"
    if not os.path.exists(config_path):
        print("config/config.yaml not found. Copying from template.")
        os.makedirs(os.path.dirname(config_path), exist_ok=True)
        if os.path.exists(template_path):
            with open(template_path, 'r') as f_template:
                with open(config_path, 'w') as f_config:
                    f_config.write(f_template.read())
            print("config/config.yaml created from template.")
        else:
            print(f"Error: Config template not found at {template_path}. Cannot create config.yaml.")

_ensure_config_exists() # Call this function at the very beginning

app = FastAPI()

# Initialize the Orchestrator and KnowledgeBase
orchestrator = Orchestrator()
knowledge_base = KnowledgeBase()
diagnostics = Diagnostics() # Initialize Diagnostics for direct API access if needed
voice_interface = VoiceInterface() # Initialize VoiceInterface
security_layer = SecurityLayer() # Initialize SecurityLayer
chat_history_manager = ChatHistoryManager() # Initialize ChatHistoryManager

# Create a separate router for API endpoints
api_router = FastAPI(title="AutoBot API")
app.mount("/api", api_router)

# WebSocket endpoint for real-time event stream
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    print(f"WebSocket connected from client: {websocket.client}")
    print(f"Requested WebSocket path: {websocket.scope['path']}")
    print(f"WebSocket connection type: {websocket.scope['type']}")

    async def broadcast_event(event_data: dict):
        try:
            await websocket.send_json(event_data)
            
            # Add event to chat history manager
            sender = "system"
            text = ""
            message_type = event_data.get("type", "default")
            raw_data = event_data.get("payload", {}) # Provide empty dict as default

            if message_type == 'goal_received':
                text = f"Goal received: \"{raw_data.get('goal', 'N/A')}\""
            elif message_type == 'plan_ready':
                text = f"Here is the plan:\n{raw_data.get('llm_response', 'No plan text available.')}"
                sender = "bot"
            elif message_type == 'goal_completed':
                text = f"Goal completed. Result: {json.dumps(raw_data.get('results', {}), indent=2)}"
            elif message_type == 'command_execution_start':
                text = f"Executing command: {raw_data.get('command', 'N/A')}"
            elif message_type == 'command_execution_end':
                status = raw_data.get('status', 'N/A')
                output = raw_data.get('output', '')
                error = raw_data.get('error', '')
                text = f"Command finished ({status}). Output: {output or error}"
            elif message_type == 'error':
                text = f"Error: {raw_data.get('message', 'Unknown error')}"
                sender = "error"
            elif message_type == 'progress':
                text = f"Progress: {raw_data.get('message', 'N/A')}"
            elif message_type == 'llm_response':
                text = raw_data.get('response', 'N/A')
                sender = "bot"
            elif message_type == 'user_message':
                text = raw_data.get('message', 'N/A')
                sender = "user"
            elif message_type == 'thought':
                text = json.dumps(raw_data.get('thought', {}), indent=2)
                sender = "thought"
            elif message_type == 'tool_code':
                text = raw_data.get('code', 'N/A')
                sender = "tool-code"
            elif message_type == 'tool_output':
                text = raw_data.get('output', 'N/A')
                sender = "tool-output"
            elif message_type == 'settings_updated':
                text = "Settings updated successfully."
            elif message_type == 'file_uploaded':
                text = f"File uploaded: {raw_data.get('filename', 'N/A')}"
            elif message_type == 'knowledge_base_update':
                text = f"Knowledge Base updated: {raw_data.get('type', 'N/A')}"
            elif message_type == 'llm_status':
                status = raw_data.get('status', 'N/A')
                model = raw_data.get('model', 'N/A')
                message = raw_data.get('message', '')
                text = f"LLM ({model}) connection {status}. {message}"
                if status == 'disconnected':
                    sender = "error"
            elif message_type == 'diagnostics_report':
                text = f"Diagnostics Report: {json.dumps(raw_data, indent=2)}"
            elif message_type == 'user_permission_request':
                text = f"User Permission Request: {json.dumps(raw_data, indent=2)}"
            
            if text: # Only add messages with content
                chat_history_manager.add_message(sender, text, message_type, raw_data)

        except RuntimeError as e:
            print(f"Error sending to WebSocket: {e}")
            pass # This might happen if the connection is already closed but not yet detected by WebSocketDisconnect

    event_manager.register_websocket_broadcast(broadcast_event)

    try:
        while True:
            # Keep the connection alive, or handle incoming messages from frontend
            message = await websocket.receive_text()
            try:
                data = json.loads(message)
                if data.get('type') == 'user_message':
                    # User messages from frontend are already handled by the /api/goal endpoint
                    # and then broadcast back via event_manager.
                    # So, we don't need to add them to history here again to avoid duplicates.
                    pass
            except json.JSONDecodeError:
                pass # Ignore non-JSON messages or other types
    except WebSocketDisconnect:
        print("WebSocket disconnected.")
    finally:
        event_manager.register_websocket_broadcast(None)

# Serve static files for the old UI (CSS, JS, etc.) - Commented out to focus on Vue.js interface
# app.mount("/old_static", StaticFiles(directory="frontend"), name="old_static")

# Serve static files for the old dashboard - Commented out to focus on Vue.js interface
# app.mount("/old_dashboard", StaticFiles(directory="frontend/old_dashboard"), name="old_dashboard")

# Serve static files from the root directory for assets - must be last to avoid capturing other routes
app.mount("/", StaticFiles(directory="static", html=True), name="static")

@app.middleware("http")
async def add_security_headers(request, call_next):
    response = await call_next(request)
    
    # Remove unneeded headers
    # Remove unneeded headers if they exist
    if "content-security-policy" in response.headers:
        del response.headers["content-security-policy"]
    if "x-xss-protection" in response.headers:
        del response.headers["x-xss-protection"]
    if "X-Frame-Options" in response.headers: # Replaced by CSP frame-ancestors
        del response.headers["X-Frame-Options"]

    # Add security headers
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    
    # Remove Expires header if present (prefer Cache-Control)
    if "Expires" in response.headers:
        del response.headers["Expires"]

    return response

@app.on_event("startup")
async def startup_event_orchestrator():
    """Run startup tasks for the orchestrator."""
    await orchestrator.startup()

# WebSocket endpoint for real-time event stream via API router
@api_router.websocket("/")
async def api_websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    print(f"WebSocket connected from client: {websocket.client}")
    print(f"Requested WebSocket path: {websocket.scope['path']}")
    print(f"WebSocket connection type: {websocket.scope['type']}")

    async def broadcast_event(event_data: dict):
        try:
            await websocket.send_json(event_data)
            
            # Add event to chat history manager
            sender = "system"
            text = ""
            message_type = event_data.get("type", "default")
            raw_data = event_data.get("payload", {}) # Provide empty dict as default

            if message_type == 'goal_received':
                text = f"Goal received: \"{raw_data.get('goal', 'N/A')}\""
            elif message_type == 'plan_ready':
                text = f"Here is the plan:\n{raw_data.get('llm_response', 'No plan text available.')}"
                sender = "bot"
            elif message_type == 'goal_completed':
                text = f"Goal completed. Result: {json.dumps(raw_data.get('results', {}), indent=2)}"
            elif message_type == 'command_execution_start':
                text = f"Executing command: {raw_data.get('command', 'N/A')}"
            elif message_type == 'command_execution_end':
                status = raw_data.get('status', 'N/A')
                output = raw_data.get('output', '')
                error = raw_data.get('error', '')
                text = f"Command finished ({status}). Output: {output or error}"
            elif message_type == 'error':
                text = f"Error: {raw_data.get('message', 'Unknown error')}"
                sender = "error"
            elif message_type == 'progress':
                text = f"Progress: {raw_data.get('message', 'N/A')}"
            elif message_type == 'llm_response':
                text = raw_data.get('response', 'N/A')
                sender = "bot"
            elif message_type == 'user_message':
                text = raw_data.get('message', 'N/A')
                sender = "user"
            elif message_type == 'thought':
                text = json.dumps(raw_data.get('thought', {}), indent=2)
                sender = "thought"
            elif message_type == 'tool_code':
                text = raw_data.get('code', 'N/A')
                sender = "tool-code"
            elif message_type == 'tool_output':
                text = raw_data.get('output', 'N/A')
                sender = "tool-output"
            elif message_type == 'settings_updated':
                text = "Settings updated successfully."
            elif message_type == 'file_uploaded':
                text = f"File uploaded: {raw_data.get('filename', 'N/A')}"
            elif message_type == 'knowledge_base_update':
                text = f"Knowledge Base updated: {raw_data.get('type', 'N/A')}"
            elif message_type == 'llm_status':
                status = raw_data.get('status', 'N/A')
                model = raw_data.get('model', 'N/A')
                message = raw_data.get('message', '')
                text = f"LLM ({model}) connection {status}. {message}"
                if status == 'disconnected':
                    sender = "error"
            elif message_type == 'diagnostics_report':
                text = f"Diagnostics Report: {json.dumps(raw_data, indent=2)}"
            elif message_type == 'user_permission_request':
                text = f"User Permission Request: {json.dumps(raw_data, indent=2)}"
            
            if text: # Only add messages with content
                chat_history_manager.add_message(sender, text, message_type, raw_data)

        except RuntimeError as e:
            print(f"Error sending to WebSocket: {e}")
            pass # This might happen if the connection is already closed but not yet detected by WebSocketDisconnect

    event_manager.register_websocket_broadcast(broadcast_event)

    try:
        while True:
            # Keep the connection alive, or handle incoming messages from frontend
            message = await websocket.receive_text()
            try:
                data = json.loads(message)
                if data.get('type') == 'user_message':
                    # User messages from frontend are already handled by the /api/goal endpoint
                    # and then broadcast back via event_manager.
                    # So, we don't need to add them to history here again to avoid duplicates.
                    pass
            except json.JSONDecodeError:
                pass # Ignore non-JSON messages or other types
    except WebSocketDisconnect:
        print("WebSocket disconnected.")
    finally:
        event_manager.register_websocket_broadcast(None)

# Commented out to focus on Vue.js interface
# @app.get("/old_dashboard")
# async def read_old_dashboard():
#     return FileResponse("frontend/old_dashboard/index.html")

@app.get("/api/hello")
async def hello_world():
    return {"message": "Hello from AutoBot backend!"}

@app.get("/api/version")
async def get_version():
    # For now, hardcode version info. In a real app, this would come from a config file or build process.
    return {
        "version_no": "1.0.0",
        "version_time": "2025-06-18 20:00 UTC"
    }

@app.get("/.well-known/appspecific/com.chrome.devtools.json")
async def chrome_devtools_json():
    """
    Handles the request for /.well-known/appspecific/com.chrome.devtools.json
    to prevent 404 errors in Chrome/Edge developer console.
    """
    return JSONResponse(status_code=200, content={})

@app.post("/api/login")
async def login(username: str = Form(...), password: str = Form(...)):
    user_role = security_layer.authenticate_user(username, password)
    if user_role:
        security_layer.audit_log("login", username, "success", {"ip": "N/A"}) # IP logging would be more complex
        return {"message": "Login successful", "role": user_role}
    else:
        security_layer.audit_log("login", username, "failure", {"reason": "invalid_credentials"})
        return JSONResponse(status_code=401, content={"message": "Invalid credentials"})

@app.post("/api/goal")
async def receive_goal(payload: GoalPayload): # Changed to accept JSON payload
    goal = payload.goal
    use_phi2 = payload.use_phi2
    user_role = payload.user_role

    if not security_layer.check_permission(user_role, "allow_goal_submission"):
        security_layer.audit_log("submit_goal", user_role, "denied", {"goal": goal, "reason": "permission_denied"})
        return JSONResponse(status_code=403, content={"message": "Permission denied to submit goal."})
    
    print(f"Received goal via API: {goal}")
    await event_manager.publish("goal_received", {"goal": goal, "use_phi2": use_phi2}) # Re-added use_phi2 to event
    
    try:
        result = await orchestrator.execute_goal(goal, user_role) # use_phi2 is handled by orchestrator's internal logic
        
        security_layer.audit_log("submit_goal", user_role, result.get("status", "unknown"), {"goal": goal, "result": result})
        await event_manager.publish("goal_completed", {"goal": goal, "result": result})
        return result
    except Exception as e:
        error_message = f"Internal Server Error during goal execution: {e}"
        logging.error(error_message, exc_info=True) # Log the full traceback
        security_layer.audit_log("submit_goal", user_role, "failure", {"goal": goal, "error": str(e)})
        await event_manager.publish("error", {"message": error_message})
        return JSONResponse(status_code=500, content={"message": "Internal Server Error", "detail": str(e)})

@app.get("/api/settings")
async def get_settings():
    """Fetches current configuration settings."""
    config_path = "config/config.yaml"
    if not os.path.exists(config_path):
        # If config.yaml doesn't exist, copy from template
        template_path = "config/config.yaml.template"
        if os.path.exists(template_path):
            os.makedirs(os.path.dirname(config_path), exist_ok=True)
            with open(template_path, 'r') as f_template:
                with open(config_path, 'w') as f_config:
                    f_config.write(f_template.read())
        else:
            return JSONResponse(status_code=500, content={"message": "Config template not found."})

    with open(config_path, 'r') as f:
        settings = yaml.safe_load(f)
    return settings

@app.get("/api/settings_modal_html")
async def get_settings_modal_html():
    """
    This endpoint is no longer used as the new admin GUI handles settings directly.
    Returning a 404 or an empty response.
    """
    return JSONResponse(status_code=404, content={"message": "This endpoint is deprecated. Settings are now handled by the new admin GUI."})

@app.get("/api/system_metrics")
async def get_system_metrics_api():
    """Fetches real-time system metrics (CPU, RAM, GPU/VRAM)."""
    metrics = diagnostics.get_system_metrics()
    return metrics

@app.post("/api/settings")
async def update_settings(settings: dict):
    """Updates configuration settings."""
    config_path = "config/config.yaml"
    try:
        with open(config_path, 'w') as f:
            yaml.safe_dump(settings, f, indent=2)
        
        # Dynamically update logging level if it was changed
        if 'logging' in settings and 'level' in settings['logging']:
            new_level = settings['logging']['level'].upper()
            numeric_level = getattr(logging, new_level, None)
            if isinstance(numeric_level, int):
                logging.getLogger().setLevel(numeric_level)
                print(f"Logging level updated to {new_level}")
            else:
                print(f"Warning: Invalid logging level received: {new_level}")

        await event_manager.publish("settings_updated", {"settings": settings})
        return {"message": "Settings updated successfully."}
    except Exception as e:
        await event_manager.publish("error", {"message": f"Failed to update settings: {e}"})
        return JSONResponse(status_code=500, content={"message": f"Failed to update settings: {e}"})

@app.post("/api/uploadfile/")
async def create_upload_file(file: UploadFile = File(...), file_type: str = Form(...), metadata: Optional[str] = Form(None)):
    """Handles file uploads and adds them to the knowledge base."""
    upload_dir = "uploads"
    os.makedirs(upload_dir, exist_ok=True)
    if file.filename is None:
        return JSONResponse(status_code=400, content={"message": "Filename not provided."})
    file_path = os.path.join(upload_dir, file.filename)
    
    parsed_metadata = json.loads(metadata) if metadata else {}

    try:
        with open(file_path, "wb") as buffer:
            while True:
                chunk = await file.read(1024)
                if not chunk:
                    break
                buffer.write(chunk)
        
        await event_manager.publish("file_uploaded", {"filename": file.filename, "path": file_path, "size": file.size})
        
        # Add file to knowledge base
        kb_result = knowledge_base.add_file(file_path, file_type, parsed_metadata)
        if kb_result["status"] == "success":
            await event_manager.publish("knowledge_base_update", {"type": "file_added", "filename": file.filename, "kb_result": kb_result})
            return {"filename": file.filename, "message": "File uploaded and added to KB successfully.", "kb_result": kb_result}
        else:
            await event_manager.publish("error", {"message": f"File uploaded but failed to add to KB: {kb_result['message']}"})
            return JSONResponse(status_code=500, content={"message": f"File uploaded but failed to add to KB: {kb_result['message']}"})

    except Exception as e:
        await event_manager.publish("error", {"message": f"Failed to upload or process file {file.filename}: {e}"})
        return JSONResponse(status_code=500, content={"message": f"Failed to upload or process file: {e}"})

@app.get("/api/files")
async def list_files_api(path: str = Query("", description="Path to list files from")):
    """
    Lists files and directories within a specified path.
    """
    base_dir = os.getcwd() # Current working directory of the application
    target_dir = os.path.join(base_dir, path)

    if not os.path.exists(target_dir) or not os.path.isdir(target_dir):
        return JSONResponse(status_code=404, content={"message": "Directory not found."})

    files_list = []
    try:
        for item_name in os.listdir(target_dir):
            item_path = os.path.join(target_dir, item_name)
            relative_path = os.path.relpath(item_path, base_dir)
            is_dir = os.path.isdir(item_path)
            files_list.append({
                "name": item_name,
                "path": relative_path,
                "is_dir": is_dir,
                "size": os.path.getsize(item_path) if not is_dir else None,
                "last_modified": os.path.getmtime(item_path)
            })
        # Sort directories first, then files, both alphabetically
        files_list.sort(key=lambda x: (not x['is_dir'], x['name'].lower()))
        return {"files": files_list}
    except Exception as e:
        logging.error(f"Error listing files in {target_dir}: {e}", exc_info=True)
        return JSONResponse(status_code=500, content={"message": f"Failed to list files: {e}"})

@app.delete("/api/delete_file")
async def delete_file_api(path: str = Query(..., description="Path of the file or directory to delete")):
    """
    Deletes a file or an empty directory at the specified path.
    """
    full_path = os.path.join(os.getcwd(), path)

    if not os.path.exists(full_path):
        return JSONResponse(status_code=404, content={"message": "File or directory not found."})

    try:
        if os.path.isfile(full_path):
            os.remove(full_path)
            message = f"File '{path}' deleted successfully."
        elif os.path.isdir(full_path):
            # Only allow deleting empty directories for safety
            if not os.listdir(full_path):
                os.rmdir(full_path)
                message = f"Empty directory '{path}' deleted successfully."
            else:
                return JSONResponse(status_code=400, content={"message": "Directory is not empty. Cannot delete non-empty directories."})
        else:
            return JSONResponse(status_code=400, content={"message": "Path is not a file or an empty directory."})
        
        await event_manager.publish("file_deleted", {"path": path, "message": message})
        return {"message": message}
    except OSError as e:
        logging.error(f"OS Error deleting {full_path}: {e}", exc_info=True)
        return JSONResponse(status_code=500, content={"message": f"Failed to delete {path}: {e}"})
    except Exception as e:
        logging.error(f"Error deleting {full_path}: {e}", exc_info=True)
        return JSONResponse(status_code=500, content={"message": f"Failed to delete {path}: {e}"})

@app.post("/api/execute_command")
async def execute_command(command_data: dict, user_role: str = Form("user")): # Added user_role
    """
    Executes a shell command and returns its output.
    """
    command = command_data.get("command")
    if not command:
        security_layer.audit_log("execute_command", user_role, "failure", {"command": command, "reason": "no_command_provided"})
        await event_manager.publish("error", {"message": "No command provided for execution."})
        return JSONResponse(status_code=400, content={"message": "No command provided."})

    if not security_layer.check_permission(user_role, "allow_shell_execute", resource=command):
        security_layer.audit_log("execute_command", user_role, "failure", {"command": command, "reason": "permission_denied"})
        return JSONResponse(status_code=403, content={"message": "Permission denied to execute command."})

    await event_manager.publish("command_execution_start", {"command": command})
    print(f"Executing command: {command}")
    
    try:
        # Run the command asynchronously
        process = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()

        output = stdout.decode().strip()
        error = stderr.decode().strip()

        if process.returncode == 0:
            message = f"Command executed successfully.\nOutput:\n{output}"
            security_layer.audit_log("execute_command", user_role, "success", {"command": command, "output": output})
            await event_manager.publish("command_execution_end", {"command": command, "status": "success", "output": output})
            print(message)
            return {"message": message, "output": output, "status": "success"}
        else:
            message = f"Command failed with exit code {process.returncode}.\nError:\n{error}\nOutput:\n{output}"
            security_layer.audit_log("execute_command", user_role, "failure", {"command": command, "error": error, "returncode": process.returncode})
            await event_manager.publish("command_execution_end", {"command": command, "status": "error", "error": error, "output": output, "returncode": process.returncode})
            print(message)
            return JSONResponse(status_code=500, content={"message": message, "error": error, "output": output, "status": "error"})
    except Exception as e:
        message = f"Error during command execution: {e}"
        security_layer.audit_log("execute_command", user_role, "failure", {"command": command, "error": str(e)})
        await event_manager.publish("error", {"message": message})
        return JSONResponse(status_code=500, content={"message": message, "status": "error"})

@app.post("/api/knowledge_base/store_fact")
async def store_fact_api(content: str = Form(...), metadata: Optional[str] = Form(None)):
    """API to store a structured fact in the knowledge base."""
    parsed_metadata = json.loads(metadata) if metadata else None
    result = knowledge_base.store_fact(content, parsed_metadata)
    if result["status"] == "success":
        await event_manager.publish("knowledge_base_update", {"type": "fact_stored", "fact_id": result.get("fact_id"), "content": content})
        return result
    else:
        await event_manager.publish("error", {"message": f"Failed to store fact: {result['message']}"})
        return JSONResponse(status_code=500, content=result)

@app.get("/api/chat/history")
async def get_chat_history_api():
    """
    Retrieves the conversation history from the ChatHistoryManager.
    """
    history = chat_history_manager.get_all_messages()
    # Calculate a simple token count (e.g., word count)
    total_tokens = sum(len(msg.get('text', '').split()) for msg in history)
    return {"history": history, "tokens": total_tokens}

@app.post("/api/chat/reset")
async def reset_chat_api(user_role: str = Form("user")):
    """Clears the entire chat history."""
    if not security_layer.check_permission(user_role, "allow_chat_control"): # Assuming a new permission
        security_layer.audit_log("reset_chat", user_role, "denied", {"reason": "permission_denied"})
        return JSONResponse(status_code=403, content={"message": "Permission denied to reset chat."})
    
    chat_history_manager.clear_history()
    await event_manager.publish("chat_reset", {"message": "Chat history cleared."})
    return {"message": "Chat history cleared successfully."}

@app.post("/api/chat/new")
async def new_chat_session_api(user_role: str = Form("user")):
    """Starts a new chat session by clearing the current history."""
    if not security_layer.check_permission(user_role, "allow_chat_control"):
        security_layer.audit_log("new_chat", user_role, "denied", {"reason": "permission_denied"})
        return JSONResponse(status_code=403, content={"message": "Permission denied to start new chat."})
    
    chat_history_manager.clear_history() # For now, new chat means clearing current
    await event_manager.publish("new_chat_session", {"message": "New chat session started."})
    return {"message": "New chat session started successfully."}

@app.get("/api/chat/list_sessions")
async def list_chat_sessions_api(user_role: str = Query("user")):
    """Lists available chat sessions."""
    if not security_layer.check_permission(user_role, "allow_chat_control"):
        security_layer.audit_log("list_chat_sessions", user_role, "denied", {"reason": "permission_denied"})
        return JSONResponse(status_code=403, content={"message": "Permission denied to list chat sessions."})
    
    sessions = chat_history_manager.list_sessions()
    return {"sessions": sessions}

@app.get("/api/chat/load_session/{session_id}")
async def load_chat_session_api(session_id: str, user_role: str = Query("user")):
    """Loads a specific chat session."""
    if not security_layer.check_permission(user_role, "allow_chat_control"):
        security_layer.audit_log("load_chat_session", user_role, "denied", {"session_id": session_id, "reason": "permission_denied"})
        return JSONResponse(status_code=403, content={"message": "Permission denied to load chat session."})
    
    history = chat_history_manager.load_session(session_id)
    if history:
        await event_manager.publish("chat_session_loaded", {"session_id": session_id, "message": "Chat session loaded."})
        return {"message": f"Session '{session_id}' loaded successfully.", "history": history}
    else:
        return JSONResponse(status_code=404, content={"message": f"Session '{session_id}' not found."})

@app.post("/api/chat/save_session")
async def save_chat_session_api(session_id: str = Form("default_session"), user_role: str = Form("user")):
    """Saves the current chat history as a named session."""
    if not security_layer.check_permission(user_role, "allow_chat_control"):
        security_layer.audit_log("save_chat_session", user_role, "denied", {"session_id": session_id, "reason": "permission_denied"})
        return JSONResponse(status_code=403, content={"message": "Permission denied to save chat session."})
    
    chat_history_manager.save_session(session_id)
    await event_manager.publish("chat_session_saved", {"session_id": session_id, "message": "Chat session saved."})
    return {"message": f"Current chat session saved as '{session_id}'."}

@app.get("/ctx_window_get")
async def get_context_window():
    """
    Retrieves the content of the LLM's context window.
    For now, this is a placeholder. In a real implementation, this would fetch
    the actual context provided to the LLM in the last interaction.
    """
    # Placeholder for actual context window retrieval
    mock_context = """
System Prompt: You are an AI assistant.
Conversation History:
User: Hello, how are you?
Agent: I am an AI assistant, functioning as expected. How can I help you today?
Relevant Knowledge:
- AutoBot is an autonomous agent.
- It uses Ollama for local LLM interactions.
"""
    mock_tokens = len(mock_context.split()) # Simple token count
    return {"content": mock_context, "tokens": mock_tokens}

@app.get("/api/knowledge_base/get_fact")
async def get_fact_api(fact_id: Optional[int] = None, query: Optional[str] = None):
    """API to retrieve facts from the knowledge base."""
    facts = knowledge_base.get_fact(fact_id=fact_id, query=query)
    return {"facts": facts}

@app.post("/api/knowledge_base/search")
async def search_knowledge_base_api(query: str = Form(...), n_results: int = Form(5)):
    """API to search the vector store in the knowledge base."""
    results = knowledge_base.search(query, n_results)
    return {"results": results}


@app.post("/api/voice/listen")
async def voice_listen_api(user_role: str = Form("user")): # Added user_role
    if not security_layer.check_permission(user_role, "allow_voice_listen"):
        security_layer.audit_log("voice_listen", user_role, "denied", {"reason": "permission_denied"})
        return JSONResponse(status_code=403, content={"message": "Permission denied to listen via voice."})

    result = await voice_interface.listen_and_convert_to_text()
    if result["status"] == "success":
        security_layer.audit_log("voice_listen", user_role, "success", {"text": result["text"]})
        return {"message": "Speech recognized.", "text": result["text"]}
    else:
        security_layer.audit_log("voice_listen", user_role, "failure", {"reason": result.get('message')})
        return JSONResponse(status_code=500, content={"message": f"Speech recognition failed: {result['message']}"})

@app.post("/api/voice/speak")
async def voice_speak_api(text: str = Form(...), user_role: str = Form("user")):
    """Converts text to speech and plays it."""
    if not security_layer.check_permission(user_role, "allow_voice_speak"):
        security_layer.audit_log("voice_speak", user_role, "denied", {"text_preview": text[:50], "reason": "permission_denied"})
        return JSONResponse(status_code=403, content={"message": "Permission denied to speak via voice."})

    result = await voice_interface.speak_text(text)
    if result["status"] == "success":
        security_layer.audit_log("voice_speak", user_role, "success", {"text_preview": text[:50]})
        return {"message": "Text spoken successfully."}
    else:
        security_layer.audit_log("voice_speak", user_role, "failure", {"text_preview": text[:50], "reason": result.get('message')})
        return JSONResponse(status_code=500, content={"message": f"Text-to-speech failed: {result['message']}"})

@app.post("/api/agent/pause")
async def pause_agent_api(user_role: str = Form("user")):
    """Pauses the agent's current operation."""
    if not security_layer.check_permission(user_role, "allow_agent_control"):
        security_layer.audit_log("agent_pause", user_role, "denied", {"reason": "permission_denied"})
        return JSONResponse(status_code=403, content={"message": "Permission denied to pause agent."})
    
    # TODO: Implement actual pause functionality in orchestrator
    # For now, just simulate success
    result = {"status": "success"}
    security_layer.audit_log("agent_pause", user_role, "success", {})
    await event_manager.publish("agent_paused", {"message": "Agent operation paused."})
    return {"message": "Agent paused successfully."}

@app.post("/api/agent/resume")
async def resume_agent_api(user_role: str = Form("user")):
    """Resumes the agent's operation if paused."""
    if not security_layer.check_permission(user_role, "allow_agent_control"):
        security_layer.audit_log("agent_resume", user_role, "denied", {"reason": "permission_denied"})
        return JSONResponse(status_code=403, content={"message": "Permission denied to resume agent."})
    
    # TODO: Implement actual resume functionality in orchestrator
    # For now, just simulate success
    result = {"status": "success"}
    security_layer.audit_log("agent_resume", user_role, "success", {})
    await event_manager.publish("agent_resumed", {"message": "Agent operation resumed."})
    return {"message": "Agent resumed successfully."}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
