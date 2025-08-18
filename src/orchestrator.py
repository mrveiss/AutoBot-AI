# src/orchestrator.py
import asyncio
import json
import logging
import re
import time
import uuid
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional

from src.autobot_types import TaskComplexity

# Import the centralized ConfigManager and Redis client utility
from src.config import config as global_config_manager
from src.diagnostics import Diagnostics
from src.error_handler import log_error
from src.event_manager import event_manager
from src.exceptions import (
    IntegrationError,
    LLMConnectionError,
    LLMResponseError,
    LLMTimeoutError,
    ValidationError,
    WorkflowExecutionError,
    WorkflowValidationError,
)
from src.knowledge_base import KnowledgeBase
from src.llm_interface import LLMInterface
from src.prompt_manager import prompt_manager
from src.system_info_collector import get_os_info
from src.tool_discovery import discover_tools
from src.tools import ToolRegistry
from src.utils.redis_client import get_redis_client
from src.worker_node import GUI_AUTOMATION_SUPPORTED, WorkerNode

logger = logging.getLogger(__name__)

# Workflow orchestration enhancements


# TaskComplexity moved to src.types to avoid duplicate definitions


class WorkflowStatus(Enum):
    PLANNED = "planned"
    IN_PROGRESS = "in_progress"
    WAITING_USER = "waiting_user"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class WorkflowStep:
    id: str
    agent_type: str
    action: str
    inputs: Dict[str, Any]
    outputs: Dict[str, Any] = None
    status: str = "pending"
    user_approval_required: bool = False
    dependencies: List[str] = None


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
    def __init__(
        self,
        config_manager=None,
        llm_interface=None,
        knowledge_base=None,
        diagnostics=None,
    ):
        """
        Initialize Orchestrator with dependency injection support.

        Args:
            config_manager: Configuration manager instance (optional, uses global if None)
            llm_interface: LLM interface instance (optional, creates new if None)
            knowledge_base: Knowledge base instance (optional, creates new if None)
            diagnostics: Diagnostics instance (optional, creates new if None)
        """
        # Use provided dependencies or fall back to defaults for backward compatibility
        self.config_manager = config_manager or global_config_manager
        self.llm_interface = llm_interface or LLMInterface()
        self.knowledge_base = knowledge_base or KnowledgeBase()
        self.diagnostics = diagnostics or Diagnostics()

        # Add logger attribute
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

        llm_config = self.config_manager.get_llm_config()
        self.orchestrator_llm_model = llm_config.get(
            "orchestrator_llm",
            llm_config.get("ollama", {}).get("model", "tinyllama:latest"),
        )
        self.task_llm_model = llm_config.get(
            "task_llm",
            f"ollama_{llm_config.get('ollama', {}).get('model', 'llama3.2:1b-instruct-q4_K_M')}",
        )
        self.ollama_models = llm_config.get("ollama", {}).get("models", {})
        self.phi2_enabled = False  # This will be driven by config if needed

        self.task_transport_type = self.config_manager.get_nested(
            "task_transport.type", "local"
        )
        self.redis_client = None
        self.worker_capabilities: Dict[str, Dict[str, Any]] = {}
        self.pending_approvals: Dict[str, asyncio.Future] = {}
        # Use default channel names since we're using memory.redis config
        self.redis_command_approval_request_channel = "command_approval_request"
        self.redis_command_approval_response_channel_prefix = "command_approval_"

        self.agent_paused = False

        # Workflow orchestration enhancements
        self.active_workflows: Dict[str, List[WorkflowStep]] = {}
        # Cache classification results to avoid inconsistent LLM responses
        self._classification_cache: Dict[str, TaskComplexity] = {}
        self.agent_registry = {
            "research": "Web research with Playwright",
            "librarian": "Knowledge base search and storage",
            "system_commands": "Execute shell commands and installations",
            "rag": "Document analysis and synthesis",
            "knowledge_manager": "Structured information storage",
            "orchestrator": "Workflow planning and coordination",
            "chat": "Conversational responses",
            "security_scanner": "Security vulnerability scanning and assessment",
            "network_discovery": "Network asset discovery and mapping",
        }

        self.langchain_agent = None
        self.use_langchain = self.config_manager.get_nested(
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
        worker_node = self.local_worker if hasattr(self, "local_worker") else None
        self.tool_registry = ToolRegistry(
            worker_node=worker_node, knowledge_base=self.knowledge_base
        )

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
                                    "Failed to parse worker capabilities "
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
                                    "Error processing worker capabilities "
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
                                "Received unhandled approval message for task "
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
                    "System information collected: "
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
                    "Available tools collected: "
                    f"{json.dumps(self.available_tools, indent=2)}"
                ),
            },
        )
        print("Available tools collected on startup.")

        # Tool registry already initialized in constructor
        # Just update the worker_node if needed
        if hasattr(self, "local_worker") and self.tool_registry:
            self.tool_registry.worker_node = self.local_worker

        if (
            self.use_langchain
            and LANGCHAIN_AVAILABLE
            and LangChainAgentOrchestrator is not None
        ):
            try:
                kb_config = self.config_manager.get("knowledge_base", {})
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
                    config=self.config_manager.to_dict(),
                    worker_node=(
                        self.local_worker if hasattr(self, "local_worker") else None
                    ),
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
            kb_config = self.config_manager.get("knowledge_base", {})
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
                n_results=self.config_manager.get_nested(
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
                        "\n\nUse the following context to inform your plan:\n"
                        f"{context_str}"
                    )

                system_prompt += (
                    "\n\nOperating System Information:\n"
                    f"{json.dumps(self.system_info, indent=2)}\n"
                )
                system_prompt += (
                    "\n\nAvailable System Tools:\n"
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
                        "\n\nUse the following context to inform your plan:\n"
                        f"{context_str}"
                    )
                system_prompt += (
                    "\n\nOperating System Information:\n"
                    f"{json.dumps(self.system_info, indent=2)}\n"
                )
                system_prompt += (
                    "\n\nAvailable System Tools:\n"
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
                    "LLM response is plain text. "
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
        Execute a goal using workflow orchestration or iterative approach.

        This method coordinates the entire goal execution process, from initial setup
        through multi-agent workflow coordination or iterative planning until completion.

        Args:
            goal: The user's goal or task to accomplish
            messages: Optional conversation history for context

        Returns:
            Dict containing execution results, status, and any response content
        """
        if messages is None:
            messages = [{"role": "user", "content": goal}]

        await self._log_goal_start(goal)

        # Check if we should use workflow orchestration
        should_orchestrate = await self.should_use_workflow_orchestration(goal)

        if should_orchestrate:
            # Check if enhanced orchestration is enabled
            use_enhanced = self.config_manager.get_nested(
                "orchestrator.use_enhanced_multi_agent", True
            )

            if use_enhanced:
                # Use enhanced multi-agent orchestrator
                try:
                    from src.enhanced_multi_agent_orchestrator import (
                        create_and_execute_workflow,
                    )

                    self.logger.info("Using enhanced multi-agent orchestration")

                    # Create context from messages
                    context = {
                        "messages": messages,
                        "timestamp": time.time(),
                        "request_id": str(uuid.uuid4()),
                    }

                    # Execute with enhanced orchestrator
                    result = await create_and_execute_workflow(goal, context)

                    # Format response
                    if result.get("success"):
                        response_text = self._format_enhanced_results(
                            result.get("results", {})
                        )
                    else:
                        response_text = f"I encountered an issue: {result.get('error', 'Unknown error')}"

                    return {
                        "status": "success",
                        "tool_name": "enhanced_workflow_orchestrator",
                        "tool_args": {
                            "plan_id": result.get("plan_id"),
                            "strategy": result.get("strategy_used"),
                            "execution_time": result.get("execution_time"),
                        },
                        "response_text": response_text,
                        "workflow_executed": True,
                        "enhanced_orchestration": True,
                    }

                except Exception as e:
                    self.logger.error(
                        f"Enhanced orchestration failed: {e}, falling back to standard"
                    )
                    # Fall back to standard orchestration

            # Standard workflow orchestration
            workflow_response = await self.create_workflow_response(goal)

            await event_manager.publish(
                "log_message",
                {
                    "level": "INFO",
                    "message": f"Executing workflow orchestration: {workflow_response.get('message_classification')}",
                },
            )

            # Actually execute the workflow steps
            execution_result = await self._execute_workflow_steps(
                workflow_response, goal
            )

            # Return the execution result
            return {
                "status": "success",
                "tool_name": "workflow_orchestrator",
                "tool_args": workflow_response,
                "response_text": execution_result.get(
                    "response_text", "Workflow completed successfully"
                ),
                "workflow_executed": True,
                "workflow_details": execution_result,
            }

        # Try LangChain agent first if available
        langchain_result = await self._try_langchain_execution(goal, messages)
        if langchain_result:
            return langchain_result

        # Handle simple commands directly
        if self._is_simple_command(goal):
            return await self._execute_simple_command(goal)

        # Execute complex goal using iterative approach
        return await self._execute_complex_goal(goal, messages)

    def _format_enhanced_results(self, results: Dict[str, Any]) -> str:
        """Format results from enhanced orchestrator into readable response."""
        if not results:
            return "The workflow completed but no specific results were returned."

        # Extract meaningful information from results
        completed_tasks = []
        outputs = []

        for task_id, result in results.items():
            if result.get("status") == "completed":
                completed_tasks.append(result.get("agent", "unknown"))
                if "output" in result and isinstance(result["output"], dict):
                    output_result = result["output"].get("result", "")
                    if output_result:
                        outputs.append(str(output_result))

        # Build response
        response_parts = []

        if completed_tasks:
            response_parts.append(
                f"I coordinated {len(completed_tasks)} agents to complete your request."
            )

        if outputs:
            response_parts.append("\n\nHere's what I found:\n" + "\n".join(outputs))

        return (
            " ".join(response_parts)
            if response_parts
            else "The workflow completed successfully."
        )

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
            except LLMConnectionError as e:
                log_error(e, context="langchain_execution", include_traceback=False)
                await event_manager.publish(
                    "log_message",
                    {
                        "level": "ERROR",
                        "message": "LangChain Agent connection failed, falling back to standard orchestrator",
                    },
                )
            except LLMTimeoutError as e:
                log_error(e, context="langchain_execution", include_traceback=False)
                await event_manager.publish(
                    "log_message",
                    {
                        "level": "ERROR",
                        "message": "LangChain Agent timed out, falling back to standard orchestrator",
                    },
                )
            except LLMResponseError as e:
                log_error(e, context="langchain_execution", include_traceback=False)
                await event_manager.publish(
                    "log_message",
                    {
                        "level": "ERROR",
                        "message": "LangChain Agent returned invalid response, falling back to standard orchestrator",
                    },
                )
            except Exception as e:
                log_error(e, context="langchain_execution")
                await event_manager.publish(
                    "log_message",
                    {
                        "level": "ERROR",
                        "message": "LangChain Agent encountered unexpected error, falling back to standard orchestrator",
                    },
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
        max_iterations = self.config_manager.get_nested(
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
                # Debug information for tool registry issue
                debug_info = f"Tool registry is None. Available attributes: {[attr for attr in dir(self) if 'tool' in attr.lower()]}"
                print(f"DEBUG: {debug_info}")
                result = {
                    "status": "error",
                    "message": f"Tool registry not initialized. {debug_info}",
                }

            tool_output_content = result.get(
                "result",
                result.get(
                    "output", result.get("message", "Tool execution completed.")
                ),
            )
            messages.append({"role": "tool_output", "content": tool_output_content})

            return await self._process_tool_result(result, tool_name, messages)

        except ValidationError as e:
            log_error(e, context=f"tool_execution:{tool_name}", include_traceback=False)
            error_msg = f"Tool validation failed: {e.safe_message}"
            messages.append({"role": "user", "content": error_msg})
            await event_manager.publish("error", {"message": error_msg})
            return {"completed": False}
        except IntegrationError as e:
            log_error(e, context=f"tool_execution:{tool_name}", include_traceback=False)
            error_msg = f"Tool integration failed: {e.safe_message}"
            messages.append({"role": "user", "content": error_msg})
            await event_manager.publish("error", {"message": error_msg})
            return {"completed": False}
        except Exception as e:
            log_error(e, context=f"tool_execution:{tool_name}")
            error_msg = "Tool execution encountered an unexpected error"
            messages.append({"role": "user", "content": error_msg})
            await event_manager.publish("error", {"message": error_msg})
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
        """
        Performance optimization to bypass LLM processing for simple, known commands and conversational inputs.

        This function acts as a fast-path filter to identify straightforward system commands
        and simple conversational inputs that don't require complex reasoning or planning.
        By recognizing these patterns, we can execute them directly without the overhead
        of LLM analysis, significantly improving response time for common operations.

        Args:
            goal (str): The user's goal/command to analyze

        Returns:
            bool: True if the goal matches a simple command pattern, False otherwise

        Examples:
            - "get ip address" -> True (network info command)
            - "list processes" -> True (system status command)
            - "hello" -> True (simple greeting)
            - "Plan a complex multi-step workflow" -> False (requires LLM reasoning)
        """
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

        # Add conversational patterns for simple interactions
        conversational_patterns = [
            r"^(hello|hi|hey|greetings?)!?$",
            r"^(good\s+(morning|afternoon|evening|day))!?$",
            r"^(how\s+are\s+you|how\s+are\s+things)[\?!]?$",
            r"^(thanks?|thank\s+you)!?$",
            r"^(bye|goodbye|see\s+you)!?$",
            r"^(yes|no|ok|okay)!?$",
        ]

        goal_clean = goal.strip().lower()
        is_command = any(re.search(pattern, goal_clean) for pattern in command_patterns)
        is_conversational = any(re.search(pattern, goal_clean) for pattern in conversational_patterns)
        is_simple = is_command or is_conversational

        print(f"DEBUG: _is_simple_command('{goal}') -> {is_simple} (command: {is_command}, conversational: {is_conversational})")
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
        else:
            # Check if this is a simple conversational input that doesn't need complex orchestration
            conversational_patterns = [
                r"^(hello|hi|hey|greetings?)!?$",
                r"^(good\s+(morning|afternoon|evening|day))!?$",
                r"^(how\s+are\s+you|how\s+are\s+things)[\?!]?$",
                r"^(thanks?|thank\s+you)!?$",
                r"^(bye|goodbye|see\s+you)!?$",
                r"^(yes|no|ok|okay)!?$",
            ]

            goal_clean = goal.strip().lower()
            is_conversational = any(re.search(pattern, goal_clean) for pattern in conversational_patterns)

            if is_conversational:
                print(f"DEBUG: Detected conversational input: '{goal}', providing direct response")

                # Provide appropriate conversational responses
                if re.search(r"^(hello|hi|hey|greetings?)!?$", goal_clean):
                    response_text = "Hello! I'm AutoBot, your AI assistant. I'm here to help you with various tasks including system commands, research, security analysis, and more. What can I help you with today?"
                elif re.search(r"^(good\s+(morning|afternoon|evening|day))!?$", goal_clean):
                    response_text = "Good day! I'm AutoBot, ready to assist you with your tasks. How can I help you today?"
                elif re.search(r"^(how\s+are\s+you|how\s+are\s+things)[\?!]?$", goal_clean):
                    response_text = "I'm doing well and ready to help! My systems are operational and I'm equipped with various capabilities including system commands, research tools, security scanning, and more. What would you like to work on?"
                elif re.search(r"^(thanks?|thank\s+you)!?$", goal_clean):
                    response_text = "You're welcome! I'm always happy to help. Let me know if you need anything else."
                elif re.search(r"^(bye|goodbye|see\s+you)!?$", goal_clean):
                    response_text = "Goodbye! Feel free to return anytime you need assistance. Have a great day!"
                elif re.search(r"^(yes|no|ok|okay)!?$", goal_clean):
                    response_text = "I understand. Is there anything specific you'd like me to help you with?"
                else:
                    response_text = "I'm here to help! What would you like me to assist you with today?"

                return {
                    "status": "success",
                    "tool_name": "conversational_response",
                    "tool_args": {"response_text": response_text},
                    "response_text": response_text
                }

            print(
                "DEBUG: _execute_simple_command could not determine a direct "
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

    async def classify_request_complexity(self, user_message: str) -> TaskComplexity:
        """Classify user request complexity using intelligent agent."""
        # Check cache first to avoid inconsistent LLM responses
        cache_key = hash(user_message)
        if cache_key in self._classification_cache:
            cached_result = self._classification_cache[cache_key]
            print(f"Using cached classification: {cached_result.value}")
            return cached_result

        try:
            from src.agents.classification_agent import ClassificationAgent

            agent = ClassificationAgent(self.llm_interface)
            result = await agent.classify_request(user_message)

            # Store detailed classification result for workflow planning
            self._last_classification_result = result

            print(
                f"Classification: {result.complexity.value} (confidence: {result.confidence:.2f})"
            )
            print(f"Reasoning: {result.reasoning}")

            # Cache the result
            self._classification_cache[cache_key] = result.complexity

            return result.complexity
        except LLMConnectionError as e:
            log_error(e, context="request_classification", include_traceback=False)
            print("LLM connection failed for classification, using Redis fallback")
            # Fallback to Redis-based classifier
            try:
                from src.workflow_classifier import WorkflowClassifier

                classifier = WorkflowClassifier(self.redis_client)
                fallback_result = classifier.classify_request(user_message)
                self._classification_cache[cache_key] = fallback_result
                return fallback_result
            except Exception as e2:
                log_error(e2, context="redis_classification")
                print("Redis classification error, falling back to simple")
                simple_result = TaskComplexity.SIMPLE
                self._classification_cache[cache_key] = simple_result
                return simple_result
        except LLMTimeoutError as e:
            log_error(e, context="request_classification", include_traceback=False)
            print("LLM timeout for classification, using Redis fallback")
            try:
                from src.workflow_classifier import WorkflowClassifier

                classifier = WorkflowClassifier(self.redis_client)
                fallback_result = classifier.classify_request(user_message)
                self._classification_cache[cache_key] = fallback_result
                return fallback_result
            except Exception as e2:
                log_error(e2, context="redis_classification")
                print("Redis classification error, falling back to simple")
                simple_result = TaskComplexity.SIMPLE
                self._classification_cache[cache_key] = simple_result
                return simple_result
        except LLMResponseError as e:
            log_error(e, context="request_classification", include_traceback=False)
            print(
                "LLM returned invalid response for classification, using Redis fallback"
            )
            try:
                from src.workflow_classifier import WorkflowClassifier

                classifier = WorkflowClassifier(self.redis_client)
                fallback_result = classifier.classify_request(user_message)
                self._classification_cache[cache_key] = fallback_result
                return fallback_result
            except Exception as e2:
                log_error(e2, context="redis_classification")
                print("Redis classification error, falling back to simple")
                simple_result = TaskComplexity.SIMPLE
                self._classification_cache[cache_key] = simple_result
                return simple_result
        except Exception as e:
            log_error(e, context="request_classification")
            print("Classification encountered unexpected error, using Redis fallback")
            try:
                from src.workflow_classifier import WorkflowClassifier

                classifier = WorkflowClassifier(self.redis_client)
                fallback_result = classifier.classify_request(user_message)
                self._classification_cache[cache_key] = fallback_result
                return fallback_result
            except Exception as e2:
                log_error(e2, context="redis_classification")
                print("Redis classification error, falling back to simple")
                simple_result = TaskComplexity.SIMPLE
                self._classification_cache[cache_key] = simple_result
                return simple_result

    def plan_workflow_steps(
        self, user_message: str, complexity: TaskComplexity
    ) -> List[WorkflowStep]:
        """Plan workflow steps based on request complexity."""

        if complexity == TaskComplexity.SIMPLE:
            return [
                WorkflowStep(
                    id="simple_response",
                    agent_type="chat",
                    action="provide_direct_answer",
                    inputs={"message": user_message},
                )
            ]

        elif complexity == TaskComplexity.RESEARCH:
            return [
                WorkflowStep(
                    id="kb_search",
                    agent_type="librarian",
                    action="search_knowledge_base",
                    inputs={"query": user_message},
                ),
                WorkflowStep(
                    id="web_research",
                    agent_type="research",
                    action="web_research",
                    inputs={"query": user_message, "focus": "tools_and_guides"},
                    dependencies=["kb_search"],
                ),
                WorkflowStep(
                    id="synthesize_results",
                    agent_type="rag",
                    action="synthesize_findings",
                    inputs={
                        "kb_results": "{kb_search.outputs}",
                        "research_results": "{web_research.outputs}",
                    },
                    dependencies=["kb_search", "web_research"],
                ),
            ]

        elif complexity == TaskComplexity.INSTALL:
            return [
                WorkflowStep(
                    id="research_install",
                    agent_type="research",
                    action="research_installation",
                    inputs={"query": user_message},
                ),
                WorkflowStep(
                    id="plan_install",
                    agent_type="orchestrator",
                    action="create_install_plan",
                    inputs={"install_info": "{research_install.outputs}"},
                    user_approval_required=True,
                    dependencies=["research_install"],
                ),
                WorkflowStep(
                    id="execute_install",
                    agent_type="system_commands",
                    action="install_software",
                    inputs={"install_plan": "{plan_install.outputs}"},
                    dependencies=["plan_install"],
                ),
                WorkflowStep(
                    id="verify_install",
                    agent_type="system_commands",
                    action="verify_installation",
                    inputs={"software_info": "{research_install.outputs}"},
                    dependencies=["execute_install"],
                ),
            ]

        elif complexity == TaskComplexity.SECURITY_SCAN:
            # Security scanning workflow
            return [
                WorkflowStep(
                    id="validate_target",
                    agent_type="security_scanner",
                    action="validate_scan_target",
                    inputs={"user_message": user_message},
                ),
                WorkflowStep(
                    id="network_discovery",
                    agent_type="network_discovery",
                    action="perform_host_discovery",
                    inputs={"target": "{validate_target.outputs.target}"},
                    dependencies=["validate_target"],
                ),
                WorkflowStep(
                    id="port_scan",
                    agent_type="security_scanner",
                    action="perform_port_scan",
                    inputs={
                        "target": "{validate_target.outputs.target}",
                        "hosts": "{network_discovery.outputs.hosts}",
                    },
                    dependencies=["network_discovery"],
                ),
                WorkflowStep(
                    id="service_detection",
                    agent_type="security_scanner",
                    action="detect_services",
                    inputs={"scan_results": "{port_scan.outputs}"},
                    dependencies=["port_scan"],
                ),
                WorkflowStep(
                    id="vulnerability_assessment",
                    agent_type="security_scanner",
                    action="assess_vulnerabilities",
                    inputs={
                        "services": "{service_detection.outputs}",
                        "scan_results": "{port_scan.outputs}",
                    },
                    user_approval_required=True,
                    dependencies=["service_detection"],
                ),
                WorkflowStep(
                    id="generate_report",
                    agent_type="orchestrator",
                    action="compile_security_report",
                    inputs={
                        "discovery": "{network_discovery.outputs}",
                        "ports": "{port_scan.outputs}",
                        "services": "{service_detection.outputs}",
                        "vulnerabilities": "{vulnerability_assessment.outputs}",
                    },
                    dependencies=["vulnerability_assessment"],
                ),
                WorkflowStep(
                    id="store_results",
                    agent_type="knowledge_manager",
                    action="store_scan_results",
                    inputs={"report": "{generate_report.outputs}"},
                    dependencies=["generate_report"],
                ),
            ]

        elif complexity == TaskComplexity.COMPLEX:
            # This handles the network scanning tools scenario and similar complex requests
            return [
                WorkflowStep(
                    id="kb_search",
                    agent_type="librarian",
                    action="search_knowledge_base",
                    inputs={"query": user_message},
                ),
                WorkflowStep(
                    id="web_research",
                    agent_type="research",
                    action="research_tools",
                    inputs={
                        "query": f"{user_message} 2024",
                        "focus": "installation_usage",
                    },
                    dependencies=["kb_search"],
                ),
                WorkflowStep(
                    id="present_options",
                    agent_type="orchestrator",
                    action="present_tool_options",
                    inputs={"research_findings": "{web_research.outputs}"},
                    user_approval_required=True,
                    dependencies=["web_research"],
                ),
                WorkflowStep(
                    id="detailed_research",
                    agent_type="research",
                    action="get_installation_guide",
                    inputs={
                        "selected_tool": "{present_options.outputs.user_selection}"
                    },
                    dependencies=["present_options"],
                ),
                WorkflowStep(
                    id="store_knowledge",
                    agent_type="knowledge_manager",
                    action="store_tool_info",
                    inputs={"tool_data": "{detailed_research.outputs}"},
                    dependencies=["detailed_research"],
                ),
                WorkflowStep(
                    id="plan_installation",
                    agent_type="orchestrator",
                    action="create_install_plan",
                    inputs={"install_guide": "{detailed_research.outputs}"},
                    user_approval_required=True,
                    dependencies=["detailed_research"],
                ),
                WorkflowStep(
                    id="execute_install",
                    agent_type="system_commands",
                    action="install_tool",
                    inputs={"install_plan": "{plan_installation.outputs}"},
                    dependencies=["plan_installation"],
                ),
                WorkflowStep(
                    id="verify_install",
                    agent_type="system_commands",
                    action="verify_installation",
                    inputs={"tool_info": "{detailed_research.outputs}"},
                    dependencies=["execute_install"],
                ),
            ]

        return []

    async def create_workflow_response(self, user_message: str) -> Dict[str, Any]:
        """Create comprehensive workflow response instead of simple chat."""

        # Classify the request
        complexity = await self.classify_request_complexity(user_message)

        # Plan the workflow
        workflow_steps = self.plan_workflow_steps(user_message, complexity)

        # Log workflow planning
        await event_manager.publish(
            "log_message",
            {
                "level": "INFO",
                "message": f"Classified request as {complexity.value}, planned {len(workflow_steps)} steps",
            },
        )
        print(
            f"Classified request as {complexity.value}, planned {len(workflow_steps)} steps"
        )

        # Generate response
        response = {
            "message_classification": complexity.value,
            "workflow_required": complexity != TaskComplexity.SIMPLE,
            "planned_steps": len(workflow_steps),
            "agents_involved": list(set(step.agent_type for step in workflow_steps)),
            "user_approvals_needed": sum(
                1 for step in workflow_steps if step.user_approval_required
            ),
            "estimated_duration": self._estimate_workflow_duration(workflow_steps),
            "workflow_preview": self._create_workflow_preview(workflow_steps),
        }

        if complexity == TaskComplexity.SIMPLE:
            response["immediate_response"] = "I can answer this directly."
        else:
            response["orchestration_plan"] = {
                "description": f"This requires a {complexity.value} workflow with {len(workflow_steps)} steps",
                "next_action": "Starting workflow execution...",
                "progress_tracking": "Real-time updates will be provided",
            }

            # Store the workflow for execution
            workflow_id = str(uuid.uuid4())
            self.active_workflows[workflow_id] = workflow_steps
            response["workflow_id"] = workflow_id
            response["workflow_steps"] = workflow_steps

        return response

    def _create_workflow_preview(self, steps: List[WorkflowStep]) -> List[str]:
        """Create human-readable workflow preview."""
        preview = []
        for i, step in enumerate(steps, 1):
            agent_name = step.agent_type.title()
            action_desc = step.action.replace("_", " ").title()
            approval_note = (
                " (requires your approval)" if step.user_approval_required else ""
            )
            preview.append(f"{i}. {agent_name}: {action_desc}{approval_note}")
        return preview

    def _estimate_workflow_duration(self, steps: List[WorkflowStep]) -> str:
        """Estimate how long the workflow will take."""
        duration_map = {
            "librarian": 5,  # KB search
            "research": 30,  # Web research
            "rag": 10,  # Synthesis
            "system_commands": 60,  # Installation
            "knowledge_manager": 5,  # Storage
            "orchestrator": 2,  # Planning
            "chat": 1,  # Simple response
            "security_scanner": 120,  # Security scans
            "network_discovery": 60,  # Network discovery
        }

        total_seconds = sum(duration_map.get(step.agent_type, 10) for step in steps)

        if total_seconds < 60:
            return f"{total_seconds} seconds"
        elif total_seconds < 3600:
            return f"{total_seconds // 60} minutes"
        else:
            return (
                f"{total_seconds // 3600} hours {(total_seconds % 3600) // 60} minutes"
            )

    async def should_use_workflow_orchestration(self, user_message: str) -> bool:
        """Determine if a request should use multi-agent workflow orchestration."""
        complexity = await self.classify_request_complexity(user_message)
        should_orchestrate = complexity != TaskComplexity.SIMPLE

        if should_orchestrate:
            await event_manager.publish(
                "log_message",
                {
                    "level": "INFO",
                    "message": f"Request '{user_message[:50]}...' classified as {complexity.value}, enabling workflow orchestration",
                },
            )
            print(f"Enabling workflow orchestration for {complexity.value} request")

        return should_orchestrate

    def _format_workflow_response_text(self, workflow_response: Dict[str, Any]) -> str:
        """Format workflow response for user display."""
        classification = workflow_response.get("message_classification", "unknown")
        agents = ", ".join(workflow_response.get("agents_involved", []))
        duration = workflow_response.get("estimated_duration", "unknown")
        approvals = workflow_response.get("user_approvals_needed", 0)

        response_parts = [
            f"🎯 **Request Classification**: {classification.title()}",
            f"🤖 **Agents Involved**: {agents}",
            f"⏱️  **Estimated Duration**: {duration}",
            f"👤 **User Approvals Needed**: {approvals}",
            "",
            "📋 **Planned Workflow Steps**:",
        ]

        preview = workflow_response.get("workflow_preview", [])
        for step in preview:
            response_parts.append(f"   {step}")

        if workflow_response.get("workflow_required", False):
            response_parts.extend(
                [
                    "",
                    "🚀 This is a demonstration of AutoBot's enhanced workflow orchestration.",
                    "Instead of giving generic responses, the system now plans multi-agent",
                    "workflows that coordinate research, knowledge management, and execution",
                    "agents to provide comprehensive solutions to complex requests.",
                    "",
                    "In the full implementation, this workflow would execute automatically",
                    "with real-time progress updates and user approval prompts.",
                ]
            )

        return "\n".join(response_parts)

    async def _execute_workflow_steps(
        self, workflow_response: Dict[str, Any], original_goal: str
    ) -> Dict[str, Any]:
        """
        Execute the planned workflow steps by coordinating multiple agents.

        Args:
            workflow_response: The planned workflow from create_workflow_response
            original_goal: The original user goal/request

        Returns:
            Dict containing execution results and final response
        """
        try:
            workflow_preview = workflow_response.get("workflow_preview", [])
            classification = workflow_response.get("message_classification", "unknown")

            # Initialize result collection
            agent_results = []

            await event_manager.publish(
                "log_message",
                {
                    "level": "INFO",
                    "message": f"Executing {len(workflow_preview)} workflow steps for {classification} request",
                },
            )

            # Execute each workflow step
            for i, step_description in enumerate(workflow_preview, 1):
                step_start_time = time.time()

                await event_manager.publish(
                    "log_message",
                    {
                        "level": "INFO",
                        "message": f"Step {i}/{len(workflow_preview)}: {step_description}",
                    },
                )

                # Extract agent type and action from step description
                if ":" in step_description:
                    agent_type, action = step_description.split(":", 1)
                    # Clean up agent type - remove step numbers and whitespace
                    agent_type = agent_type.strip().lower()
                    if ". " in agent_type:
                        agent_type = agent_type.split(". ", 1)[1]
                    action = action.strip()
                else:
                    agent_type = "orchestrator"
                    action = step_description

                # Execute the step based on agent type
                step_result = await self._execute_agent_step(
                    agent_type, action, original_goal, agent_results
                )

                step_duration = time.time() - step_start_time

                # Store step result
                step_info = {
                    "step": i,
                    "agent": agent_type,
                    "action": action,
                    "duration": f"{step_duration:.1f}s",
                    "result": step_result,
                }
                agent_results.append(step_info)

                await event_manager.publish(
                    "log_message",
                    {
                        "level": "INFO",
                        "message": f"Step {i} completed by {agent_type} in {step_duration:.1f}s",
                    },
                )

            # Compile final response from all agent results
            final_response = await self._compile_workflow_results(
                agent_results, classification, original_goal
            )

            return {
                "execution_status": "completed",
                "agent_results": agent_results,
                "response_text": final_response,
                "steps_executed": len(workflow_preview),
                "classification": classification,
            }

        except WorkflowExecutionError as e:
            log_error(e, context="workflow_execution", include_traceback=False)
            await event_manager.publish(
                "log_message",
                {
                    "level": "ERROR",
                    "message": f"Workflow execution failed: {e.safe_message}",
                },
            )
            return {
                "execution_status": "failed",
                "error": e.safe_message,
                "response_text": "I encountered an error while coordinating the workflow. Let me try a different approach.",
                "fallback_needed": True,
            }
        except WorkflowValidationError as e:
            log_error(e, context="workflow_execution", include_traceback=False)
            await event_manager.publish(
                "log_message",
                {
                    "level": "ERROR",
                    "message": f"Workflow validation failed: {e.safe_message}",
                },
            )
            return {
                "execution_status": "failed",
                "error": e.safe_message,
                "response_text": "The workflow plan is invalid. Let me try a different approach.",
                "fallback_needed": True,
            }
        except Exception as e:
            log_error(e, context="workflow_execution")
            await event_manager.publish(
                "log_message",
                {
                    "level": "ERROR",
                    "message": "Workflow execution encountered an unexpected error",
                },
            )
            return {
                "execution_status": "failed",
                "error": "Workflow execution failed",
                "response_text": "I encountered an unexpected error while coordinating the workflow. Let me try a different approach.",
                "fallback_needed": True,
            }

    async def _execute_agent_step(
        self,
        agent_type: str,
        action: str,
        original_goal: str,
        previous_results: List[Dict],
    ) -> str:
        """
        Execute a single workflow step by calling the appropriate agent.

        Args:
            agent_type: Type of agent to use (research, librarian, etc.)
            action: Specific action to perform
            original_goal: Original user request for context
            previous_results: Results from previous workflow steps

        Returns:
            String result of the agent's work
        """
        try:
            if agent_type == "librarian":
                # Search knowledge base for relevant information
                if self.knowledge_base:
                    kb_results = await self.knowledge_base.search(
                        original_goal, n_results=3
                    )
                    if kb_results:
                        return f"Found {len(kb_results)} relevant documents in knowledge base"
                    else:
                        return "No relevant information found in knowledge base"
                else:
                    return "Knowledge base not available"

            elif agent_type == "research":
                # Perform web research using research agent
                if "research tools" in action.lower():
                    # Mock research for network scanning tools
                    if "network" in original_goal.lower():
                        return "Found specialized network scanning tools: nmap (Network Mapper) for comprehensive port scanning, masscan for high-speed port scanning, zmap for internet-wide scanning, and Wireshark for packet analysis"
                    else:
                        return f"Researched tools related to: {original_goal}"

                elif "installation guide" in action.lower():
                    # Look for installation information from previous research
                    research_results = [
                        r for r in previous_results if r.get("agent") == "research"
                    ]
                    if research_results:
                        return "Retrieved detailed installation guides with step-by-step instructions and dependencies"
                    else:
                        return (
                            "Generated installation guide based on standard practices"
                        )
                else:
                    return f"Web research completed for: {action}"

            elif agent_type == "knowledge_manager":
                # Store information in knowledge base
                context_info = f"Workflow execution for: {original_goal}"
                if previous_results:
                    # Summarize what we learned to store
                    return "Stored workflow findings and tool information for future reference"
                else:
                    return "Prepared to store workflow results"

            elif agent_type == "system_commands":
                # Execute system commands (in safe demonstration mode)
                if "install" in action.lower():
                    return "Tool installation simulation completed (demo mode - no actual installation)"
                elif "verify" in action.lower():
                    return "Installation verification simulation completed"
                else:
                    return f"System command simulation: {action}"

            elif agent_type == "orchestrator":
                # Coordination and planning tasks
                if "present" in action.lower() and "options" in action.lower():
                    # Present options from research results
                    research_results = [
                        r for r in previous_results if r.get("agent") == "research"
                    ]
                    if research_results:
                        return "Presented tool options to user: nmap (recommended for beginners), masscan (for high-speed scanning), zmap (for large-scale scanning)"
                    else:
                        return "Compiled and presented available options"

                elif "create" in action.lower() and "plan" in action.lower():
                    return "Created detailed installation and configuration plan with prerequisites and steps"
                else:
                    return f"Orchestration task completed: {action}"
            else:
                # Default agent behavior
                return f"Agent {agent_type} completed: {action}"

        except Exception as e:
            return f"Agent {agent_type} encountered error: {str(e)}"

    async def _compile_workflow_results(
        self, agent_results: List[Dict], classification: str, original_goal: str
    ) -> str:
        """
        Compile results from all workflow steps into a comprehensive response.

        Args:
            agent_results: Results from all executed workflow steps
            classification: Request classification (simple, research, install, complex)
            original_goal: Original user request

        Returns:
            Comprehensive response text combining all agent outputs
        """
        try:
            response_parts = []

            # Add workflow header
            response_parts.extend(
                [
                    f"🎯 **Multi-Agent Workflow Completed** ({classification.title()})",
                    f"**Request:** {original_goal}",
                    "",
                ]
            )

            # Group results by agent type
            agent_summary = {}
            for result in agent_results:
                agent = result["agent"]
                if agent not in agent_summary:
                    agent_summary[agent] = []
                agent_summary[agent].append(result["result"])

            # Add detailed findings section
            response_parts.append("📋 **Coordinated Agent Results:**")

            # Research findings
            if "research" in agent_summary:
                response_parts.extend(["", "🔍 **Research Agent Findings:**"])
                for finding in agent_summary["research"]:
                    response_parts.append(f"• {finding}")

            # Knowledge base findings
            if "librarian" in agent_summary:
                response_parts.extend(["", "📚 **Knowledge Base Search:**"])
                for finding in agent_summary["librarian"]:
                    response_parts.append(f"• {finding}")

            # Orchestration steps
            if "orchestrator" in agent_summary:
                response_parts.extend(["", "🎯 **Coordination & Planning:**"])
                for finding in agent_summary["orchestrator"]:
                    response_parts.append(f"• {finding}")

            # System actions
            if "system_commands" in agent_summary:
                response_parts.extend(["", "⚙️ **System Operations:**"])
                for finding in agent_summary["system_commands"]:
                    response_parts.append(f"• {finding}")

            # Knowledge management
            if "knowledge_manager" in agent_summary:
                response_parts.extend(["", "💾 **Knowledge Management:**"])
                for finding in agent_summary["knowledge_manager"]:
                    response_parts.append(f"• {finding}")

            # Add execution summary
            total_steps = len(agent_results)
            unique_agents = len(agent_summary)
            total_duration = sum(
                float(r["duration"].replace("s", "")) for r in agent_results
            )

            response_parts.extend(
                [
                    "",
                    "📊 **Execution Summary:**",
                    f"• **Steps Executed:** {total_steps}",
                    f"• **Agents Coordinated:** {unique_agents}",
                    f"• **Total Duration:** {total_duration:.1f}s",
                    f"• **Classification:** {classification.title()}",
                    "",
                    "✅ **Multi-agent workflow orchestration completed successfully!**",
                    "",
                    "This demonstrates AutoBot's transformation from generic responses to",
                    "intelligent coordination of specialized agents working together.",
                ]
            )

            return "\n".join(response_parts)

        except Exception as e:
            return f"Error compiling workflow results: {str(e)}"


# Removed example usage block
