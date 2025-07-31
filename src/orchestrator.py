# src/orchestrator.py
import asyncio
import json
import redis
from typing import Dict, Any, List, Optional
import uuid
import time
import traceback
import re

from src.llm_interface import LLMInterface
from src.event_manager import event_manager
from src.knowledge_base import KnowledgeBase
from src.worker_node import WorkerNode, GUI_AUTOMATION_SUPPORTED
from src.diagnostics import Diagnostics
from src.system_info_collector import get_os_info
from src.tool_discovery import discover_tools
from src.tools import ToolRegistry

# Import the centralized ConfigManager
from src.config import config as global_config_manager

# Import LangChain Agent (optional)
try:
    from src.langchain_agent_orchestrator import LangChainAgentOrchestrator
    LANGCHAIN_AVAILABLE = True
except ImportError:
    LangChainAgentOrchestrator = None
    LANGCHAIN_AVAILABLE = False
    print("WARNING: LangChain Agent not available. Using standard orchestrator only.")

class Orchestrator:
    def __init__(self):
        # Remove config_path and direct config loading
        self.llm_interface = LLMInterface() # Will update LLMInterface to use global_config_manager
        self.knowledge_base = KnowledgeBase() # Will update KnowledgeBase to use global_config_manager
        self.diagnostics = Diagnostics() # Will update Diagnostics to use global_config_manager
        
        llm_config = global_config_manager.get_llm_config()
        self.orchestrator_llm_model = llm_config.get('orchestrator_llm', 'phi:2.7b')
        self.task_llm_model = llm_config.get('task_llm', 'ollama')
        self.ollama_models = llm_config.get('ollama', {}).get('models', {})
        self.phi2_enabled = False # This will be driven by config if needed

        self.task_transport_type = global_config_manager.get_nested('task_transport.type', 'local')
        self.redis_client = None
        self.worker_capabilities: Dict[str, Dict[str, Any]] = {}
        self.pending_approvals: Dict[str, asyncio.Future] = {}
        self.redis_command_approval_request_channel = global_config_manager.get_nested('task_transport.redis.channels.command_approval_request', 'command_approval_request')
        self.redis_command_approval_response_channel_prefix = global_config_manager.get_nested('task_transport.redis.channels.command_approval_response_prefix', 'command_approval_')
        
        self.agent_paused = False
        
        self.langchain_agent = None
        self.use_langchain = global_config_manager.get_nested('orchestrator.use_langchain', False)

        if self.task_transport_type == "redis":
            redis_transport_config = global_config_manager.get_nested('task_transport.redis', {})
            redis_host = redis_transport_config.get('host', 'localhost')
            redis_port = redis_transport_config.get('port', 6379)
            try:
                self.redis_client = redis.Redis(host=redis_host, port=redis_port, decode_responses=True)
                self.redis_client.ping() # Test connection immediately
                print(f"Orchestrator connected to Redis at {redis_host}:{redis_port}")
            except redis.ConnectionError as e:
                print(f"Orchestrator failed to connect to Redis at {redis_host}:{redis_port}: {e}. Falling back to local task transport.")
                self.redis_client = None
                self.task_transport_type = "local" # Fallback to local if Redis fails
                self.local_worker = WorkerNode()
        
        if self.task_transport_type == "local":
            print("Orchestrator configured for local task transport.")
            self.local_worker = WorkerNode()
        
        # Initialize unified tool registry to eliminate code duplication
        self.tool_registry = None

    async def _listen_for_worker_capabilities(self):
        print("Listening for worker capabilities (Redis transport)...")
        await asyncio.sleep(1)

    async def _listen_for_command_approvals(self):
        if not self.redis_client:
            print("Redis client not available for command approval listening")
            return
            
        pubsub = self.redis_client.pubsub()
        approval_channel_pattern = f"{self.redis_command_approval_response_channel_prefix}*"
        pubsub.psubscribe(approval_channel_pattern)
        print(f"Listening for command approvals on Redis channel '{approval_channel_pattern}'...")
        for message in pubsub.listen():
            if message['type'] == 'pmessage':
                channel = message['channel'].decode('utf-8')
                data = json.loads(message['data'])
                task_id = data.get('task_id')
                approved = data.get('approved')
                
                if task_id and task_id in self.pending_approvals:
                    future = self.pending_approvals.pop(task_id)
                    if not future.done():
                        future.set_result({"approved": approved})
                    print(f"Received approval for task {task_id}: Approved={approved}")
                else:
                    print(f"Received unhandled approval message for task {task_id}: {data}")

    async def startup(self):
        ollama_connected = await self.llm_interface.check_ollama_connection()
        if ollama_connected:
            await event_manager.publish("llm_status", {"status": "connected", "model": self.llm_interface.orchestrator_llm_alias})
            print(f"LLM ({self.llm_interface.orchestrator_llm_alias}) connected successfully.")
        else:
            await event_manager.publish("llm_status", {"status": "disconnected", "model": self.llm_interface.orchestrator_llm_alias, "message": "Failed to connect to Ollama or configured models not found."})
            print(f"LLM ({self.llm_interface.orchestrator_llm_alias}) connection failed.")

        if self.task_transport_type == "redis" and self.redis_client:
            asyncio.create_task(self._listen_for_worker_capabilities())
        elif self.task_transport_type == "local" and hasattr(self, 'local_worker'):
            await self.local_worker.report_capabilities()
        
        self.system_info = get_os_info()
        await event_manager.publish("log_message", {"level": "INFO", "message": f"System information collected: {json.dumps(self.system_info, indent=2)}"})
        print("System information collected on startup.")

        self.available_tools = discover_tools()
        await event_manager.publish("log_message", {"level": "INFO", "message": f"Available tools collected: {json.dumps(self.available_tools, indent=2)}"})
        print("Available tools collected on startup.")
        
        # Initialize unified tool registry to eliminate code duplication
        worker_node = self.local_worker if hasattr(self, 'local_worker') else None
        self.tool_registry = ToolRegistry(worker_node=worker_node, knowledge_base=self.knowledge_base)
        
        if self.use_langchain and LANGCHAIN_AVAILABLE and LangChainAgentOrchestrator is not None:
            try:
                kb_config = global_config_manager.get('knowledge_base', {})
                if kb_config.get('provider') == 'disabled':
                    print("Knowledge Base disabled in configuration. Skipping LangChain KB initialization.")
                    self.knowledge_base = None
                # KnowledgeBase.ainit() is now called in main.py's lifespan startup, no need to call it here.
                
                self.langchain_agent = LangChainAgentOrchestrator(
                    config=global_config_manager.to_dict(), # Pass the full config dict
                    worker_node=self.local_worker if hasattr(self, 'local_worker') else None,
                    knowledge_base=self.knowledge_base
                )
                
                if self.langchain_agent.available:
                    print("LangChain Agent initialized successfully.")
                    await event_manager.publish("log_message", {"level": "INFO", "message": "LangChain Agent initialized successfully."})
                else:
                    print("LangChain Agent initialization failed.")
                    self.langchain_agent = None
                    self.use_langchain = False
            except Exception as e:
                print(f"Failed to initialize LangChain Agent: {e}")
                await event_manager.publish("log_message", {"level": "ERROR", "message": f"Failed to initialize LangChain Agent: {e}"})
                self.langchain_agent = None
                self.use_langchain = False
        else:
            kb_config = global_config_manager.get('knowledge_base', {})
            if kb_config.get('provider') == 'disabled':
                print("Knowledge Base disabled in configuration. Skipping initialization.")
                self.knowledge_base = None
            # KnowledgeBase.ainit() is now called in main.py's lifespan startup, no need to call it here.

    def set_phi2_enabled(self, enabled: bool):
        self.phi2_enabled = enabled
        print(f"Phi-2 enabled status set to: {self.phi2_enabled}")
        asyncio.create_task(event_manager.publish("settings_update", {"phi2_enabled": enabled}))

    async def pause_agent(self):
        self.agent_paused = True
        await event_manager.publish("log_message", {"level": "INFO", "message": "Agent paused"})
        print("Agent paused")

    async def resume_agent(self):
        self.agent_paused = False
        await event_manager.publish("log_message", {"level": "INFO", "message": "Agent resumed"})
        print("Agent resumed")

    async def generate_task_plan(self, goal: str, messages: Optional[List[Dict[str, str]]] = None) -> Dict[str, Any]:
        if messages is None:
            messages = [{"role": "user", "content": goal}]
        target_llm_model = self.orchestrator_llm_model
        orchestrator_settings = self.llm_interface.orchestrator_llm_settings
        
        await event_manager.publish("log_message", {"level": "INFO", "message": f"Generating plan using Orchestrator LLM: {target_llm_model}"})
        print(f"Generating plan using Orchestrator LLM: {target_llm_model}")

        retrieved_context = []
        if self.knowledge_base is not None:
            retrieved_context = await self.knowledge_base.search(goal, n_results=global_config_manager.get_nested('knowledge_base.search_results_limit', 3)) # Use config for n_results
        
        context_str = ""
        if retrieved_context:
            context_str = "\n\nRelevant Context from Knowledge Base:\n"
            for i, item in enumerate(retrieved_context):
                context_str += f"--- Document: {item['metadata'].get('filename', 'N/A')} (Chunk {item['metadata'].get('chunk_index', 'N/A')}) ---\n"
                context_str += item['content'] + "\n"
            await event_manager.publish("log_message", {"level": "INFO", "message": f"Retrieved {len(retrieved_context)} context chunks."})
        else:
            await event_manager.publish("log_message", {"level": "INFO", "message": "No relevant context found in knowledge base."})
        
        system_prompt_parts = [
            self.llm_interface.orchestrator_system_prompt,
            "You have access to the following tools. You MUST use these tools to achieve the user's goal. Each item below is a tool you can directly instruct to use. Do NOT list the tool descriptions, only the tool names and their parameters as shown below:",
        ]

        if self.task_transport_type == "local" and GUI_AUTOMATION_SUPPORTED:
            system_prompt_parts.append("""- GUI Automation:
    - 'Type text "TEXT" into active window.'
    - 'Click element "IMAGE_PATH".'
    - 'Read text from region (X, Y, WIDTH, HEIGHT).'
    - 'Bring window to front "APP_TITLE".'""")
        else:
            system_prompt_parts.append("- GUI Automation: (Not available in this environment. Will be simulated as shell commands.)")

        system_prompt_parts.append("""- System Integration:
    - 'Query system information.'
    - 'List system services.'
    - 'Manage service "SERVICE_NAME" action "start|stop|restart".'
    - 'Execute system command "COMMAND".'
    - 'Get process info for "PROCESS_NAME" or PID "PID".'
    - 'Terminate process with PID "PID".'
    - 'Fetch web content from URL "URL".'
- Knowledge Base:
    - 'Add file "FILE_PATH" of type "FILE_TYPE" to knowledge base with metadata {JSON_METADATA}.'
    - 'Search knowledge base for "QUERY" with N results.'
    - 'Store fact "CONTENT" with metadata {JSON_METADATA}.'
    - 'Get fact by ID "ID" or query "QUERY".'
- User Interaction:
    - 'Ask user for manual for program "PROGRAM_NAME" with question "QUESTION_TEXT".'
    - 'Ask user for approval to run command "COMMAND_TO_APPROVE".'

Prioritize using the most specific tool for the job. For example, use 'Manage service "SERVICE_NAME" action "start|stop|restart".' for services, 'Query system information.' for system details, and 'Type text "TEXT" into active window.' for GUI typing, rather than 'Execute system command "COMMAND".' if a more specific tool exists.

IMPORTANT: When a tool is executed, its output will be provided to you with the role `tool_output`. You MUST use the actual, factual content from these `tool_output` messages to inform your subsequent actions and responses. Do NOT hallucinate or invent information. If the user asks a question that was answered by a tool, directly use the tool's output in your response.

If the user's request is purely conversational and does not require a tool, respond using the 'respond_conversationally' tool. Do NOT generate unrelated content or puzzles. Focus solely on the user's current goal and the information provided by tools.
""")
        system_prompt = "\n".join(system_prompt_parts)

        if context_str:
            system_prompt += f"\n\nUse the following context to inform your plan:\n{context_str}"
        
        system_prompt += f"\n\nOperating System Information:\n{json.dumps(self.system_info, indent=2)}\n"
        system_prompt += f"\n\nAvailable System Tools:\n{json.dumps(self.available_tools, indent=2)}\n"

        full_messages = [{"role": "system", "content": system_prompt}] + messages
        
        response = await self.llm_interface.chat_completion(
            messages=full_messages,
            llm_type="orchestrator",
            temperature=orchestrator_settings.get('temperature', 0.7),
            **{k: v for k, v in orchestrator_settings.items() if k not in ['system_prompt', 'temperature', 'sampling_strategy', 'structured_output']}
        )
        
        print(f"Raw LLM response from chat_completion: {response}")
        await event_manager.publish("log_message", {"level": "DEBUG", "message": f"Raw LLM response: {response}"})

        llm_raw_content = None
        if isinstance(response, dict):
            if 'message' in response and isinstance(response['message'], dict) and 'content' in response['message']:
                llm_raw_content = response['message']['content']
            elif 'choices' in response and isinstance(response['choices'], list) and len(response['choices']) > 0 and \
                 'message' in response['choices'][0] and isinstance(response['choices'][0]['message'], dict) and \
                 'content' in response['choices'][0]['message']:
                llm_raw_content = response['choices'][0]['message']['content']

        if llm_raw_content:
            try:
                parsed_content = json.loads(llm_raw_content)
                if isinstance(parsed_content, dict) and "tool_name" in parsed_content and "tool_args" in parsed_content:
                    return parsed_content
                else:
                    print(f"LLM returned unexpected JSON (not a tool call). Treating as conversational: {llm_raw_content}")
                    return {
                        "thoughts": ["The LLM returned unexpected JSON. Responding conversationally with the raw JSON."],
                        "tool_name": "respond_conversationally",
                        "tool_args": {"response_text": llm_raw_content}
                    }
            except json.JSONDecodeError:
                print(f"LLM response is plain text. Treating as conversational: {llm_raw_content}")
                return {
                    "thoughts": ["The user's request does not require a tool. Responding conversationally."],
                    "tool_name": "respond_conversationally",
                    "tool_args": {"response_text": llm_raw_content}
                }
        
        error_message = "Failed to generate an action from Orchestrator LLM. No content received."
        await event_manager.publish("error", {"message": error_message})
        print(error_message)
        return {"tool_name": "respond_conversationally", "tool_args": {"response_text": error_message}}

    async def execute_goal(self, goal: str, messages: Optional[List[Dict[str, str]]] = None) -> Dict[str, Any]:
        """Execute a goal using an iterative approach with the orchestrator LLM."""
        if messages is None:
            messages = [{"role": "user", "content": goal}]
        
        await event_manager.publish("log_message", {"level": "INFO", "message": f"Starting goal execution: {goal}"})
        print(f"Starting goal execution: {goal}")
        
        if self.use_langchain and self.langchain_agent and hasattr(self.langchain_agent, 'available') and self.langchain_agent.available:
            try:
                await event_manager.publish("log_message", {"level": "INFO", "message": "Using LangChain Agent for goal execution"})
                print("Using LangChain Agent for goal execution")
                return await self.langchain_agent.execute_goal(goal, messages)
            except Exception as e:
                await event_manager.publish("log_message", {"level": "ERROR", "message": f"LangChain Agent failed, falling back to standard orchestrator: {e}"})
                print(f"LangChain Agent failed, falling back to standard orchestrator: {e}")
        
        if self._is_simple_command(goal):
            simple_command_result = await self._execute_simple_command(goal)
            print(f"DEBUG: Simple command handled directly. Returning result: {simple_command_result}")
            return simple_command_result
        
        max_iterations = global_config_manager.get_nested('orchestrator.max_iterations', 10) # Get from config
        iteration = 0
        
        while iteration < max_iterations:
            if self.agent_paused:
                await event_manager.publish("log_message", {"level": "INFO", "message": "Agent is paused, waiting for resume..."})
                print("Agent is paused, waiting for resume...")
                await asyncio.sleep(1)
                continue
                
            iteration += 1
            await event_manager.publish("log_message", {"level": "INFO", "message": f"Iteration {iteration}/{max_iterations}"})
            print(f"Iteration {iteration}/{max_iterations}")
            
            action = await self.generate_task_plan(goal, messages)
            
            if not action:
                await event_manager.publish("error", {"message": "Failed to generate action plan"})
                print("Failed to generate action plan")
                return {"status": "error", "message": "Failed to generate action plan."}
            
            tool_name = action.get("tool_name")
            tool_args = action.get("tool_args", {})
            thoughts = action.get("thoughts", [])
            
            if thoughts:
                thoughts_text = " ".join(thoughts) if isinstance(thoughts, list) else str(thoughts)
                await event_manager.publish("log_message", {"level": "INFO", "message": f"AI Thoughts: {thoughts_text}"})
                print(f"AI Thoughts: {thoughts_text}")
            
            await event_manager.publish("log_message", {"level": "INFO", "message": f"Executing tool: {tool_name} with args: {tool_args}"})
            print(f"Executing tool: {tool_name} with args: {tool_args}")
            
            if not isinstance(tool_name, str):
                error_msg = f"Invalid tool_name received from LLM: {tool_name}. Expected string."
                await event_manager.publish("error", {"message": error_msg})
                messages.append({"role": "user", "content": f"Tool execution failed: {error_msg}"})
                continue
            
            # Use unified tool registry to eliminate code duplication
            try:
                if self.tool_registry:
                    result = await self.tool_registry.execute_tool(tool_name, tool_args)
                else:
                    result = {"status": "error", "message": "Tool registry not initialized"}
                
                tool_output_content = result.get("result", result.get("output", result.get("message", "Tool execution completed.")))
                messages.append({"role": "tool_output", "content": tool_output_content})
                
                if result.get("status") == "success":
                    if tool_name == "respond_conversationally":
                        result_content = result.get("response_text", result.get("result", result.get("output", result.get("message", "Task completed successfully"))))
                    else:
                        result_content = result.get("result", result.get("output", result.get("message", "Task completed successfully")))
                    
                    await event_manager.publish("llm_response", {"response": result_content})
                    await event_manager.publish("log_message", {"level": "INFO", "message": f"Tool execution successful: {result_content}"})
                    print(f"Tool execution successful: {result_content}")
                    
                    if tool_name == "respond_conversationally":
                        await event_manager.publish("log_message", {"level": "INFO", "message": "Goal execution completed with conversational response"})
                        print("Goal execution completed with conversational response")
                        return {"tool_name": "respond_conversationally", "tool_args": {"response_text": result_content}, "response_text": result_content}
                        
                elif result.get("status") == "pending_approval":
                    approval_result = await self._handle_command_approval(result)
                    if approval_result.get("approved"):
                        continue
                    else:
                        messages.append({"role": "user", "content": "User declined to approve the command. Please suggest an alternative approach."})
                        continue
                        
                else:
                    error_msg = result.get("message", "Unknown error occurred")
                    messages.append({"role": "user", "content": f"Tool execution failed: {error_msg}"})
                    await event_manager.publish("error", {"message": error_msg})
                    print(f"Tool execution failed: {error_msg}")
                    
            except Exception as e:
                error_msg = f"Exception during tool execution: {str(e)}"
                messages.append({"role": "user", "content": error_msg})
                await event_manager.publish("error", {"message": error_msg})
                print(error_msg)
                traceback.print_exc()
        
        await event_manager.publish("log_message", {"level": "WARNING", "message": f"Goal execution completed after {max_iterations} iterations"})
        print(f"Goal execution completed after {max_iterations} iterations")
        return {"status": "warning", "message": "Goal execution completed, but may not have fully achieved the objective."}

    def _is_simple_command(self, goal: str) -> bool:
        command_patterns = [
            r"use\s+(\w+)\s+to\s+get",
            r"run\s+(\w+)",
            r"execute\s+(\w+)",
            r"(\w+)\s+command",
            r"get.*ip.*address",
            r"show.*network",
            r"list.*processes",
            r"ifconfig",
            r"ip\s+addr"
        ]
        is_simple = any(re.search(pattern, goal.lower()) for pattern in command_patterns)
        print(f"DEBUG: _is_simple_command('{goal}') -> {is_simple}")
        return is_simple

    async def _execute_simple_command(self, goal: str) -> Dict[str, Any]:
        command = None
        if "ifconfig" in goal.lower():
            command = "ifconfig"
        elif "ip addr" in goal.lower() or "ip address" in goal.lower():
            command = "ip addr show"
        elif "ps" in goal.lower() and "process" in goal.lower():
            command = "ps aux"
        elif "netstat" in goal.lower():
            command = "netstat -tuln"
        
        print(f"DEBUG: _execute_simple_command called for goal: '{goal}', determined command: '{command}'")

        if command:
            await event_manager.publish("log_message", {"level": "INFO", "message": f"Executing simple command: {command}"})
            
            task = {
                "task_id": str(uuid.uuid4()),
                "type": "system_execute_command",
                "command": command,
                "user_role": "user",
                "timestamp": time.time()
            }
            
            result = await self.local_worker.execute_task(task)
            
            await event_manager.publish("log_message", {"level": "INFO", "message": f"Result from worker for simple command '{command}': {json.dumps(result, indent=2)}"})
            print(f"Result from worker for simple command '{command}': {json.dumps(result, indent=2)}")

            if result.get("status") == "success":
                return {
                    "tool_name": "execute_system_command",
                    "tool_args": {
                        "command": command,
                        "output": result.get("output", "Command executed successfully"),
                        "status": "success"
                    }
                }
            else:
                error_msg = result.get("message", "Command execution failed")
                return {
                    "tool_name": "execute_system_command",
                    "tool_args": {
                        "command": command,
                        "error": error_msg,
                        "output": result.get("output", ""),
                        "status": "error"
                    }
                }
        
        print(f"DEBUG: _execute_simple_command could not determine a direct command for '{goal}'. Falling back to generate_task_plan.")
        return await self.generate_task_plan(goal, [{"role": "user", "content": goal}])

    async def _handle_command_approval(self, result):
        command = result.get("command")
        task_id = result.get("task_id")
        
        if not command or not task_id:
            return {"approved": False, "message": "Invalid approval request"}
        
        await event_manager.publish("log_message", {"level": "INFO", "message": f"Requesting approval for command: {command}"})
        print(f"Requesting approval for command: {command}")
        
        if self.task_transport_type == "redis":
            approval_future = asyncio.Future()
            self.pending_approvals[task_id] = approval_future
            
            approval_request = {
                "task_id": task_id,
                "command": command,
                "timestamp": time.time()
            }
            if self.redis_client:
                self.redis_client.publish(self.redis_command_approval_request_channel, json.dumps(approval_request))
            else:
                await event_manager.publish("error", {"message": "Redis client not initialized for command approval."})
                return {"approved": False, "message": "Redis client not available for approval."}
            
            try:
                approval_response = await asyncio.wait_for(approval_future, timeout=300)
                return approval_response
            except asyncio.TimeoutError:
                self.pending_approvals.pop(task_id, None)
                await event_manager.publish("error", {"message": f"Command approval timeout for: {command}"})
                return {"approved": False, "message": "Approval timeout"}
        else:
            await event_manager.publish("log_message", {"level": "WARNING", "message": "Local approval mechanism not implemented, auto-approving"})
            return {"approved": True, "message": "Auto-approved for local execution"}

    async def generate_next_action(self, goal: str, messages: Optional[List[Dict[str, str]]]):
        return await self.generate_task_plan(goal, messages)

# Removed example usage block
