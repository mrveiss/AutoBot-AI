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

        if self.task_transport_type == "redis":
            redis_host = self.config['task_transport']['redis']['host']
            redis_port = self.config['task_transport']['redis']['port']
            self.redis_client = redis.Redis(host=redis_host, port=redis_port, decode_responses=True)
            print(f"Orchestrator connected to Redis at {redis_host}:{redis_port}")
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

    def _load_config(self, config_path):
        with open(config_path, 'r') as f:
            return yaml.safe_load(f)

    def set_phi2_enabled(self, enabled: bool): # This function might become obsolete or need re-purposing
        self.phi2_enabled = enabled
        print(f"Phi-2 enabled status set to: {self.phi2_enabled}")
        asyncio.create_task(event_manager.publish("settings_update", {"phi2_enabled": enabled}))

    async def generate_task_plan(self, goal: str):
        # Always use the orchestrator LLM for planning
        target_llm_model = self.orchestrator_llm_model
        orchestrator_settings = self.llm_interface.orchestrator_llm_settings
        
        await event_manager.publish("log_message", {"level": "INFO", "message": f"Generating plan using Orchestrator LLM: {target_llm_model}"})
        print(f"Generating plan using Orchestrator LLM: {target_llm_model}")

        retrieved_context = self.knowledge_base.search(goal, n_results=3)
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
- Knowledge Base:
    - 'Add file "FILE_PATH" of type "FILE_TYPE" to knowledge base with metadata {JSON_METADATA}.'
    - 'Search knowledge base for "QUERY" with N results.'
    - 'Store fact "CONTENT" with metadata {JSON_METADATA}.'
    - 'Get fact by ID "ID" or query "QUERY".'

Prioritize using the most specific tool for the job. For example, use 'Manage service "SERVICE_NAME" action "start|stop|restart".' for services, 'Query system information.' for system details, and 'Type text "TEXT" into active window.' for GUI typing, rather than 'Execute system command "COMMAND".' if a more specific tool exists.
""")
        system_prompt = "\n".join(system_prompt_parts)

        if context_str:
            system_prompt += f"\n\nUse the following context to inform your plan:\n{context_str}"
        
        # Inject system information into the prompt
        system_prompt += f"\n\nOperating System Information:\n{json.dumps(self.system_info, indent=2)}\n"
        
        # Inject available tools into the prompt
        system_prompt += f"\n\nAvailable System Tools:\n{json.dumps(self.available_tools, indent=2)}\n"

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Goal: {goal}"}
        ]
        
        response = await self.llm_interface.chat_completion(
            messages=messages,
            llm_type="orchestrator", # Explicitly use orchestrator LLM
            # Pass settings from config
            temperature=orchestrator_settings.get('temperature', 0.7),
            # max_tokens=orchestrator_settings.get('max_tokens', 500), # Add max_tokens to config if needed
            # structured_output=False, # Do NOT force structured output here, let LLM decide based on prompt
            **{k: v for k, v in orchestrator_settings.items() if k not in ['system_prompt', 'temperature', 'sampling_strategy', 'structured_output']} # Pass other settings
        )
        
        print(f"Raw LLM response from chat_completion: {response}")
        await event_manager.publish("log_message", {"level": "DEBUG", "message": f"Raw LLM response: {response}"})

        llm_raw_content = None
        plan_text = None
        if isinstance(response, dict):
            if 'message' in response and isinstance(response['message'], dict) and 'content' in response['message']:
                llm_raw_content = response['message']['content']
            elif 'choices' in response and isinstance(response['choices'], list) and len(response['choices']) > 0 and \
                 'message' in response['choices'][0] and isinstance(response['choices'][0]['message'], dict) and \
                 'content' in response['choices'][0]['message']:
                llm_raw_content = response['choices'][0]['message']['content']

        if llm_raw_content:
            try:
                # Attempt to parse as JSON first
                parsed_content = json.loads(llm_raw_content)
                
                # If it's a dictionary and contains 'tool_name', treat as a tool call
                if isinstance(parsed_content, dict) and "tool_name" in parsed_content and "tool_args" in parsed_content:
                    task_plan_steps = [parsed_content] # Wrap single tool call in a list
                    plan_text = json.dumps(task_plan_steps, indent=2)
                    await event_manager.publish("llm_response", {"response": llm_raw_content}) # Still publish raw LLM output
                    await event_manager.publish("plan_generated", {"goal": goal, "plan": task_plan_steps})
                    return task_plan_steps
                else:
                    # It's JSON, but not a valid tool call, treat as unexpected JSON conversational response
                    print(f"LLM returned unexpected JSON (not a tool call). Treating as conversational: {llm_raw_content}")
                    task_plan_steps = [{
                        "thoughts": ["The LLM returned unexpected JSON. Responding conversationally with the raw JSON."],
                        "tool_name": "respond_conversationally",
                        "tool_args": {"response_text": llm_raw_content}
                    }]
                    plan_text = llm_raw_content
                    await event_manager.publish("llm_response", {"response": llm_raw_content})
                    await event_manager.publish("plan_generated", {"goal": goal, "plan": task_plan_steps})
                    return task_plan_steps
            except json.JSONDecodeError:
                # If JSON parsing fails, it's plain text, treat as conversational
                print(f"LLM response is plain text. Treating as conversational: {llm_raw_content}")
                task_plan_steps = [{
                    "thoughts": ["The user's request does not require a tool. Responding conversationally."],
                    "tool_name": "respond_conversationally",
                    "tool_args": {"response_text": llm_raw_content}
                }]
                plan_text = llm_raw_content
                await event_manager.publish("llm_response", {"response": llm_raw_content})
                await event_manager.publish("plan_generated", {"goal": goal, "plan": task_plan_steps})
                return task_plan_steps
        
        error_message = "Failed to generate a task plan from Orchestrator LLM. No content received."
        await event_manager.publish("error", {"message": error_message})
        print(error_message)
        return []

    async def dispatch_task(self, task_payload: Dict[str, Any]) -> Dict[str, Any]:
        task_id = task_payload.get("task_id", str(uuid.uuid4()))
        task_payload["task_id"] = task_id
        
        await event_manager.publish("orchestrator_dispatch", {"task_id": task_id, "payload": task_payload})
        print(f"Orchestrator dispatching task {task_id}...")

        result = {"status": "error", "message": "Task dispatch failed."}
        try:
            if self.task_transport_type == "redis" and self.redis_client:
                self.redis_client.publish("orchestrator_tasks", json.dumps(task_payload))
                print(f"Task {task_id} published to Redis channel 'orchestrator_tasks'.")
                
                response_channel = f"worker_results_{task_id}"
                pubsub = self.redis_client.pubsub()
                pubsub.subscribe(response_channel)
                print(f"Orchestrator waiting for result on '{response_channel}'.")
                
                timeout = 300 # seconds
                start_time = time.time()
                for message in pubsub.listen():
                    if message['type'] == 'message':
                        result = json.loads(message['data'])
                        await event_manager.publish("orchestrator_result_received", {"task_id": task_id, "result": result})
                        pubsub.unsubscribe(response_channel)
                        break
                    if time.time() - start_time > timeout:
                        await event_manager.publish("error", {"message": f"Task {task_id} timed out after {timeout}s."})
                        pubsub.unsubscribe(response_channel)
                        result = {"status": "error", "message": "Task timed out."}
                        break
            elif self.task_transport_type == "local":
                print(f"Executing task {task_id} locally.")
                result = await self.local_worker.execute_task(task_payload)
                await event_manager.publish("orchestrator_result_received", {"task_id": task_id, "result": result})
            else:
                await event_manager.publish("error", {"message": f"Unsupported task transport type: {self.task_transport_type}"})
                result = {"status": "error", "message": "Unsupported task transport type."}
        except Exception as e:
            result = {"status": "error", "message": f"Exception during task dispatch: {e}"}
            await event_manager.publish("error", {"message": f"Orchestrator dispatch exception: {e}"})

        # Diagnostics integration
        if result['status'] == "error":
            await self.diagnostics.log_failure(task_payload, result.get('message', 'Unknown error'), result.get('error', ''))
            report = await self.diagnostics.analyze_failure(task_payload, result.get('message', 'Unknown error'), result.get('error', ''))
            
            if not self.diagnostics.diagnostics_config['auto_apply_fixes']:
                permission_granted = await self.diagnostics.request_user_permission(report)
                if permission_granted:
                    await event_manager.publish("log_message", {"level": "INFO", "message": f"User granted permission for task {task_id} fixes. Retrying or applying fix strategy..."})
                    # Here, implement retry/fallback/plan rewriting logic based on report and permission
                    # For now, just log that permission was granted.
                    # A more advanced system would re-dispatch the task or modify the plan.
                else:
                    await event_manager.publish("log_message", {"level": "WARNING", "message": f"User denied permission for task {task_id} fixes. Task will not be retried/fixed automatically."})
            else:
                await event_manager.publish("log_message", {"level": "INFO", "message": f"Auto-applying fixes for task {task_id}."})
                # Implement auto-retry/fallback/plan rewriting here
        else:
            await self.diagnostics.log_success(task_payload)

        return result

    async def pause_agent(self):
        """Pauses the agent's current operation."""
        # Placeholder for actual pause functionality
        # This can be expanded to include logic for pausing ongoing tasks
        return {"status": "success", "message": "Agent paused successfully."}

    async def resume_agent(self):
        """Resumes the agent's operation if paused."""
        # Placeholder for actual resume functionality
        # This can be expanded to include logic for resuming paused tasks
        return {"status": "success", "message": "Agent resumed successfully."}

    async def execute_goal(self, goal: str, user_role: str = "user"): # Removed use_phi2 parameter
        await event_manager.publish("goal_received_orchestrator", {"goal": goal})
        print(f"\nReceived goal: {goal}")
        plan_text = ""
        task_plan_steps = await self.generate_task_plan(goal) # Call without use_phi2
        
        if not task_plan_steps:
            await event_manager.publish("error", {"message": "Failed to generate a task plan."})
            print("Failed to generate a task plan.")
            return {"status": "error", "message": "Failed to generate task plan."}
        else:
            # Reconstruct plan_text from task_plan_steps for the final response
            # Convert each tool call object to a JSON string for display
            plan_text = "\n".join([json.dumps(step, indent=2) for step in task_plan_steps])

        # Publish separate events for plan components
        await event_manager.publish("plan_ready", {"plan": task_plan_steps, "llm_response": plan_text})
        print("\nGenerated Task Plan:")
        for i, task in enumerate(task_plan_steps):
            print(f"{i+1}. {json.dumps(task, indent=2)}") # Print each task as formatted JSON
            # Split each task into components for separate messaging
            tool_name = task.get("tool_name", "Unknown Tool")
            thoughts = task.get("thoughts", [])
            tool_args = task.get("tool_args", {})
            
            # Publish plan description
            plan_desc = f"Here is the plan for step {i+1}: I will {tool_name}."
            if tool_name == "respond_conversationally":
                plan_desc = f"Here is the plan for step {i+1}: I will respond conversationally."
            await event_manager.publish("planning", {"message": plan_desc})
            
            # Publish thoughts if any
            if thoughts:
                thought_text = ", ".join(thoughts)
                await event_manager.publish("thought", {"thought": f"Thought for step {i+1}: {thought_text}"})
            
            # Publish tool usage as utility message
            await event_manager.publish("utility", {"message": f"Tool used for step {i+1}: {tool_name}"})

        results = []
        print("\nExecuting tasks...")
        for i, tool_call_object in enumerate(task_plan_steps): # Iterate through structured tool call objects
            print(f"--- Orchestrating Task {i+1}: {tool_call_object.get('tool_name', 'Unknown Tool')} ---")
            
            task_payload = {
                "task_id": str(uuid.uuid4()),
                "user_role": user_role,
                "type": tool_call_object.get("tool_name"), # Use tool_name as task type
                **tool_call_object.get("tool_args", {}) # Add tool arguments directly to payload
            }
            
            # Handle potential missing tool_name or invalid structure from LLM
            if not task_payload["type"]:
                await event_manager.publish("error", {"message": f"Orchestrator LLM generated a task without a 'tool_name': {tool_call_object}. Falling back to shell command simulation."})
                task_payload = {
                    "type": "execute_shell_command",
                    "task_id": str(uuid.uuid4()),
                    "command": f"echo 'Simulating execution of: {json.dumps(tool_call_object)}' && sleep 0.5",
                    "user_role": user_role
                }

            result = await self.dispatch_task(task_payload)
            results.append(result)
            print(f"Task {i+1} Result: {result['status']}")
            if result['status'] == "error":
                print(f"Error details: {result['message']}")
                # Optionally, break or implement retry logic here
                # For now, continue to allow other tasks to attempt execution
        
        await event_manager.publish("goal_execution_complete", {"goal": goal, "results": results, "llm_response": plan_text})
        print("\nGoal execution complete.")
        return {"status": "completed", "results": results, "llm_response": plan_text}

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
