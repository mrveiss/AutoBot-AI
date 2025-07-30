from fastapi import FastAPI, WebSocket, WebSocketDisconnect, UploadFile, File, Form, Query
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import os
import uvicorn
import json
import asyncio
import subprocess
import logging
import logging.config
import traceback # Import traceback module
from typing import Optional, Dict, Any, List
from pydantic import BaseModel
import redis
import socket
from fastapi import Request # Ensure Request is imported at the top

# Import the centralized ConfigManager
from src.config import config as global_config_manager

# Configure logging at the very beginning
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("logs/autobot_backend.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)
logger.info("main.py: Starting application initialization.")

class GoalPayload(BaseModel):
    goal: str
    use_phi2: bool = False
    user_role: str = "user"

class CommandApprovalPayload(BaseModel):
    task_id: str
    approved: bool
    user_role: str = "user"

from src.orchestrator import Orchestrator
from src.event_manager import event_manager
from src.knowledge_base import KnowledgeBase
from src.diagnostics import Diagnostics
from src.security_layer import SecurityLayer
from src.voice_interface import VoiceInterface
from src.chat_history_manager import ChatHistoryManager

async def _check_redis_modules(redis_host: str, redis_port: int):
    """Checks if RediSearch module is loaded in Redis."""
    try:
        resolved_host = redis_host
        if redis_host == "host.docker.internal":
            try:
                resolved_host = socket.gethostbyname(redis_host)
                logger.info(f"Resolved host.docker.internal to IP: {resolved_host}")
            except socket.gaierror as e:
                logger.error(f"Failed to resolve host.docker.internal: {e}")
                resolved_host = redis_host

        r = redis.Redis(host=resolved_host, port=redis_port, decode_responses=True)
        
        try:
            # Test basic connection first
            r.ping()
            logger.info(f"Successfully connected to Redis at {resolved_host}:{redis_port}")
            
            # Try to get client info with proper error handling
            try:
                client_info = r.client_list()
                logger.info(f"Redis client info retrieved successfully")
            except Exception as e:
                logger.warning(f"Could not get client info from Redis: {e}")
                client_info = []
        except Exception as e:
            logger.warning(f"Could not connect to Redis: {e}")
            return False

        try:
            # Try to get module list - this may fail on some Redis configurations
            modules = r.module_list()
            if isinstance(modules, list):
                module_names = [m.get('name', '') for m in modules] if modules else []
                logger.info(f"Redis modules loaded: {module_names}")
                if "search" in module_names:
                    logger.info("✅ RediSearch module 'search' is detected in Redis.")
                    return True
                else:
                    logger.warning("❌ RediSearch module 'search' is NOT detected in Redis.")
                    return False
            else:
                logger.warning("Could not retrieve module list - Redis modules check skipped")
                return True
        except Exception as e:
            logger.warning(f"Could not check Redis modules: {e}")
            # Return True anyway since basic Redis connection works
            return True
            
    except redis.ConnectionError as e:
        logger.error(f"Failed to connect to Redis at {redis_host}:{redis_port} for module check: {e}")
        return False
    except Exception as e:
        logger.error(f"Error checking Redis modules: {e}")
        return False

# Removed _ensure_config_exists() function and its call. ConfigManager handles this.
logger.info("main.py: Configuration ensured.")

from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Context manager for application startup and shutdown events.
    Replaces deprecated @app.on_event("startup") and @app.on_event("shutdown").
    """
    print("DEBUG: Entering lifespan startup.")
    logger.info("Application lifespan startup initiated.")

    logger.debug("Lifespan: Initializing core components...")
    app.state.orchestrator = Orchestrator()
    app.state.knowledge_base = KnowledgeBase()
    app.state.diagnostics = Diagnostics()
    app.state.voice_interface = VoiceInterface()
    app.state.security_layer = SecurityLayer()
    logger.info("main.py: Core components (Orchestrator, KB, Diagnostics, Voice, Security) initialized within lifespan.")
    logger.debug("Lifespan: Core components initialized.")

    logger.debug("Lifespan: Checking Redis modules...")
    redis_config = global_config_manager.get_redis_config()
    await _check_redis_modules(redis_config.get('host', 'localhost'), redis_config.get('port', 6379))
    logger.debug("Lifespan: Redis modules checked.")

    async def safe_redis_task_wrapper(task_name, coro):
        """Wrapper for Redis background tasks with error handling"""
        try:
            await coro
        except Exception as e:
            logger.error(f"Redis background task '{task_name}' failed: {e}", exc_info=True)
            logger.warning(f"Redis task '{task_name}' will be retried in 30 seconds...")
            await asyncio.sleep(30)
            # Could implement retry logic here if needed

    logger.debug("Lifespan: Starting Orchestrator startup...")
    logger.debug("Lifespan: Starting Orchestrator startup...")
    try:
        await app.state.orchestrator.startup()
        if app.state.orchestrator.task_transport_type == "redis" and app.state.orchestrator.redis_client:
            logger.debug("Lifespan: Skipping Redis background tasks creation (temporarily disabled for debugging)...")
            # asyncio.create_task(
            #     safe_redis_task_wrapper(
            #         "command_approvals_listener", 
            #         app.state.orchestrator._listen_for_command_approvals()
            #     )
            # )
            # asyncio.create_task(
            #     safe_redis_task_wrapper(
            #         "worker_capabilities_listener", 
            #         app.state.orchestrator._listen_for_worker_capabilities()
            #     )
            # )
            logger.debug("Lifespan: Redis background tasks creation skipped.")
    except Exception as e:
        logger.error(f"Error during orchestrator startup: {e}", exc_info=True)
        # Depending on severity, you might want to raise the exception or handle it gracefully
        # For now, we'll log and allow the app to potentially continue in a degraded state
    logger.debug("Lifespan: Orchestrator startup completed.")
    
    logger.debug("Lifespan: Initializing KnowledgeBase...")
    try:
        # Initialize KnowledgeBase asynchronously
        await app.state.knowledge_base.ainit()
        logger.info("KnowledgeBase ainit() called during startup.")
    except Exception as e:
        logger.error(f"Error during KnowledgeBase initialization: {e}", exc_info=True)
        # Let's not raise the exception to see if the app can still function
        logger.warning("KnowledgeBase initialization failed, but continuing startup...")
    logger.debug("Lifespan: KnowledgeBase initialized.")

    logger.debug("Lifespan: Initializing ChatHistoryManager...")
    redis_config = global_config_manager.get_redis_config()
    use_redis = redis_config.get('enabled', False)
    redis_host = redis_config.get('host', 'localhost')
    redis_port = redis_config.get('port', 6379)
    logger.info(f"main.py: Redis configuration loaded from centralized config: enabled={use_redis}, host={redis_host}, port={redis_port}")

    app.state.chat_history_manager = ChatHistoryManager(
        history_file=global_config_manager.get_nested('data.chat_history_file', "data/chat_history.json"),
        use_redis=use_redis,
        redis_host=redis_host,
        redis_port=redis_port
    )
    logger.info("main.py: ChatHistoryManager initialized within lifespan.")
    logger.debug("Lifespan: ChatHistoryManager initialized.")

    logger.debug("Lifespan: Initializing main Redis client...")
    try:
        app.state.main_redis_client = redis.Redis(host=redis_host, port=redis_port, decode_responses=True)
        app.state.main_redis_client.ping() # Test connection
        logger.info("main.py: Main Redis client initialized and connected within lifespan.")
    except redis.ConnectionError as e:
        logger.error(f"main.py: Failed to connect to Redis for main_redis_client: {e}")
        app.state.main_redis_client = None
    logger.debug("Lifespan: Main Redis client initialized.")

    yield

    # Shutdown events
    logger.info("Application lifespan shutdown initiated.")
    print("Application shutting down.")

app = FastAPI(lifespan=lifespan)
logger.info("main.py: FastAPI app initialized with lifespan.")

# Enable CORS for frontend on multiple ports using config
backend_config = global_config_manager.get_backend_config()
cors_origins = backend_config.get('cors_origins', ["http://localhost:8080", "http://localhost:5173"])

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
logger.info("main.py: CORS middleware added.")



# Create a separate router for API endpoints
api_router = FastAPI(title="AutoBot API")
app.mount("/api", api_router)
logger.info("main.py: API router mounted.")

# WebSocket endpoint for real-time event stream
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    logger.info(f"main.py: WebSocket connected from client: {websocket.client}")
    logger.info(f"main.py: Requested WebSocket path: {websocket.scope['path']}")
    logger.info(f"main.py: WebSocket connection type: {websocket.scope['type']}")

    # Access chat_history_manager from app.state via scope
    chat_history_manager = websocket.scope["app"].state.chat_history_manager

    async def broadcast_event(event_data: dict):
        try:
            await websocket.send_json(event_data)
            
            # Add event to chat history manager
            sender = "system"
            text = ""
            message_type = event_data.get("type", "default")
            raw_data = event_data.get("payload", {})

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
            
            if text:
                chat_history_manager.add_message(sender, text, message_type, raw_data)

        except RuntimeError as e:
            print(f"Error sending to WebSocket: {e}")
            pass

    event_manager.register_websocket_broadcast(broadcast_event)

    try:
        while True:
            message = await websocket.receive_text()
            try:
                data = json.loads(message)
                if data.get('type') == 'user_message':
                    pass
            except json.JSONDecodeError:
                pass
    except WebSocketDisconnect:
        print("WebSocket disconnected.")
    finally:
        event_manager.register_websocket_broadcast(None)

app.mount("/", StaticFiles(directory="frontend/static", html=True), name="static")

@app.middleware("http")
async def add_security_headers(request, call_next):
    response = await call_next(request)
    
    if "content-security-policy" in response.headers:
        del response.headers["content-security-policy"]
    if "x-xss-protection" in response.headers:
        del response.headers["x-xss-protection"]
    if "X-Frame-Options" in response.headers:
        del response.headers["X-Frame-Options"]

    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    
    if "Expires" in response.headers:
        del response.headers["Expires"]

    return response


@api_router.get("/hello")
async def hello_world():
    return {"message": "Hello from AutoBot backend!"}

@api_router.get("/version")
async def get_version():
    return {
        "version_no": "1.0.0",
        "version_time": "2025-06-18 20:00 UTC"
    }

@api_router.get("/health")
async def health_check(request: Request):
    """Health check endpoint for frontend status monitoring."""
    orchestrator_status = "unknown"
    diagnostics_status = "unknown"
    llm_status = "skipped" # Still skipped, as we're not checking it yet
    
    logger.debug("Health check: Starting with explicit app.state checks and print statements.")
    
    try:
        orchestrator = getattr(request.app.state, 'orchestrator', None)
        print(f"DEBUG: Health check - retrieved orchestrator: {orchestrator}")
        if orchestrator:
            orchestrator_status = "connected"
            logger.debug("Health check: Orchestrator instance found in app.state.")
        else:
            orchestrator_status = "not_found_in_state"
            logger.error("Health check: Orchestrator instance NOT found in app.state.")
        
        diagnostics = getattr(request.app.state, 'diagnostics', None)
        print(f"DEBUG: Health check - retrieved diagnostics: {diagnostics}")
        if diagnostics:
            diagnostics_status = "connected"
            logger.debug("Health check: Diagnostics instance found in app.state.")
        else:
            diagnostics_status = "not_found_in_state"
            logger.error("Health check: Diagnostics instance NOT found in app.state.")

        logger.info("Health check: Returning status after explicit app.state checks.")
        return {
            "status": "healthy",
            "backend": "connected",
            "orchestrator": orchestrator_status,
            "diagnostics": diagnostics_status, # Add diagnostics status to response
            "llm": llm_status,
            "timestamp": asyncio.get_event_loop().time()
        }
    except Exception as e:
        logger.error(f"Health check: An unexpected error occurred during app.state access: {e}", exc_info=True)
        return JSONResponse(
            status_code=503,
            content={
                "status": "unhealthy", 
                "backend": "connected",
                "orchestrator": "error_exception",
                "diagnostics": "error_exception",
                "llm": "error_exception",
                "error": str(e),
                "detail": traceback.format_exc()
            }
        )

@api_router.get("/chats")
async def list_chats(request: Request):
    """List all available chat sessions."""
    chat_history_manager = request.app.state.chat_history_manager
    try:
        sessions = chat_history_manager.list_sessions()
        return {"chats": sessions}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

@api_router.get("/chats/{chat_id}")
async def get_chat(chat_id: str, request: Request):
    """Get a specific chat session."""
    chat_history_manager = request.app.state.chat_history_manager
    try:
        history = chat_history_manager.load_session(chat_id)
        if history:
            return {"chat_id": chat_id, "history": history}
        else:
            return JSONResponse(status_code=404, content={"error": "Chat not found"})
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

@api_router.post("/chats/new")
async def create_new_chat():
    """Create a new chat session ID (POST method)."""
    try:
        import uuid
        chat_id = str(uuid.uuid4())
        return {"chat_id": chat_id, "status": "success"}
    except Exception as e:
        logging.error(f"Error creating new chat: {str(e)}")
        return JSONResponse(status_code=500, content={"error": f"Error creating new chat: {str(e)}"})

@api_router.get("/settings/backend")
async def get_backend_settings():
    """Get backend-specific settings from the centralized ConfigManager."""
    try:
        return global_config_manager.get_backend_config()
    except Exception as e:
        logger.error(f"Failed to retrieve backend settings from ConfigManager: {e}", exc_info=True)
        return JSONResponse(status_code=500, content={"error": f"Failed to retrieve backend settings: {e}"})

@api_router.post("/settings/backend")
async def update_backend_settings(request: Request, settings: dict): # Reordered arguments
    """Update backend-specific settings using the centralized ConfigManager."""
    try:
        for key, value in settings.items():
            global_config_manager.set_nested(f'backend.{key}', value)
        
        global_config_manager.save_settings()
        
        global_config_manager.reload()

        if 'logging' in settings and 'level' in settings['logging']:
            new_level = settings['logging']['level'].upper()
            numeric_level = getattr(logging, new_level, None)
            if isinstance(numeric_level, int):
                logging.getLogger().setLevel(numeric_level)
                print(f"Logging level updated to {new_level}")
            else:
                print(f"Warning: Invalid logging level received: {new_level}")

        if 'memory' in settings and 'redis' in settings['memory']:
            global chat_history_manager
            redis_config = global_config_manager.get_redis_config()
            use_redis = redis_config.get('enabled', False)
            redis_host = redis_config.get('host', 'localhost')
            redis_port = redis_config.get('port', 6379)
            chat_history_manager = ChatHistoryManager(
                history_file=global_config_manager.get_nested('data.chat_history_file', "data/chat_history.json"),
                use_redis=use_redis,
                redis_host=redis_host,
                redis_port=redis_port
            )
            print(f"ChatHistoryManager updated with Redis settings: enabled={use_redis}, host={redis_host}, port={redis_port}")

        await event_manager.publish("settings_updated", {"backend_settings": settings})
        return {"message": "Backend settings updated successfully."}
    except Exception as e:
        logger.error(f"Failed to update backend settings: {e}", exc_info=True)
        await event_manager.publish("error", {"message": f"Failed to update backend settings: {e}"})
        return JSONResponse(status_code=500, content={"message": f"Failed to update backend settings: {e}"})

@api_router.get("/prompts")
async def get_prompts():
    """Get available system prompts."""
    try:
        prompts_dir = "prompts"
        if not os.path.exists(prompts_dir):
            return {"prompts": []}
        
        prompts = []
        for file in os.listdir(prompts_dir):
            if file.endswith('.txt'):
                file_path = os.path.join(prompts_dir, file)
                with open(file_path, 'r') as f:
                    content = f.read()
                prompts.append({
                    "name": file.replace('.txt', ''),
                    "content": content
                })
        
        return {"prompts": prompts}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.get("/.well-known/appspecific/com.chrome.devtools.json")
async def chrome_devtools_json():
    """
    Handles the request for /.well-known/appspecific/com.chrome.devtools.json
    to prevent 404 errors in Chrome/Edge developer console.
    """
    return JSONResponse(status_code=200, content={})

@api_router.post("/login")
async def login(request: Request, username: str = Form(...), password: str = Form(...)): # Reordered arguments
    security_layer = request.app.state.security_layer
    user_role = security_layer.authenticate_user(username, password)
    if user_role:
        security_layer.audit_log("login", username, "success", {"ip": "N/A"})
        return {"message": "Login successful", "role": user_role}
    else:
        security_layer.audit_log("login", username, "failure", {"reason": "invalid_credentials"})
        return JSONResponse(status_code=401, content={"message": "Invalid credentials"})

@api_router.post("/goal")
async def receive_goal(request: Request, payload: GoalPayload): # Reordered arguments
    """
    Receives a goal from the user to be executed by the orchestrator.
    
    Args:
        payload (GoalPayload): The payload containing the goal, whether to use Phi-2 model, and user role.
    
    Returns:
        dict: The result of the goal execution.
    
    Raises:
        JSONResponse: Returns a 403 error if permission is denied, or a 500 error if an internal error occurs.
    """
    orchestrator = request.app.state.orchestrator
    security_layer = request.app.state.security_layer

    goal = payload.goal
    use_phi2 = payload.use_phi2
    user_role = payload.user_role

    if not security_layer.check_permission(user_role, "allow_goal_submission"):
        security_layer.audit_log("submit_goal", user_role, "denied", {"goal": goal, "reason": "permission_denied"})
        return JSONResponse(status_code=403, content={"message": "Permission denied to submit goal."})
    
    logging.info(f"Received goal via API: {goal}")
    await event_manager.publish("user_message", {"message": goal})
    await event_manager.publish("goal_received", {"goal": goal, "use_phi2": use_phi2})
    
    try:
        orchestrator_result = await orchestrator.execute_goal(goal, [{"role": "user", "content": goal}])
        
        result_dict: Dict[str, Any]
        if isinstance(orchestrator_result, dict):
            result_dict = orchestrator_result
        else:
            result_dict = {"message": str(orchestrator_result)}

        response_message = "An unexpected response format was received."
        tool_output_content: Optional[str] = None
        tool_name: Optional[str] = None
        
        tool_name = result_dict.get("tool_name")
        tool_args = result_dict.get("tool_args", {})
        
        if tool_name == "respond_conversationally":
            response_message = result_dict.get("response_text") or tool_args.get("response_text", "No response text provided.")
            tool_output_content = None
        elif tool_name == "execute_system_command":
            command_output = tool_args.get("output", "")
            command_error = tool_args.get("error", "")
            command_status = tool_args.get("status", "unknown")
            
            if command_status == "success":
                response_message = f"Command executed successfully.\nOutput:\n{command_output}"
                tool_output_content = command_output
            else:
                response_message = f"Command failed ({command_status}).\nError:\n{command_error}\nOutput:\n{command_output}"
                tool_output_content = f"ERROR: {command_error}\nOUTPUT: {command_output}"
        elif tool_name:
            tool_output_content = tool_args.get("output", tool_args.get("message", str(tool_args)))
            response_message = f"Tool Used: {tool_name}\nOutput: {tool_output_content}"
        elif result_dict.get("output"):
            response_message = result_dict["output"]
            tool_output_content = result_dict["output"]
        elif result_dict.get("message"):
            response_message = result_dict["message"]
            tool_output_content = result_dict["message"]
        else:
            response_message = str(result_dict)
            tool_output_content = str(result_dict)

        if tool_output_content and tool_name != "respond_conversationally":
            await event_manager.publish("tool_output", {"output": tool_output_content})

        security_layer.audit_log("submit_goal", user_role, "success", {"goal": goal, "result": response_message})
        await event_manager.publish("goal_completed", {"goal": goal, "result": response_message})
        
        return {"message": response_message}
    except Exception as e:
        error_message = f"Internal Server Error during goal execution: {str(e)}"
        logging.error(error_message, exc_info=True)
        security_layer.audit_log("submit_goal", user_role, "failure", {"goal": goal, "error": str(e)})
        await event_manager.publish("error", {"message": error_message})
        return JSONResponse(status_code=500, content={"message": "Internal Server Error", "detail": str(e)})

@api_router.get("/settings")
async def get_settings():
    """Fetches current configuration settings from the centralized ConfigManager."""
    try:
        return global_config_manager.to_dict()
    except Exception as e:
        logger.error(f"Failed to retrieve settings from ConfigManager: {e}", exc_info=True)
        return JSONResponse(status_code=500, content={"message": f"Failed to retrieve settings: {e}"})

@api_router.get("/settings_modal_html")
async def get_settings_modal_html():
    """
    This endpoint is no longer used as the new admin GUI handles settings directly.
    Returning a 404 or an empty response.
    """
    return JSONResponse(status_code=404, content={"message": "This endpoint is deprecated. Settings are now handled by the new admin GUI."})

@api_router.get("/system_metrics")
async def get_system_metrics_api(request: Request):
    """Fetches real-time system metrics (CPU, RAM, GPU/VRAM)."""
    diagnostics = request.app.state.diagnostics
    metrics = diagnostics.get_system_metrics()
    return metrics

@api_router.post("/settings")
async def update_settings(request: Request, settings: dict): # Reordered arguments
    """Updates configuration settings."""
    # This endpoint is for general settings updates, not just backend.
    # It should use ConfigManager's save_settings and reload.
    try:
        # Update the entire configuration with the provided settings
        # This assumes the incoming 'settings' dict is a full representation of the desired config
        # or a partial update that ConfigManager can intelligently merge.
        # For simplicity, we'll assume it's a partial update to the top level.
        for key, value in settings.items():
            global_config_manager.set(key, value)
        
        global_config_manager.save_settings()
        global_config_manager.reload()

        # Dynamically update logging level if it was changed
        if 'logging' in settings and 'level' in settings['logging']:
            new_level = settings['logging']['level'].upper()
            numeric_level = getattr(logging, new_level, None)
            if isinstance(numeric_level, int):
                logging.getLogger().setLevel(numeric_level)
                print(f"Logging level updated to {new_level}")
            else:
                print(f"Warning: Invalid logging level received: {new_level}")

        # Update ChatHistoryManager with new Redis settings if changed
        if 'memory' in settings and 'redis' in settings['memory']:
            chat_history_manager = request.app.state.chat_history_manager
            redis_config = global_config_manager.get_redis_config()
            use_redis = redis_config.get('enabled', False)
            redis_host = redis_config.get('host', 'localhost')
            redis_port = redis_config.get('port', 6379)
            # Re-initialize ChatHistoryManager with new settings
            request.app.state.chat_history_manager = ChatHistoryManager(
                history_file=global_config_manager.get_nested('data.chat_history_file', "data/chat_history.json"),
                use_redis=use_redis,
                redis_host=redis_host,
                redis_port=redis_port
            )
            print(f"ChatHistoryManager updated with Redis settings: enabled={use_redis}, host={redis_host}, port={redis_port}")

        await event_manager.publish("settings_updated", {"settings": settings})
        return {"message": "Settings updated successfully."}
    except Exception as e:
        logger.error(f"Failed to update settings: {e}", exc_info=True)
        await event_manager.publish("error", {"message": f"Failed to update settings: {e}"})
        return JSONResponse(status_code=500, content={"message": f"Failed to update settings: {e}"})

@api_router.post("/uploadfile/")
async def create_upload_file(request: Request, file: UploadFile = File(...), file_type: str = Form(...), metadata: Optional[str] = Form(None)): # Reordered arguments
    """Handles file uploads and adds them to the knowledge base."""
    knowledge_base = request.app.state.knowledge_base
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
        
        kb_result = await knowledge_base.add_file(file_path, file_type, parsed_metadata)
        if kb_result["status"] == "success":
            await event_manager.publish("knowledge_base_update", {"type": "file_added", "filename": file.filename, "kb_result": kb_result})
            return {"filename": file.filename, "message": "File uploaded and added to KB successfully.", "kb_result": kb_result}
        else:
            await event_manager.publish("error", {"message": f"File uploaded but failed to add to KB: {kb_result['message']}"})
            return JSONResponse(status_code=500, content={"message": f"File uploaded but failed to add to KB: {kb_result['message']}"})

    except Exception as e:
        await event_manager.publish("error", {"message": f"Failed to upload or process file {file.filename}: {e}"})
        return JSONResponse(status_code=500, content={"message": f"Failed to upload or process file: {e}"})

@api_router.get("/files")
async def list_files_api(request: Request, path: str = Query("", description="Path to list files from")): # Reordered arguments
    """
    Lists files and directories within a specified path.
    
    Args:
        path (str): The path to list files from, relative to the current working directory.
    
    Returns:
        dict: A dictionary containing a list of files and directories with their metadata.
    
    Raises:
        JSONResponse: Returns a 404 error if the directory is not found, or a 500 error if an internal error occurs.
    """
    base_dir = os.getcwd()
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
        files_list.sort(key=lambda x: (not x['is_dir'], x['name'].lower()))
        return {"files": files_list}
    except Exception as e:
        logging.error(f"Error listing files in {target_dir}: {str(e)}", exc_info=True)
        return JSONResponse(status_code=500, content={"message": f"Failed to list files: {str(e)}"})

@api_router.delete("/delete_file")
async def delete_file_api(request: Request, path: str = Query(..., description="Path of the file or directory to delete")): # Reordered arguments
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

@api_router.post("/execute_command")
async def execute_command(request: Request, command_data: dict, user_role: str = Form("user")): # Reordered arguments
    """
    Executes a shell command and returns its output.
    
    Args:
        command_data (dict): A dictionary containing the command to execute.
        user_role (str): The role of the user executing the command.
    
    Returns:
        dict: A dictionary containing the result of the command execution.
    
    Raises:
        JSONResponse: Returns a 400 error if no command is provided, a 403 error if permission is denied,
                      or a 500 error if an internal error occurs.
    """
    security_layer = request.app.state.security_layer
    command = command_data.get("command")
    if not command:
        security_layer.audit_log("execute_command", user_role, "failure", {"command": command, "reason": "no_command_provided"})
        await event_manager.publish("error", {"message": "No command provided for execution."})
        return JSONResponse(status_code=400, content={"message": "No command provided."})

    if not security_layer.check_permission(user_role, "allow_shell_execute", resource=command):
        security_layer.audit_log("execute_command", user_role, "failure", {"command": command, "reason": "permission_denied"})
        return JSONResponse(status_code=403, content={"message": "Permission denied to execute command."})

    await event_manager.publish("command_execution_start", {"command": command})
    logging.info(f"Executing command: {command}")
    
    try:
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
            logging.info(message)
            return {"message": message, "output": output, "status": "success"}
        else:
            message = f"Command failed with exit code {process.returncode}.\nError:\n{error}\nOutput:\n{output}"
            security_layer.audit_log("execute_command", user_role, "failure", {"command": command, "error": error, "returncode": process.returncode})
            await event_manager.publish("command_execution_end", {"command": command, "status": "error", "error": error, "output": output, "returncode": process.returncode})
            logging.error(message)
            return JSONResponse(status_code=500, content={"message": message, "error": error, "output": output, "status": "error"})
    except Exception as e:
        message = f"Error during command execution: {str(e)}"
        security_layer.audit_log("execute_command", user_role, "failure", {"command": command, "error": str(e)})
        await event_manager.publish("error", {"message": message})
        logging.error(message, exc_info=True)
        return JSONResponse(status_code=500, content={"message": message, "status": "error"})

@api_router.post("/knowledge_base/store_fact")
async def store_fact_api(request: Request, content: str = Form(...), metadata: Optional[str] = Form(None)): # Reordered arguments
    """API to store a structured fact in the knowledge base."""
    knowledge_base = request.app.state.knowledge_base
    parsed_metadata = json.loads(metadata) if metadata else None
    result = await knowledge_base.store_fact(content, parsed_metadata)
    if result["status"] == "success":
        await event_manager.publish("knowledge_base_update", {"type": "fact_stored", "fact_id": result.get("fact_id"), "content": content})
        return result
    else:
        await event_manager.publish("error", {"message": f"Failed to store fact: {result['message']}"})
        return JSONResponse(status_code=500, content=result)

@api_router.get("/chat/history")
async def get_chat_history_api(request: Request):
    """
    Retrieves the conversation history from the ChatHistoryManager.
    """
    chat_history_manager = request.app.state.chat_history_manager
    history = chat_history_manager.get_all_messages()
    total_tokens = sum(len(msg.get('text', '').split()) for msg in history)
    return {"history": history, "tokens": total_tokens}

@api_router.post("/chat/reset")
async def reset_chat_api(request: Request, user_role: str = Form("user")): # Reordered arguments
    """Clears the entire chat history."""
    security_layer = request.app.state.security_layer
    chat_history_manager = request.app.state.chat_history_manager
    if not security_layer.check_permission(user_role, "allow_chat_control"):
        security_layer.audit_log("reset_chat", user_role, "denied", {"reason": "permission_denied"})
        return JSONResponse(status_code=403, content={"message": "Permission denied to reset chat."})
    
    chat_history_manager.clear_history()
    await event_manager.publish("chat_reset", {"message": "Chat history cleared."})
    return {"message": "Chat history cleared successfully."}

@api_router.post("/chat/new")
async def new_chat_session_api(request: Request, user_role: str = Form("user")): # Reordered arguments
    """Starts a new chat session by clearing the current history."""
    security_layer = request.app.state.security_layer
    chat_history_manager = request.app.state.chat_history_manager
    if not security_layer.check_permission(user_role, "allow_chat_control"):
        security_layer.audit_log("new_chat", user_role, "denied", {"reason": "permission_denied"})
        return JSONResponse(status_code=403, content={"message": "Permission denied to start new chat."})
    
    chat_history_manager.clear_history()
    await event_manager.publish("new_chat_session", {"message": "New chat session started."})
    return {"message": "New chat session started successfully."}

@api_router.get("/chat/list_sessions")
async def list_chat_sessions_api(request: Request, user_role: str = Query("user")): # Reordered arguments
    """Lists available chat sessions."""
    security_layer = request.app.state.security_layer
    chat_history_manager = request.app.state.chat_history_manager
    if not security_layer.check_permission(user_role, "allow_chat_control"):
        security_layer.audit_log("list_chat_sessions", user_role, "denied", {"reason": "permission_denied"})
        return JSONResponse(status_code=403, content={"message": "Permission denied to list chat sessions."})
    
    sessions = chat_history_manager.list_sessions()
    return {"sessions": sessions}

@api_router.get("/chat/load_session/{session_id}")
async def load_chat_session_api(session_id: str, request: Request, user_role: str = Query("user")): # Reordered arguments
    """Loads a specific chat session."""
    security_layer = request.app.state.security_layer
    chat_history_manager = request.app.state.chat_history_manager
    if not security_layer.check_permission(user_role, "allow_chat_control"):
        security_layer.audit_log("load_chat_session", user_role, "denied", {"session_id": session_id, "reason": "permission_denied"})
        return JSONResponse(status_code=403, content={"message": "Permission denied to load chat session."})
    
    history = chat_history_manager.load_session(session_id)
    if history:
        await event_manager.publish("chat_session_loaded", {"session_id": session_id, "message": "Chat session loaded."})
        return {"message": f"Session '{session_id}' loaded successfully.", "history": history}
    else:
        return JSONResponse(status_code=404, content={"message": f"Session '{session_id}' not found."})

@api_router.post("/chat/save_session")
async def save_chat_session_api(request: Request, session_id: str = Form("default_session"), user_role: str = Form("user")): # Reordered arguments
    """Saves the current chat history as a named session."""
    security_layer = request.app.state.security_layer
    chat_history_manager = request.app.state.chat_history_manager
    if not security_layer.check_permission(user_role, "allow_chat_control"):
        security_layer.audit_log("save_chat_session", user_role, "denied", {"session_id": session_id, "reason": "permission_denied"})
        return JSONResponse(status_code=403, content={"message": "Permission denied to save chat session."})
    
    chat_history_manager.save_session(session_id)
    await event_manager.publish("chat_session_saved", {"session": session_id, "message": "Chat session saved."})
    return {"message": f"Current chat session saved as '{session_id}'."}

@app.get("/ctx_window_get")
async def get_context_window():
    """
    Retrieves the content of the LLM's context window.
    For now, this is a placeholder. In a real implementation, this would fetch
    the actual context provided to the LLM in the last interaction.
    """
    mock_context = """
System Prompt: You are an AI assistant.
Conversation History:
User: Hello, how are you?
Agent: I am an AI assistant, functioning as expected. How can I help you today?
Relevant Knowledge:
- AutoBot is an autonomous agent.
- It uses Ollama for local LLM interactions.
"""
    mock_tokens = len(mock_context.split())
    return {"content": mock_context, "tokens": mock_tokens}

@api_router.get("/knowledge_base/get_fact")
async def get_fact_api(request: Request, fact_id: Optional[int] = None, query: Optional[str] = None): # Reordered arguments
    """API to retrieve facts from the knowledge base."""
    knowledge_base = request.app.state.knowledge_base
    facts = knowledge_base.get_fact(fact_id=fact_id, query=query)
    return {"facts": facts}

@api_router.post("/knowledge_base/search")
async def search_knowledge_base_api(request: Request, query: str = Form(...), n_results: int = Form(5)): # Reordered arguments
    """API to search the vector store in the knowledge base."""
    knowledge_base = request.app.state.knowledge_base
    results = knowledge_base.search(query, n_results)
    return {"results": results}


@api_router.post("/voice/listen")
async def voice_listen_api(request: Request, user_role: str = Form("user")): # Reordered arguments
    security_layer = request.app.state.security_layer
    voice_interface = request.app.state.voice_interface
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

@api_router.post("/voice/speak")
async def voice_speak_api(request: Request, text: str = Form(...), user_role: str = Form("user")): # Reordered arguments
    """Converts text to speech and plays it."""
    security_layer = request.app.state.security_layer
    voice_interface = request.app.state.voice_interface
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

@api_router.post("/agent/pause")
async def pause_agent_api(request: Request, user_role: str = Form("user")): # Reordered arguments
    """
    Pauses the agent's current operation.
    Note: This is currently a placeholder and returns a success status without actual functionality.
    Full implementation will be added with backend integration.
    """
    security_layer = request.app.state.security_layer
    orchestrator = request.app.state.orchestrator
    if not security_layer.check_permission(user_role, "allow_agent_control"):
        security_layer.audit_log("agent_pause", user_role, "denied", {"reason": "permission_denied"})
        return JSONResponse(status_code=403, content={"message": "Permission denied to pause agent."})
    
    await orchestrator.pause_agent()
    security_layer.audit_log("agent_pause", user_role, "success", {})
    await event_manager.publish("agent_paused", {"message": "Agent operation paused."})
    return {"message": "Agent paused successfully."}

@api_router.post("/agent/resume")
async def resume_agent_api(request: Request, user_role: str = Form("user")): # Reordered arguments
    """
    Resumes the agent's operation if paused.
    Note: This is currently a placeholder and returns a success status without actual functionality.
    Full implementation will be added with backend integration.
    """
    security_layer = request.app.state.security_layer
    orchestrator = request.app.state.orchestrator
    if not security_layer.check_permission(user_role, "allow_agent_control"):
        security_layer.audit_log("agent_resume", user_role, "denied", {"reason": "permission_denied"})
        return JSONResponse(status_code=403, content={"message": "Permission denied to resume agent."})
    
    await orchestrator.resume_agent()
    security_layer.audit_log("agent_resume", user_role, "success", {})
    await event_manager.publish("agent_resumed", {"message": "Agent operation resumed."})
    return {"message": "Agent resumed successfully."}

@api_router.post("/command_approval")
async def command_approval(request: Request, payload: CommandApprovalPayload): # Reordered arguments
    """
    Receives user approval/denial for a command execution.
    """
    security_layer = request.app.state.security_layer
    main_redis_client = request.app.state.main_redis_client

    task_id = payload.task_id
    approved = payload.approved
    user_role = payload.user_role

    if not security_layer.check_permission(user_role, "allow_command_approval"):
        security_layer.audit_log("command_approval", user_role, "denied", {"task_id": task_id, "approved": approved, "reason": "permission_denied"})
        return JSONResponse(status_code=403, content={"message": "Permission denied to approve/deny commands."})

    try:
        if main_redis_client:
            approval_message = {"task_id": task_id, "approved": approved}
            main_redis_client.publish(f"command_approval_{task_id}", json.dumps(approval_message))
            logging.info(f"Published command approval for task {task_id}: Approved={approved}")
            return {"message": "Approval status received and forwarded.", "task_id": task_id, "approved": approved}
        else:
            error_message = "Redis client not initialized. Cannot process command approval."
            logging.error(error_message)
            return JSONResponse(status_code=500, content={"message": error_message})
    except Exception as e:
        logging.error(f"Error publishing command approval for task {task_id}: {e}", exc_info=True)
        return JSONResponse(status_code=500, content={"message": f"Failed to process command approval: {e}"})
