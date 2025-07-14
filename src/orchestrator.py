# src/orchestrator.py
import os
import yaml
import asyncio
import json
import redis
from typing import Dict, Any, List, Optional
import uuid
import time
import traceback
import re # Import re

from src.llm_interface import LLMInterface
from src.event_manager import event_manager
from src.knowledge_base import KnowledgeBase
from src.worker_node import WorkerNode, GUI_AUTOMATION_SUPPORTED # Import GUI_AUTOMATION_SUPPORTED
from src.diagnostics import Diagnostics
from src.system_info_collector import get_os_info # Import the system info collector
from src.tool_discovery import discover_tools # Import the tool discovery function

# Import LangChain Agent (optional)
try:
    from src.langchain_agent_orchestrator import LangChainAgentOrchestrator
    LANGCHAIN_AVAILABLE = True
except ImportError:
    LangChainAgentOrchestrator = None  # type: ignore
    LANGCHAIN_AVAILABLE = False
    print("WARNING: LangChain Agent not available. Using standard orchestrator only.")

class Orchestrator:
    def __init__(self, config_path="config/config.yaml"):
        self.config_path = config_path
        self.config = self._load_config(config_path)
        self.llm_interface = LLMInterface(config_path)
        self.knowledge_base = KnowledgeBase(config_path)
        self.diagnostics = Diagnostics(config_path) # Initialize Diagnostics
        self.orchestrator_llm_model = self.config['llm_config']['default_llm'] # Renamed for clarity
        self.task_llm_model = self.config['llm_config']['task_llm'] # New: Task LLM
        self.ollama_models = self.config['llm_config']['ollama']['models']
        self.phi2_enabled = False # This might need to be re-evaluated if phi2 is specifically the task LLM

        self.task_transport_type = self.config['task_transport']['type']
        self.redis_client = None
        self.worker_capabilities: Dict[str, Dict[str, Any]] = {}
        self.pending_approvals: Dict[str, asyncio.Future] = {} # Store Futures for pending approvals
        
        # Initialize agent state
        self.agent_paused = False
        
        # Initialize LangChain Agent if available
        self.langchain_agent = None
        self.use_langchain = self.config.get('orchestrator', {}).get('use_langchain', False)

        if self.task_transport_type == "redis":
            redis_host = self.config['task_transport']['redis']['host']
            redis_port = self.config['task_transport']['redis']['port']
            self.redis_client = redis.Redis(host=redis_host, port=redis_port, decode_responses=True)
            print(f"Orchestrator connected to Redis at {redis_host}:{redis_port}")
            asyncio.create_task(self._listen_for_command_approvals()) # Start listening for approvals
        else:
            print("Orchestrator configured for local task transport.")
            self.local_worker = WorkerNode(config_path)

    async def _listen_for_worker_capabilities(self):
        """Listens for worker capabilities reports on Redis."""
        # This is a placeholder for actual Redis pub/sub logic for worker capabilities
        print("Listening for worker capabilities (Redis transport)...")
        # Example: pubsub = self.redis_client.pubsub()
        # pubsub.subscribe('worker_capabilities')
        # for message in pubsub.listen():
        #     if message['type'] == 'message':
        #         worker_info = json.loads(message['data'])
        #         self.worker_capabilities[worker_info['worker_id']] = worker_info
        #         print(f"Received capabilities from worker: {worker_info['worker_id']}")
        await asyncio.sleep(1) # Simulate listening

    async def _listen_for_command_approvals(self):
        """Listens for command approval messages from the GUI via Redis."""
        if not self.redis_client:
            print("Redis client not available for command approval listening")
            return
            
        pubsub = self.redis_client.pubsub()
        # Subscribe to a pattern for command approvals, e.g., "command_approval_*"
        pubsub.psubscribe("command_approval_*") 
        print("Listening for command approvals on Redis channel 'command_approval_*'...")
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
        """Performs asynchronous startup tasks for the Orchestrator."""
        # Check Ollama connection status on startup
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
        
        # Collect system information on startup
        self.system_info = get_os_info()
        await event_manager.publish("log_message", {"level": "INFO", "message": f"System information collected: {json.dumps(self.system_info, indent=2)}"})
        print("System information collected on startup.")

        # Collect available tools on startup
        self.available_tools = discover_tools()
        await event_manager.publish("log_message", {"level": "INFO", "message": f"Available tools collected: {json.dumps(self.available_tools, indent=2)}"})
        print("Available tools collected on startup.")
        
        # Initialize LangChain Agent if configured and available
        if self.use_langchain and LANGCHAIN_AVAILABLE and LangChainAgentOrchestrator is not None:
            try:
                # Initialize knowledge base first
                llm_config_for_kb = self.config.get('llm_config', {}) # Corrected: use 'llm_config'
                await self.knowledge_base.ainit(llm_config_for_kb)
                
                # Initialize LangChain Agent
                self.langchain_agent = LangChainAgentOrchestrator(
                    config=self.config,
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
            # Initialize knowledge base with current LLM config
            llm_config_for_kb = self.config.get('llm_config', {}) # Corrected: use 'llm_config'
            await self.knowledge_base.ainit(llm_config_for_kb)

    def _load_config(self, config_path):
        with open(config_path, 'r') as f:
            return yaml.safe_load(f)

    def set_phi2_enabled(self, enabled: bool): # This function might become obsolete or need re-purposing
        self.phi2_enabled = enabled
        print(f"Phi-2 enabled status set to: {self.phi2_enabled}")
        asyncio.create_task(event_manager.publish("settings_update", {"phi2_enabled": enabled}))

    async def pause_agent(self):
        """Pause the agent from processing new tasks."""
        self.agent_paused = True
        await event_manager.publish("log_message", {"level": "INFO", "message": "Agent paused"})
        print("Agent paused")

    async def resume_agent(self):
        """Resume the agent to process tasks."""
        self.agent_paused = False
        await event_manager.publish("log_message", {"level": "INFO", "message": "Agent resumed"})
        print("Agent resumed")

    async def generate_task_plan(self, goal: str, messages: Optional[List[Dict[str, str]]] = None) -> Dict[str, Any]:
        if messages is None:
            messages = [{"role": "user", "content": goal}]
        # Always use the orchestrator LLM for planning
        target_llm_model = self.orchestrator_llm_model
        orchestrator_settings = self.llm_interface.orchestrator_llm_settings
        
        await event_manager.publish("log_message", {"level": "INFO", "message": f"Generating plan using Orchestrator LLM: {target_llm_model}"})
        print(f"Generating plan using Orchestrator LLM: {target_llm_model}")

        retrieved_context = await self.knowledge_base.search(goal, n_results=3)
        context_str = ""
        if retrieved_context:
            context_str = "\n\nRelevant Context from Knowledge Base:\n"
            for i, item in enumerate(retrieved_context):
                context_str += f"--- Document: {item['metadata'].get('filename', 'N/A')} (Chunk {item['metadata'].get('chunk_index', 'N/A')}) ---\n"
                context_str += item['content'] + "\n"
            await event_manager.publish("log_message", {"level": "INFO", "message": f"Retrieved {len(retrieved_context)} context chunks."})
        else:
            await event_manager.publish("log_message", {"level": "INFO", "message": "No relevant context found in knowledge base."})
        
        # Use the system prompt loaded from file
        system_prompt_parts = [
            self.llm_interface.orchestrator_system_prompt,
            "You have access to the following tools. You MUST use these tools to achieve the user's goal. Each item below is a tool you can directly instruct to use. Do NOT list the tool descriptions, only the tool names and their parameters as shown below:",
        ]

        # Conditionally add GUI Automation capabilities
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

        # Combine system prompt with current conversation history
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
                    # If it's JSON but not a valid tool call, treat as conversational
                    print(f"LLM returned unexpected JSON (not a tool call). Treating as conversational: {llm_raw_content}")
                    return {
                        "thoughts": ["The LLM returned unexpected JSON. Responding conversationally with the raw JSON."],
                        "tool_name": "respond_conversationally",
                        "tool_args": {"response_text": llm_raw_content}
                    }
            except json.JSONDecodeError:
                # If JSON parsing fails, it's plain text, treat as conversational
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
        
        # Use LangChain Agent if available and configured
        if self.use_langchain and self.langchain_agent and hasattr(self.langchain_agent, 'available') and self.langchain_agent.available:
            try:
                await event_manager.publish("log_message", {"level": "INFO", "message": "Using LangChain Agent for goal execution"})
                print("Using LangChain Agent for goal execution")
                return await self.langchain_agent.execute_goal(goal, messages)
            except Exception as e:
                await event_manager.publish("log_message", {"level": "ERROR", "message": f"LangChain Agent failed, falling back to standard orchestrator: {e}"})
                print(f"LangChain Agent failed, falling back to standard orchestrator: {e}")
                # Fall through to standard orchestrator
        
        # Simple command detection for direct execution
        if self._is_simple_command(goal):
            simple_command_result = await self._execute_simple_command(goal)
            # If a simple command was handled, return its result immediately
            # This result is already a structured response (tool_name, tool_args)
            print(f"DEBUG: Simple command handled directly. Returning result: {simple_command_result}")
            return simple_command_result
        
        max_iterations = 10  # Prevent infinite loops
        iteration = 0
        
        while iteration < max_iterations:
            # Check if agent is paused
            if self.agent_paused:
                await event_manager.publish("log_message", {"level": "INFO", "message": "Agent is paused, waiting for resume..."})
                print("Agent is paused, waiting for resume...")
                await asyncio.sleep(1)
                continue
                
            iteration += 1
            await event_manager.publish("log_message", {"level": "INFO", "message": f"Iteration {iteration}/{max_iterations}"})
            print(f"Iteration {iteration}/{max_iterations}")
            
            # Generate the next action using the orchestrator LLM
            action = await self.generate_task_plan(goal, messages)
            
            if not action:
                await event_manager.publish("error", {"message": "Failed to generate action plan"})
                print("Failed to generate action plan")
                return {"status": "error", "message": "Failed to generate action plan."}
            
            # Extract tool information
            tool_name = action.get("tool_name")
            tool_args = action.get("tool_args", {})
            thoughts = action.get("thoughts", [])
            
            if thoughts:
                thoughts_text = " ".join(thoughts) if isinstance(thoughts, list) else str(thoughts)
                await event_manager.publish("log_message", {"level": "INFO", "message": f"AI Thoughts: {thoughts_text}"})
                print(f"AI Thoughts: {thoughts_text}")
            
            await event_manager.publish("log_message", {"level": "INFO", "message": f"Executing tool: {tool_name} with args: {tool_args}"})
            print(f"Executing tool: {tool_name} with args: {tool_args}")
            
            # Ensure tool_name is a string before mapping
            if not isinstance(tool_name, str):
                error_msg = f"Invalid tool_name received from LLM: {tool_name}. Expected string."
                await event_manager.publish("error", {"message": error_msg})
                messages.append({"role": "user", "content": f"Tool execution failed: {error_msg}"})
                continue # Continue to next iteration to allow LLM to correct
            
            # Map tool names to actual task types
            mapped_task = self._map_tool_to_task(tool_name, tool_args)
            
            # Execute the tool
            try:
                if self.task_transport_type == "local":
                    result = await self.local_worker.execute_task(mapped_task)
                else:
                    # Redis-based execution would go here
                    result = {"status": "error", "message": "Redis execution not implemented"}
                
                # Add the action and result to conversation history
                # IMPORTANT: Ensure the actual tool output is added to messages for context
                tool_output_content = result.get("result", result.get("output", result.get("message", "Tool execution completed.")))
                messages.append({"role": "tool_output", "content": tool_output_content}) # Use a specific role for tool output
                
                if result.get("status") == "success":
                    # For conversational responses, prioritize response_text
                    if tool_name == "respond_conversationally":
                        result_content = result.get("response_text", result.get("result", result.get("output", result.get("message", "Task completed successfully"))))
                    else:
                        result_content = result.get("result", result.get("output", result.get("message", "Task completed successfully")))
                    
                    await event_manager.publish("llm_response", {"response": result_content})
                    await event_manager.publish("log_message", {"level": "INFO", "message": f"Tool execution successful: {result_content}"})
                    print(f"Tool execution successful: {result_content}")
                    
                    # Check if this was a conversational response (goal complete)
                    if tool_name == "respond_conversationally":
                        await event_manager.publish("log_message", {"level": "INFO", "message": "Goal execution completed with conversational response"})
                        print("Goal execution completed with conversational response")
                        return {"tool_name": "respond_conversationally", "tool_args": {"response_text": result_content}, "response_text": result_content}
                        
                elif result.get("status") == "pending_approval":
                    # Handle command approval flow
                    approval_result = await self._handle_command_approval(result)
                    if approval_result.get("approved"):
                        # Re-execute the command with approval
                        continue
                    else:
                        messages.append({"role": "user", "content": "User declined to approve the command. Please suggest an alternative approach."})
                        continue
                        
                else:
                    error_msg = result.get("message", "Unknown error occurred")
                    messages.append({"role": "user", "content": f"Tool execution failed: {error_msg}"})
                    await event_manager.publish("error", {"message": f"Tool execution failed: {error_msg}"})
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
        """Check if the goal is a simple system command that can be executed directly."""
        command_patterns = [
            r"use\s+(\w+)\s+to\s+get",
            r"run\s+(\w+)",
            r"execute\s+(\w+)",
            r"(\w+)\s+command",
            r"get.*ip.*address",
            r"show.*network",
            r"list.*processes",
            r"ifconfig", # Explicitly match "ifconfig"
            r"ip\s+addr" # Explicitly match "ip addr"
        ]
        is_simple = any(re.search(pattern, goal.lower()) for pattern in command_patterns)
        print(f"DEBUG: _is_simple_command('{goal}') -> {is_simple}")
        return is_simple

    async def _execute_simple_command(self, goal: str) -> Dict[str, Any]:
        """Execute simple commands directly without LLM planning."""
        # Extract command from goal
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
                # Return the raw result of the system command execution
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
                # Return the raw error result of the system command execution
                return {
                    "tool_name": "execute_system_command",
                    "tool_args": {
                        "command": command,
                        "error": error_msg,
                        "output": result.get("output", ""), # Include any partial output
                        "status": "error"
                    }
                }
        
        # Fallback to normal LLM processing
        # If a simple command is not directly handled, let the main execution flow handle it.
        # This will lead to generate_task_plan being called.
        print(f"DEBUG: _execute_simple_command could not determine a direct command for '{goal}'. Falling back to generate_task_plan.")
        return await self.generate_task_plan(goal, [{"role": "user", "content": goal}])

    def _map_tool_to_task(self, tool_name: Optional[str], tool_args: dict) -> dict:
        """Map orchestrator tool names to worker node task types."""
        task_id = str(uuid.uuid4())
        base_task = {
            "task_id": task_id,
            "user_role": "user",
            "timestamp": time.time()
        }
        
        if not isinstance(tool_name, str): # Handle None or non-string tool_name
            return {
                "type": "respond_conversationally",
                "response_text": f"Error: Invalid tool name received: {tool_name}. Cannot execute task."
            }

        # Map tool names to actual task types
        if tool_name == "execute_system_command" or tool_name == "system_execute_command":
            base_task.update({
                "type": "system_execute_command",
                "command": tool_args.get("command", tool_args.get("COMMAND", ""))
            })
        elif tool_name == "query_system_information" or tool_name == "system_query_info":
            base_task.update({"type": "system_query_info"})
        elif tool_name == "list_system_services" or tool_name == "system_list_services":
            base_task.update({"type": "system_list_services"})
        elif tool_name == "manage_service" or tool_name == "system_manage_service":
            base_task.update({
                "type": "system_manage_service",
                "service_name": tool_args.get("service_name", tool_args.get("SERVICE_NAME", "")),
                "action": tool_args.get("action", "")
            })
        elif tool_name == "get_process_info" or tool_name == "system_get_process_info":
            base_task.update({
                "type": "system_get_process_info",
                "process_name": tool_args.get("process_name", tool_args.get("PROCESS_NAME")),
                "pid": tool_args.get("pid", tool_args.get("PID"))
            })
        elif tool_name == "terminate_process" or tool_name == "system_terminate_process":
            base_task.update({
                "type": "system_terminate_process",
                "pid": tool_args.get("pid", tool_args.get("PID"))
            })
        elif tool_name == "web_fetch":
            base_task.update({
                "type": "web_fetch",
                "url": tool_args.get("url", tool_args.get("URL", ""))
            })
        elif tool_name == "respond_conversationally":
            base_task.update({
                "type": "respond_conversationally",
                "response_text": tool_args.get("response_text", "")
            })
        elif tool_name == "ask_user_for_manual":
            base_task.update({
                "type": "ask_user_for_manual",
                "program_name": tool_args.get("program_name", tool_args.get("PROGRAM_NAME", "")),
                "question_text": tool_args.get("question_text", tool_args.get("QUESTION_TEXT", ""))
            })
        else:
            # Default mapping - try to use tool_name as task type
            base_task.update({
                "type": tool_name,
                **tool_args
            })
        
        return base_task

    async def _handle_command_approval(self, result):
        """Handle command approval workflow."""
        command = result.get("command")
        task_id = result.get("task_id")
        
        if not command or not task_id:
            return {"approved": False, "message": "Invalid approval request"}
        
        await event_manager.publish("log_message", {"level": "INFO", "message": f"Requesting approval for command: {command}"})
        print(f"Requesting approval for command: {command}")
        
        if self.task_transport_type == "redis":
            # Create a Future to wait for approval
            approval_future = asyncio.Future()
            self.pending_approvals[task_id] = approval_future
            
            # Publish approval request via Redis
            approval_request = {
                "task_id": task_id,
                "command": command,
                "timestamp": time.time()
            }
            if self.redis_client: # Explicit check for type checker
                self.redis_client.publish("command_approval_request", json.dumps(approval_request))
            else:
                await event_manager.publish("error", {"message": "Redis client not initialized for command approval."})
                return {"approved": False, "message": "Redis client not available for approval."}
            
            try:
                # Wait for approval response (with timeout)
                approval_response = await asyncio.wait_for(approval_future, timeout=300)  # 5 minute timeout
                return approval_response
            except asyncio.TimeoutError:
                self.pending_approvals.pop(task_id, None)
                await event_manager.publish("error", {"message": f"Command approval timeout for: {command}"})
                return {"approved": False, "message": "Approval timeout"}
        else:
            # For local execution, we would need to implement a different approval mechanism
            # For now, return approved=True for local development
            await event_manager.publish("log_message", {"level": "WARNING", "message": "Local approval mechanism not implemented, auto-approving"})
            return {"approved": True, "message": "Auto-approved for local execution"}

    async def generate_next_action(self, goal: str, messages: Optional[List[Dict[str, str]]]):
        """Generate the next action in the execution sequence."""
        return await self.generate_task_plan(goal, messages)

# Example Usage (for testing)
if __name__ == "__main__":
    # Ensure config.yaml exists for testing
    if not os.path.exists("config/config.yaml"):
        print("config/config.yaml not found. Copying from template for testing.")
        os.makedirs("config", exist_ok=True)
        with open("config/config.yaml.template", "r") as f_template:
            with open("config/config.yaml", "w") as f_config:
                f_config.write(f_template.read())

    async def run_test_goal():
        orchestrator = Orchestrator()
        await asyncio.sleep(2) # Give some time for Redis pubsub to connect and worker to report capabilities

        # Test with default LLM (TinyLLaMA via Ollama)
        await orchestrator.execute_goal("Write a short story about a robot learning to paint.")

        # Simulate a failing task for diagnostics testing
        # await orchestrator.execute_goal("Run a command that does not exist.")

        # Test GUI automation task
        # await orchestrator.execute_goal("Type text 'Hello from GUI automation!' into active window.")
        # await orchestrator.execute_goal("Bring window to front 'Terminal'.")

    asyncio.run(run_test_goal())
