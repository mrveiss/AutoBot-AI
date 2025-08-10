# src/orchestrator.py
import asyncio
import json
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
from src.prompt_manager import prompt_manager

# Import the centralized ConfigManager and Redis client utility
from src.config import config as global_config_manager
from src.utils.redis_client import get_redis_client

# Import LangChain Agent (optional)
try:
    from src.langchain_agent_orchestrator import LangChainAgentOrchestrator

    LANGCHAIN_AVAILABLE = True
except ImportError:
    LangChainAgentOrchestrator = None
    LANGCHAIN_AVAILABLE = False
    msg = "WARNING: LangChain Agent not available. Using standard orchestrator only."
    print(msg)


class Orchestrator:
    def __init__(self):
        # Remove config_path and direct config loading
        # Will update LLMInterface to use global_config_manager
        self.llm_interface = LLMInterface()
        # Will update KnowledgeBase to use global_config_manager
        self.knowledge_base = KnowledgeBase()
        # Will update Diagnostics to use global_config_manager
        self.diagnostics = Diagnostics()

        llm_config = global_config_manager.get_llm_config()
        self.orchestrator_llm_model = llm_config.get(
            "orchestrator_llm",
            llm_config.get("ollama", {}).get("model", "tinyllama:latest"),
        )
        self.task_llm_model = llm_config.get("task_llm", "ollama")
        self.ollama_models = llm_config.get("ollama", {}).get("models", {})
        self.phi2_enabled = False  # This will be driven by config if needed

        self.task_transport_type = global_config_manager.get_nested(
            "task_transport.type", "local"
        )
        self.redis_client = None
        self.worker_capabilities: Dict[str, Dict[str, Any]] = {}
        self.pending_approvals: Dict[str, asyncio.Future] = {}
        # Use default channel names since we're using memory.redis config
        self.redis_command_approval_request_channel = "command_approval_request"
        self.redis_command_approval_response_channel_prefix = "command_approval_"

        self.agent_paused = False

        self.langchain_agent = None
        self.use_langchain = global_config_manager.get_nested(
            "orchestrator.use_langchain", False
        )

        if self.task_transport_type == "redis":
            # Use centralized Redis client utility
            self.redis_client = get_redis_client(async_client=False)
            if self.redis_client:
                print("Orchestrator connected to Redis via centralized utility")
            else:
                msg = (
                    "Orchestrator failed to get Redis client from centralized "
                    "utility. Falling back to local task transport."
                )
                print(msg)
                # Fallback to local if Redis fails
                self.task_transport_type = "local"
                self.local_worker = WorkerNode()

        if self.task_transport_type == "local":
            print("Orchestrator configured for local task transport.")
            self.local_worker = WorkerNode()

        # Initialize unified tool registry to eliminate code duplication
        self.tool_registry = None
        
        # Initialize system info
        self.system_info = get_os_info()
        
        # Initialize available tools
        self.available_tools = discover_tools()

    async def _listen_for_worker_capabilities(self):
        """
        Listen for worker capability reports via Redis pub/sub.
        Workers publish their capabilities on startup and capability changes.
        """
        if not self.redis_client:
            print("Redis client not available for worker capabilities listening")
            return

        pubsub = self.redis_client.pubsub()
        worker_capabilities_channel = "worker_capabilities"
        pubsub.subscribe(worker_capabilities_channel)
        msg = "Listening for worker capabilities on Redis channel "
        msg += f"'{worker_capabilities_channel}'..."
        print(msg)

        try:
            while True:
                # Use get_message with timeout instead of listen()
                # for async compatibility
                message = pubsub.get_message(timeout=1.0)
                if message is None:
                    await asyncio.sleep(0.1)  # Small delay to prevent busy waiting
                    continue

                if message["type"] == "message":
                    try:
                        data = json.loads(message["data"])
                        worker_id = data.get("worker_id")
                        capabilities = data.get("capabilities", {})
                        timestamp = data.get("timestamp", time.time())

                        if worker_id and capabilities:
                            # Update worker capabilities dictionary
                            self.worker_capabilities[worker_id] = {
                                "capabilities": capabilities,
                                "timestamp": timestamp,
                                "last_seen": time.time(),
                            }
                            print(
                                f"Updated capabilities for worker {worker_id}: "
                                f"{capabilities}"
                            )
                            await event_manager.publish(
                                "log_message",
                                {
                                    "level": "INFO",
                                    "message": (
                                        f"Worker {worker_id} capabilities updated: "
                                        f"{list(capabilities.keys())}"
                                    ),
                                },
                            )
                        else:
                            msg = (
                                "Invalid worker capabilities message: missing "
                                f"worker_id or capabilities - {data}"
                            )
                            print(msg)

                    except json.JSONDecodeError as e:
                        print(f"Failed to parse worker capabilities message: {e}")
                        await event_manager.publish(
                            "log_message",
                            {
                                "level": "ERROR",
                                "message": (
                                    f"Failed to parse worker capabilities "
                                    f"message: {e}"
                                ),
                            },
                        )
                    except Exception as e:
                        print(f"Error processing worker capabilities message: {e}")
                        await event_manager.publish(
                            "log_message",
                            {
                                "level": "ERROR",
                                "message": (
                                    f"Error processing worker capabilities "
                                    f"message: {e}"
                                ),
                            },
                        )

        except Exception as e:
            print(f"Error in worker capabilities listener: {e}")
            await event_manager.publish(
                "log_message",
                {
                    "level": "ERROR",
                    "message": f"Worker capabilities listener error: {e}",
                },
            )
        finally:
            try:
                pubsub.unsubscribe(worker_capabilities_channel)
                pubsub.close()
            except Exception as e:
                print(f"Error closing worker capabilities pubsub: {e}")

    async def _listen_for_command_approvals(self):
        if not self.redis_client:
            print("Redis client not available for command approval listening")
            return

        pubsub = self.redis_client.pubsub()
        approval_channel_pattern = (
            f"{self.redis_command_approval_response_channel_prefix}*"
        )
        pubsub.psubscribe(approval_channel_pattern)
        msg = "Listening for command approvals on Redis channel "
        msg += f"'{approval_channel_pattern}'..."
        print(msg)

        try:
            while True:
                # Use get_message with timeout instead of listen()
                # for async compatibility
                message = pubsub.get_message(timeout=1.0)
                if message is None:
                    await asyncio.sleep(0.1)  # Small delay to prevent busy waiting
                    continue

                if message["type"] == "pmessage":
                    try:
                        message["channel"].decode("utf-8")
                        data = json.loads(message["data"])
                        task_id = data.get("task_id")
                        approved = data.get("approved")

                        if task_id and task_id in self.pending_approvals:
                            future = self.pending_approvals.pop(task_id)
                            if not future.done():
                                future.set_result({"approved": approved})
                            print(
                                f"Received approval for task {task_id}: "
                                f"Approved={approved}"
                            )
                        else:
                            print(
                                f"Received unhandled approval message for task "
                                f"{task_id}: {data}"
                            )
                    except Exception as e:
                        print(f"Error processing command approval message: {e}")

        except Exception as e:
            print(f"Error in command approval listener: {e}")
        finally:
            try:
                pubsub.punsubscribe(approval_channel_pattern)
                pubsub.close()
            except Exception as e:
                print(f"Error closing command approval pubsub: {e}")

    async def startup(self):
        ollama_connected = await self.llm_interface.check_ollama_connection()
        if ollama_connected:
            await event_manager.publish(
                "llm_status",
                {
                    "status": "connected",
                    "model": self.llm_interface.orchestrator_llm_alias,
                },
            )
            print(
                f"LLM ({self.llm_interface.orchestrator_llm_alias}) "
                "connected successfully."
            )
        else:
            await event_manager.publish(
                "llm_status",
                {
                    "status": "disconnected",
                    "model": self.llm_interface.orchestrator_llm_alias,
                    "message": (
                        "Failed to connect to Ollama or configured " "models not found."
                    ),
                },
            )
            print(
                f"LLM ({self.llm_interface.orchestrator_llm_alias}) "
                "connection failed."
            )

        if self.task_transport_type == "redis" and self.redis_client:
            asyncio.create_task(self._listen_for_worker_capabilities())
        elif self.task_transport_type == "local" and hasattr(self, "local_worker"):
            await self.local_worker.report_capabilities()

        self.system_info = get_os_info()
        await event_manager.publish(
            "log_message",
            {
                "level": "INFO",
                "message": (
                    f"System information collected: "
                    f"{json.dumps(self.system_info, indent=2)}"
                ),
            },
        )
        print("System information collected on startup.")

        self.available_tools = discover_tools()
        await event_manager.publish(
            "log_message",
            {
                "level": "INFO",
                "message": (
                    f"Available tools collected: "
                    f"{json.dumps(self.available_tools, indent=2)}"
                ),
            },
        )
        print("Available tools collected on startup.")

        # Initialize unified tool registry to eliminate code duplication
        worker_node = self.local_worker if hasattr(self, "local_worker") else None
        self.tool_registry = ToolRegistry(
            worker_node=worker_node, knowledge_base=self.knowledge_base
        )

        if (
            self.use_langchain
            and LANGCHAIN_AVAILABLE
            and LangChainAgentOrchestrator is not None
        ):
            try:
                kb_config = global_config_manager.get("knowledge_base", {})
                if kb_config.get("provider") == "disabled":
                    print(
                        "Knowledge Base disabled in configuration. "
                        "Skipping LangChain KB initialization."
                    )
                    self.knowledge_base = None
                # KnowledgeBase.ainit() is now called in main.py's lifespan
                # startup, no need to call it here.

                self.langchain_agent = LangChainAgentOrchestrator(
                    # Pass the full config dict
                    config=global_config_manager.to_dict(),
                    worker_node=self.local_worker
                    if hasattr(self, "local_worker")
                    else None,
                    knowledge_base=self.knowledge_base,
                )

                if self.langchain_agent.available:
                    print("LangChain Agent initialized successfully.")
                    await event_manager.publish(
                        "log_message",
                        {
                            "level": "INFO",
                            "message": "LangChain Agent initialized successfully.",
                        },
                    )
                else:
                    print("LangChain Agent initialization failed.")
                    self.langchain_agent = None
                    self.use_langchain = False
            except Exception as e:
                print(f"Failed to initialize LangChain Agent: {e}")
                await event_manager.publish(
                    "log_message",
                    {
                        "level": "ERROR",
                        "message": (f"Failed to initialize LangChain Agent: {e}"),
                    },
                )
                self.langchain_agent = None
                self.use_langchain = False
        else:
            kb_config = global_config_manager.get("knowledge_base", {})
            if kb_config.get("provider") == "disabled":
                print(
                    "Knowledge Base disabled in configuration. "
                    "Skipping initialization."
                )
                self.knowledge_base = None
            # KnowledgeBase.ainit() is now called in main.py's lifespan
            # startup, no need to call it here.

    def set_phi2_enabled(self, enabled: bool):
        self.phi2_enabled = enabled
        print(f"Phi-2 enabled status set to: {self.phi2_enabled}")
        asyncio.create_task(
            event_manager.publish("settings_update", {"phi2_enabled": enabled})
        )

    async def pause_agent(self):
        self.agent_paused = True
        await event_manager.publish(
            "log_message", {"level": "INFO", "message": "Agent paused"}
        )
        print("Agent paused")

    async def resume_agent(self):
        self.agent_paused = False
        await event_manager.publish(
            "log_message", {"level": "INFO", "message": "Agent resumed"}
        )
        print("Agent resumed")

    async def generate_task_plan(
        self, goal: str, messages: Optional[List[Dict[str, str]]] = None
    ) -> Dict[str, Any]:
        if messages is None:
            messages = [{"role": "user", "content": goal}]
        target_llm_model = self.orchestrator_llm_model
        orchestrator_settings = self.llm_interface.orchestrator_llm_settings

        await event_manager.publish(
            "log_message",
            {
                "level": "INFO",
                "message": (
                    f"Generating plan using Orchestrator LLM: {target_llm_model}"
                ),
            },
        )
        print(f"Generating plan using Orchestrator LLM: {target_llm_model}")

        retrieved_context = []
        if self.knowledge_base is not None:
            retrieved_context = await self.knowledge_base.search(
                goal,
                n_results=global_config_manager.get_nested(
                    "knowledge_base.search_results_limit", 3
                ),
            )  # Use config for n_results

        context_str = ""
        if retrieved_context:
            context_str = "\n\nRelevant Context from Knowledge Base:\n"
            for i, item in enumerate(retrieved_context):
                filename = item["metadata"].get("filename", "N/A")
                chunk_idx = item["metadata"].get("chunk_index", "N/A")
                context_str += f"--- Document: {filename} (Chunk {chunk_idx}) ---\n"
                context_str += item["content"] + "\n"
            await event_manager.publish(
                "log_message",
                {
                    "level": "INFO",
                    "message": (f"Retrieved {len(retrieved_context)} context chunks."),
                },
            )
        else:
            await event_manager.publish(
                "log_message",
                {
                    "level": "INFO",
                    "message": "No relevant context found in knowledge base.",
                },
            )

        # Use the centralized prompt manager to get the orchestrator system prompt
        gui_automation_supported = (
            self.task_transport_type == "local" and GUI_AUTOMATION_SUPPORTED
        )

        try:
            system_prompt = prompt_manager.get(
                "orchestrator.system_prompt",
                gui_automation_supported=gui_automation_supported,
                context_str=context_str,
                system_info=self.system_info,
                available_tools=self.available_tools,
            )
        except KeyError:
            # Fallback to legacy prompt if new one doesn't exist
            print(
                "Warning: orchestrator.system_prompt not found, "
                "using legacy system prompt"
            )
            try:
                system_prompt = prompt_manager.get("orchestrator.legacy_system_prompt")

                # Add the dynamic parts that weren't in the legacy prompt
                if context_str:
                    system_prompt += (
                        f"\n\nUse the following context to inform your plan:\n"
                        f"{context_str}"
                    )

                system_prompt += (
                    f"\n\nOperating System Information:\n"
                    f"{json.dumps(self.system_info, indent=2)}\n"
                )
                system_prompt += (
                    f"\n\nAvailable System Tools:\n"
                    f"{json.dumps(self.available_tools, indent=2)}\n"
                )
            except KeyError:
                # Final fallback - use the old hardcoded version
                print(
                    "Warning: No prompt found in prompt manager, using "
                    "hardcoded fallback"
                )
                system_prompt_parts = [
                    self.llm_interface.orchestrator_system_prompt,
                    "You have access to the following tools. You MUST use these "
                    "tools to achieve the user's goal.",
                ]
                system_prompt = "\n".join(system_prompt_parts)
                if context_str:
                    system_prompt += (
                        f"\n\nUse the following context to inform your plan:\n"
                        f"{context_str}"
                    )
                system_prompt += (
                    f"\n\nOperating System Information:\n"
                    f"{json.dumps(self.system_info, indent=2)}\n"
                )
                system_prompt += (
                    f"\n\nAvailable System Tools:\n"
                    f"{json.dumps(self.available_tools, indent=2)}\n"
                )

        full_messages = [{"role": "system", "content": system_prompt}] + messages

        response = await self.llm_interface.chat_completion(
            messages=full_messages,
            llm_type="orchestrator",
            temperature=orchestrator_settings.get("temperature", 0.7),
            **{
                k: v
                for k, v in orchestrator_settings.items()
                if k
                not in [
                    "system_prompt",
                    "temperature",
                    "sampling_strategy",
                    "structured_output",
                ]
            },
        )

        print(f"Raw LLM response from chat_completion: {response}")
        await event_manager.publish(
            "log_message",
            {"level": "DEBUG", "message": f"Raw LLM response: {response}"},
        )

        llm_raw_content = None
        if isinstance(response, dict):
            if (
                "message" in response
                and isinstance(response["message"], dict)
                and "content" in response["message"]
            ):
                llm_raw_content = response["message"]["content"]
            elif (
                "choices" in response
                and isinstance(response["choices"], list)
                and len(response["choices"]) > 0
                and "message" in response["choices"][0]
                and isinstance(response["choices"][0]["message"], dict)
                and "content" in response["choices"][0]["message"]
            ):
                llm_raw_content = response["choices"][0]["message"]["content"]

        if llm_raw_content:
            try:
                parsed_content = json.loads(llm_raw_content)
                if (
                    isinstance(parsed_content, dict)
                    and "tool_name" in parsed_content
                    and "tool_args" in parsed_content
                ):
                    return parsed_content
                else:
                    print(
                        "LLM returned unexpected JSON (not a tool call). "
                        f"Treating as conversational: {llm_raw_content}"
                    )

                    # Check if the JSON is empty or malformed
                    if (
                        llm_raw_content.strip() in ["{}", "{\n\n}", "{ }", "{  }"]
                        or not llm_raw_content.strip()
                        or len(llm_raw_content.strip()) < 5
                    ):
                        # Generate a proper greeting response for empty JSON
                        if any(
                            greeting in messages[-1].get("content", "").lower()
                            for greeting in ["hello", "hi", "hey"]
                        ):
                            response_text = "Hello! How can I assist you today?"
                        else:
                            response_text = (
                                "I received your message but couldn't generate "
                                "a proper response. Could you please try rephrasing "
                                "your question?"
                            )
                    else:
                        response_text = llm_raw_content

                    return {
                        "thoughts": [
                            "The LLM returned unexpected JSON. "
                            "Providing a helpful conversational response."
                        ],
                        "tool_name": "respond_conversationally",
                        "tool_args": {"response_text": response_text},
                    }
            except json.JSONDecodeError:
                print(
                    f"LLM response is plain text. "
                    f"Treating as conversational: {llm_raw_content}"
                )
                return {
                    "thoughts": [
                        "The user's request does not require a tool. "
                        "Responding conversationally."
                    ],
                    "tool_name": "respond_conversationally",
                    "tool_args": {"response_text": llm_raw_content},
                }

        error_message = (
            "Failed to generate an action from Orchestrator LLM. No content received."
        )
        await event_manager.publish("error", {"message": error_message})
        print(error_message)
        return {
            "tool_name": "respond_conversationally",
            "tool_args": {"response_text": error_message},
        }

    async def execute_goal(
        self, goal: str, messages: Optional[List[Dict[str, str]]] = None
    ) -> Dict[str, Any]:
        """
        Execute a goal using an iterative approach with the orchestrator LLM.

        This method coordinates the entire goal execution process, from initial setup
        through iterative planning and execution until completion or timeout.

        Args:
            goal: The user's goal or task to accomplish
            messages: Optional conversation history for context

        Returns:
            Dict containing execution results, status, and any response content
        """
        if messages is None:
            messages = [{"role": "user", "content": goal}]

        await self._log_goal_start(goal)

        # Try LangChain agent first if available
        langchain_result = await self._try_langchain_execution(goal, messages)
        if langchain_result:
            return langchain_result

        # Handle simple commands directly
        if self._is_simple_command(goal):
            return await self._execute_simple_command(goal)

        # Execute complex goal using iterative approach
        return await self._execute_complex_goal(goal, messages)

    async def _log_goal_start(self, goal: str) -> None:
        """Log the start of goal execution."""
        await event_manager.publish(
            "log_message",
            {"level": "INFO", "message": f"Starting goal execution: {goal}"},
        )
        print(f"Starting goal execution: {goal}")

    async def _try_langchain_execution(
        self, goal: str, messages: List[Dict[str, str]]
    ) -> Optional[Dict[str, Any]]:
        """
        Try to execute goal using LangChain agent if available.

        Returns:
            Dict with execution results if LangChain handles it, None otherwise
        """
        if (
            self.use_langchain
            and self.langchain_agent
            and hasattr(self.langchain_agent, "available")
            and self.langchain_agent.available
        ):
            try:
                await event_manager.publish(
                    "log_message",
                    {
                        "level": "INFO",
                        "message": "Using LangChain Agent for goal execution",
                    },
                )
                print("Using LangChain Agent for goal execution")
                return await self.langchain_agent.execute_goal(goal, messages)
            except Exception as e:
                await event_manager.publish(
                    "log_message",
                    {
                        "level": "ERROR",
                        "message": (
                            "LangChain Agent failed, falling back to "
                            f"standard orchestrator: {e}"
                        ),
                    },
                )
                print(
                    "LangChain Agent failed, falling back to "
                    f"standard orchestrator: {e}"
                )
        return None

    async def _execute_complex_goal(
        self, goal: str, messages: List[Dict[str, str]]
    ) -> Dict[str, Any]:
        """
        Execute complex goal using iterative orchestrator approach.

        This method handles the main execution loop for complex goals that require
        multiple planning and execution iterations.
        """
        max_iterations = global_config_manager.get_nested(
            "orchestrator.max_iterations", 10
        )
        iteration = 0

        while iteration < max_iterations:
            if self.agent_paused:
                await event_manager.publish(
                    "log_message",
                    {
                        "level": "INFO",
                        "message": "Agent is paused, waiting for resume...",
                    },
                )
                print("Agent is paused, waiting for resume...")
                await asyncio.sleep(1)
                continue

            iteration += 1
            await event_manager.publish(
                "log_message",
                {"level": "INFO", "message": f"Iteration {iteration}/{max_iterations}"},
            )
            print(f"Iteration {iteration}/{max_iterations}")

            # Generate action plan for this iteration
            action = await self.generate_task_plan(goal, messages)

            if not action:
                await event_manager.publish(
                    "error", {"message": "Failed to generate action plan"}
                )
                print("Failed to generate action plan")
                return {
                    "status": "error",
                    "message": "Failed to generate action plan.",
                }

            # Execute the planned action
            execution_result = await self._execute_planned_action(action, messages)

            # Check if goal is completed
            if execution_result.get("completed"):
                return execution_result

        # Goal execution completed after max iterations
        await event_manager.publish(
            "log_message",
            {
                "level": "WARNING",
                "message": f"Goal execution completed after {max_iterations} "
                "iterations",
            },
        )
        print(f"Goal execution completed after {max_iterations} iterations")
        return {
            "status": "warning",
            "message": (
                "Goal execution completed, but may not have fully achieved "
                "the objective."
            ),
        }

    async def _execute_planned_action(
        self, action: Dict[str, Any], messages: List[Dict[str, str]]
    ) -> Dict[str, Any]:
        """
        Execute a single planned action from the orchestrator.

        Returns:
            Dict with execution results and completion status
        """
        tool_name = action.get("tool_name")
        tool_args = action.get("tool_args", {})
        thoughts = action.get("thoughts", [])

        # Log AI thoughts if present
        if thoughts:
            thoughts_text = (
                " ".join(thoughts) if isinstance(thoughts, list) else str(thoughts)
            )
            await event_manager.publish(
                "log_message",
                {"level": "INFO", "message": f"AI Thoughts: {thoughts_text}"},
            )
            print(f"AI Thoughts: {thoughts_text}")

        await event_manager.publish(
            "log_message",
            {
                "level": "INFO",
                "message": f"Executing tool: {tool_name} with args: {tool_args}",
            },
        )
        print(f"Executing tool: {tool_name} with args: {tool_args}")

        # Validate tool name
        if not isinstance(tool_name, str):
            error_msg = (
                f"Invalid tool_name received from LLM: {tool_name}. Expected string."
            )
            await event_manager.publish("error", {"message": error_msg})
            messages.append(
                {"role": "user", "content": f"Tool execution failed: {error_msg}"}
            )
            return {"completed": False}

        # Execute tool using unified tool registry
        try:
            if self.tool_registry:
                result = await self.tool_registry.execute_tool(tool_name, tool_args)
            else:
                result = {"status": "error", "message": "Tool registry not initialized"}

            tool_output_content = result.get(
                "result",
                result.get(
                    "output", result.get("message", "Tool execution completed.")
                ),
            )
            messages.append({"role": "tool_output", "content": tool_output_content})

            return await self._process_tool_result(result, tool_name, messages)

        except Exception as e:
            error_msg = f"Exception during tool execution: {str(e)}"
            messages.append({"role": "user", "content": error_msg})
            await event_manager.publish("error", {"message": error_msg})
            print(error_msg)
            traceback.print_exc()
            return {"completed": False}

    async def _process_tool_result(
        self, result: Dict[str, Any], tool_name: str, messages: List[Dict[str, str]]
    ) -> Dict[str, Any]:
        """
        Process the result of tool execution and determine next steps.

        Returns:
            Dict with completion status and any response content
        """
        if result.get("status") == "success":
            if tool_name == "respond_conversationally":
                result_content = result.get(
                    "response_text",
                    result.get(
                        "result",
                        result.get(
                            "output",
                            result.get("message", "Task completed successfully"),
                        ),
                    ),
                )
            else:
                result_content = result.get(
                    "result",
                    result.get(
                        "output",
                        result.get("message", "Task completed successfully"),
                    ),
                )

            await event_manager.publish("llm_response", {"response": result_content})
            await event_manager.publish(
                "log_message",
                {
                    "level": "INFO",
                    "message": f"Tool execution successful: {result_content}",
                },
            )
            print(f"Tool execution successful: {result_content}")

            if tool_name == "respond_conversationally":
                await event_manager.publish(
                    "log_message",
                    {
                        "level": "INFO",
                        "message": (
                            "Goal execution completed with conversational response"
                        ),
                    },
                )
                print("Goal execution completed with conversational response")
                return {
                    "completed": True,
                    "tool_name": "respond_conversationally",
                    "tool_args": {"response_text": result_content},
                    "response_text": result_content,
                }

        elif result.get("status") == "pending_approval":
            approval_result = await self._handle_command_approval(result)
            if approval_result.get("approved"):
                # Continue with next iteration
                return {"completed": False}
            else:
                messages.append(
                    {
                        "role": "user",
                        "content": (
                            "User declined to approve the command. "
                            "Please suggest an alternative approach."
                        ),
                    }
                )
                return {"completed": False}

        else:
            error_msg = result.get("message", "Unknown error occurred")
            messages.append(
                {"role": "user", "content": f"Tool execution failed: {error_msg}"}
            )
            await event_manager.publish("error", {"message": error_msg})
            print(f"Tool execution failed: {error_msg}")

        return {"completed": False}

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
            r"ip\s+addr",
        ]
        is_simple = any(
            re.search(pattern, goal.lower()) for pattern in command_patterns
        )
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

        print(
            f"DEBUG: _execute_simple_command called for goal: '{goal}', "
            f"determined command: '{command}'"
        )

        if command:
            await event_manager.publish(
                "log_message",
                {"level": "INFO", "message": f"Executing simple command: {command}"},
            )

            task = {
                "task_id": str(uuid.uuid4()),
                "type": "system_execute_command",
                "command": command,
                "user_role": "user",
                "timestamp": time.time(),
            }

            result = await self.local_worker.execute_task(task)

            await event_manager.publish(
                "log_message",
                {
                    "level": "INFO",
                    "message": (
                        f"Result from worker for simple command '{command}': "
                        f"{json.dumps(result, indent=2)}"
                    ),
                },
            )
            print(
                f"Result from worker for simple command '{command}': "
                f"{json.dumps(result, indent=2)}"
            )

            if result.get("status") == "success":
                return {
                    "tool_name": "execute_system_command",
                    "tool_args": {
                        "command": command,
                        "output": result.get("output", "Command executed successfully"),
                        "status": "success",
                    },
                }
            else:
                error_msg = result.get("message", "Command execution failed")
                return {
                    "tool_name": "execute_system_command",
                    "tool_args": {
                        "command": command,
                        "error": error_msg,
                        "output": result.get("output", ""),
                        "status": "error",
                    },
                }

            print(
                f"DEBUG: _execute_simple_command could not determine a direct "
                f"command for '{goal}'. Falling back to generate_task_plan."
            )
        return await self.generate_task_plan(goal, [{"role": "user", "content": goal}])

    async def _handle_command_approval(self, result):
        command = result.get("command")
        task_id = result.get("task_id")

        if not command or not task_id:
            return {"approved": False, "message": "Invalid approval request"}

        await event_manager.publish(
            "log_message",
            {"level": "INFO", "message": f"Requesting approval for command: {command}"},
        )
        print(f"Requesting approval for command: {command}")

        if self.task_transport_type == "redis":
            approval_future = asyncio.Future()
            self.pending_approvals[task_id] = approval_future

            approval_request = {
                "task_id": task_id,
                "command": command,
                "timestamp": time.time(),
            }
            if self.redis_client:
                self.redis_client.publish(
                    self.redis_command_approval_request_channel,
                    json.dumps(approval_request),
                )
            else:
                await event_manager.publish(
                    "error",
                    {"message": "Redis client not initialized for command approval."},
                )
                return {
                    "approved": False,
                    "message": "Redis client not available for approval.",
                }

            try:
                approval_response = await asyncio.wait_for(approval_future, timeout=300)
                return approval_response
            except asyncio.TimeoutError:
                self.pending_approvals.pop(task_id, None)
                await event_manager.publish(
                    "error", {"message": f"Command approval timeout for: {command}"}
                )
                return {"approved": False, "message": "Approval timeout"}
        else:
            await event_manager.publish(
                "log_message",
                {
                    "level": "WARNING",
                    "message": (
                        "Local approval mechanism not implemented, auto-approving"
                    ),
                },
            )
            return {"approved": True, "message": "Auto-approved for local execution"}

    async def generate_next_action(
        self, goal: str, messages: Optional[List[Dict[str, str]]]
    ):
        return await self.generate_task_plan(goal, messages)


# Removed example usage block
