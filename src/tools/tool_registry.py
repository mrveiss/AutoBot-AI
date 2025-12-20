# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Unified Tool Registry

This module provides a centralized implementation of all tools used by both
the standard orchestrator and LangChain orchestrator, eliminating code
duplication.
"""

import logging
import time
import uuid
from typing import TYPE_CHECKING, Any, Dict, List, Optional


if TYPE_CHECKING:
    from src.knowledge_base import KnowledgeBase
    from src.worker_node import WorkerNode

logger = logging.getLogger(__name__)

# Performance optimization: O(1) lookup for tool name matching (Issue #326)
EXECUTE_COMMAND_VARIANTS = {"executesystemcommand", "systemexecutecommand"}
QUERY_SYSTEM_INFO_VARIANTS = {"querysysteminformation", "systemqueryinfo"}
LIST_SERVICES_VARIANTS = {"listsystemservices", "systemlistservices"}
MANAGE_SERVICE_VARIANTS = {"manageservice", "systemmanageservice"}
GET_PROCESS_INFO_VARIANTS = {"getprocessinfo", "systemgetprocessinfo"}
TERMINATE_PROCESS_VARIANTS = {"terminateprocess", "systemterminateprocess"}


class ToolRegistry:
    """
    Unified tool registry that provides standardized tool implementations
    for both orchestrator types, eliminating code duplication.
    """

    def __init__(
        self,
        worker_node: Optional["WorkerNode"] = None,
        knowledge_base: Optional["KnowledgeBase"] = None,
    ):
        """
        Initialize the tool registry with required dependencies.

        Args:
            worker_node: Worker node for task execution
            knowledge_base: Knowledge base for information retrieval
        """
        self.worker_node = worker_node
        self.knowledge_base = knowledge_base
        self.logger = logging.getLogger(__name__)

    def _generate_task_id(self) -> str:
        """Generate a unique task ID."""
        return str(uuid.uuid4())

    def _create_base_task(self, task_type: str) -> Dict[str, Any]:
        """Create a base task dictionary with common fields."""
        return {
            "task_id": self._generate_task_id(),
            "type": task_type,
            "user_role": "user",
            "timestamp": time.time(),
        }

    async def _execute_worker_task(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute a task via the worker node.

        Args:
            task: Task dictionary to execute

        Returns:
            Task execution result
        """
        if not self.worker_node:
            return {"status": "error", "message": "Worker node not available"}

        try:
            result = await self.worker_node.execute_task(task)
            return result
        except Exception as e:
            self.logger.error("Error executing task %s: %s", task.get('task_id'), e)
            return {"status": "error", "message": str(e)}

    # System Integration Tools

    async def execute_system_command(self, command: str) -> Dict[str, Any]:
        """Execute a system command."""
        task = self._create_base_task("system_execute_command")
        task["command"] = command

        result = await self._execute_worker_task(task)
        return {
            "tool_name": "execute_system_command",
            "tool_args": {"command": command},
            "result": result.get("output", result.get("message", "Command executed")),
            "status": result.get("status", "success"),
        }

    async def query_system_information(self) -> Dict[str, Any]:
        """Query system information."""
        task = self._create_base_task("system_query_info")

        result = await self._execute_worker_task(task)
        return {
            "tool_name": "query_system_information",
            "tool_args": {},
            "result": result.get(
                "output", result.get("message", "System info retrieved")
            ),
            "status": result.get("status", "success"),
        }

    async def list_system_services(self) -> Dict[str, Any]:
        """List system services."""
        task = self._create_base_task("system_list_services")

        result = await self._execute_worker_task(task)
        return {
            "tool_name": "list_system_services",
            "tool_args": {},
            "result": result.get("output", result.get("message", "Services listed")),
            "status": result.get("status", "success"),
        }

    async def manage_service(self, service_name: str, action: str) -> Dict[str, Any]:
        """Manage a system service."""
        task = self._create_base_task("system_manage_service")
        task["service_name"] = service_name
        task["action"] = action

        result = await self._execute_worker_task(task)
        return {
            "tool_name": "manage_service",
            "tool_args": {"service_name": service_name, "action": action},
            "result": result.get(
                "output",
                result.get("message", f"Service {service_name} {action} completed"),
            ),
            "status": result.get("status", "success"),
        }

    async def get_process_info(
        self, process_name: Optional[str] = None, pid: Optional[str] = None
    ) -> Dict[str, Any]:
        """Get process information."""
        task = self._create_base_task("system_get_process_info")
        if process_name:
            task["process_name"] = process_name
        if pid:
            task["pid"] = pid

        result = await self._execute_worker_task(task)
        return {
            "tool_name": "get_process_info",
            "tool_args": {"process_name": process_name, "pid": pid},
            "result": result.get(
                "output", result.get("message", "Process info retrieved")
            ),
            "status": result.get("status", "success"),
        }

    async def terminate_process(self, pid: str) -> Dict[str, Any]:
        """Terminate a process by PID."""
        task = self._create_base_task("system_terminate_process")
        task["pid"] = pid

        result = await self._execute_worker_task(task)
        return {
            "tool_name": "terminate_process",
            "tool_args": {"pid": pid},
            "result": result.get(
                "output", result.get("message", f"Process {pid} terminated")
            ),
            "status": result.get("status", "success"),
        }

    async def web_fetch(self, url: str) -> Dict[str, Any]:
        """Fetch content from a web URL."""
        task = self._create_base_task("web_fetch")
        task["url"] = url

        result = await self._execute_worker_task(task)
        return {
            "tool_name": "web_fetch",
            "tool_args": {"url": url},
            "result": result.get(
                "output", result.get("message", "Web content fetched")
            ),
            "status": result.get("status", "success"),
        }

    # Knowledge Base Tools

    async def search_knowledge_base(
        self, query: str, n_results: int = 5
    ) -> Dict[str, Any]:
        """Search the knowledge base."""
        if not self.knowledge_base:
            return {
                "tool_name": "search_knowledge_base",
                "tool_args": {"query": query, "n_results": n_results},
                "result": "Knowledge base is not available",
                "status": "error",
            }

        try:
            results = await self.knowledge_base.search(query, n_results=n_results)

            if results:
                formatted_results = []
                for result in results:
                    content_preview = (
                        result["content"][:200] + "..."
                        if len(result["content"]) > 200
                        else result["content"]
                    )
                    metadata = result.get("metadata", {})
                    filename = metadata.get("filename", "N/A")
                    chunk_index = metadata.get("chunk_index", "N/A")
                    formatted_results.append(
                        f"[{filename} - Chunk {chunk_index}]: " f"{content_preview}"
                    )

                result_text = f"Found {len(results)} relevant results:\n" + "\n".join(
                    formatted_results
                )
            else:
                result_text = "No relevant information found in knowledge base"

            return {
                "tool_name": "search_knowledge_base",
                "tool_args": {"query": query, "n_results": n_results},
                "result": result_text,
                "status": "success",
            }
        except Exception as e:
            self.logger.error("Error searching knowledge base: %s", e)
            return {
                "tool_name": "search_knowledge_base",
                "tool_args": {"query": query, "n_results": n_results},
                "result": f"Error searching knowledge base: {e}",
                "status": "error",
            }

    async def add_file_to_knowledge_base(
        self, file_path: str, file_type: str, metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Add a file to the knowledge base."""
        if not self.knowledge_base:
            return {
                "tool_name": "add_file_to_knowledge_base",
                "tool_args": {"file_path": file_path, "file_type": file_type},
                "result": "Knowledge base is not available",
                "status": "error",
            }

        try:
            result = await self.knowledge_base.add_file(
                file_path, file_type, metadata or {}
            )
            return {
                "tool_name": "add_file_to_knowledge_base",
                "tool_args": {
                    "file_path": file_path,
                    "file_type": file_type,
                    "metadata": metadata,
                },
                "result": result.get(
                    "message", f"File {file_path} added to knowledge base"
                ),
                "status": result.get("status", "success"),
            }
        except Exception as e:
            self.logger.error("Error adding file to knowledge base: %s", e)
            return {
                "tool_name": "add_file_to_knowledge_base",
                "tool_args": {
                    "file_path": file_path,
                    "file_type": file_type,
                    "metadata": metadata,
                },
                "result": f"Error adding file to knowledge base: {e}",
                "status": "error",
            }

    async def store_fact(
        self, content: str, metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Store a fact in the knowledge base."""
        if not self.knowledge_base:
            return {
                "tool_name": "store_fact",
                "tool_args": {"content": content, "metadata": metadata},
                "result": "Knowledge base is not available",
                "status": "error",
            }

        try:
            result = await self.knowledge_base.store_fact(content, metadata or {})
            return {
                "tool_name": "store_fact",
                "tool_args": {"content": content, "metadata": metadata},
                "result": result.get("message", "Fact stored successfully"),
                "status": result.get("status", "success"),
            }
        except Exception as e:
            self.logger.error("Error storing fact: %s", e)
            return {
                "tool_name": "store_fact",
                "tool_args": {"content": content, "metadata": metadata},
                "result": f"Error storing fact: {e}",
                "status": "error",
            }

    async def get_fact(
        self, fact_id: Optional[int] = None, query: Optional[str] = None
    ) -> Dict[str, Any]:
        """Get facts from the knowledge base."""
        if not self.knowledge_base:
            return {
                "tool_name": "get_fact",
                "tool_args": {"fact_id": fact_id, "query": query},
                "result": "Knowledge base is not available",
                "status": "error",
            }

        try:
            results = await self.knowledge_base.get_fact(fact_id=fact_id, query=query)

            if results:
                formatted_results = []
                for result in results:
                    fact_id = result.get("id", "N/A")
                    content = result.get("content", "No content")
                    formatted_results.append(f"Fact {fact_id}: {content}")

                result_text = "\n".join(formatted_results)
            else:
                result_text = "No facts found"

            return {
                "tool_name": "get_fact",
                "tool_args": {"fact_id": fact_id, "query": query},
                "result": result_text,
                "status": "success",
            }
        except Exception as e:
            self.logger.error("Error getting facts: %s", e)
            return {
                "tool_name": "get_fact",
                "tool_args": {"fact_id": fact_id, "query": query},
                "result": f"Error getting facts: {e}",
                "status": "error",
            }

    # GUI Automation Tools

    async def type_text(self, text: str) -> Dict[str, Any]:
        """Type text into the active window."""
        task = self._create_base_task("gui_type_text")
        task["text"] = text

        result = await self._execute_worker_task(task)
        return {
            "tool_name": "type_text",
            "tool_args": {"text": text},
            "result": result.get(
                "output", result.get("message", f"Typed text: {text}")
            ),
            "status": result.get("status", "success"),
        }

    async def click_element(self, image_path: str) -> Dict[str, Any]:
        """Click on a GUI element by image."""
        task = self._create_base_task("gui_click_element")
        task["image_path"] = image_path

        result = await self._execute_worker_task(task)
        return {
            "tool_name": "click_element",
            "tool_args": {"image_path": image_path},
            "result": result.get(
                "output",
                result.get("message", f"Clicked element: {image_path}"),
            ),
            "status": result.get("status", "success"),
        }

    async def bring_window_to_front(self, window_title: str) -> Dict[str, Any]:
        """Bring a window to the front."""
        task = self._create_base_task("gui_bring_window_to_front")
        task["window_title"] = window_title

        result = await self._execute_worker_task(task)
        return {
            "tool_name": "bring_window_to_front",
            "tool_args": {"window_title": window_title},
            "result": result.get(
                "output",
                result.get("message", f"Brought window to front: {window_title}"),
            ),
            "status": result.get("status", "success"),
        }

    # User Interaction Tools

    async def ask_user_for_manual(
        self, program_name: str, question_text: str
    ) -> Dict[str, Any]:
        """Ask user for manual information."""
        task = self._create_base_task("ask_user_for_manual")
        task["program_name"] = program_name
        task["question_text"] = question_text

        result = await self._execute_worker_task(task)
        return {
            "tool_name": "ask_user_for_manual",
            "tool_args": {
                "program_name": program_name,
                "question_text": question_text,
            },
            "result": result.get(
                "output", result.get("message", "User manual request sent")
            ),
            "status": result.get("status", "success"),
        }

    async def respond_conversationally(self, response_text: str) -> Dict[str, Any]:
        """Respond conversationally to the user."""
        task = self._create_base_task("respond_conversationally")
        task["response_text"] = response_text

        result = await self._execute_worker_task(task)
        return {
            "tool_name": "respond_conversationally",
            "tool_args": {"response_text": response_text},
            "result": result.get("output", result.get("message", response_text)),
            "status": result.get("status", "success"),
            "response_text": response_text,
        }

    # Tool Name Mapping for Compatibility (Issue #315 - Dispatch Table Pattern)

    def _get_tool_handler(self, tool_name: str):
        """Get tool handler function for normalized tool name (Issue #315)."""
        # Check system tool variants first (O(1) lookup)
        if tool_name in EXECUTE_COMMAND_VARIANTS:
            return lambda args: self.execute_system_command(args.get("command", ""))
        if tool_name in QUERY_SYSTEM_INFO_VARIANTS:
            return lambda args: self.query_system_information()
        if tool_name in LIST_SERVICES_VARIANTS:
            return lambda args: self.list_system_services()
        if tool_name in MANAGE_SERVICE_VARIANTS:
            return lambda args: self.manage_service(
                args.get("service_name", ""), args.get("action", "")
            )
        if tool_name in GET_PROCESS_INFO_VARIANTS:
            return lambda args: self.get_process_info(
                args.get("process_name"), args.get("pid")
            )
        if tool_name in TERMINATE_PROCESS_VARIANTS:
            return lambda args: self.terminate_process(args.get("pid", ""))

        # Single-name tools dispatch table
        dispatch = {
            "webfetch": lambda args: self.web_fetch(args.get("url", "")),
            "searchknowledgebase": lambda args: self.search_knowledge_base(
                args.get("query", ""), args.get("n_results", 5)
            ),
            "addfiletoknowledgebase": lambda args: self.add_file_to_knowledge_base(
                args.get("file_path", ""),
                args.get("file_type", ""),
                args.get("metadata"),
            ),
            "storefact": lambda args: self.store_fact(
                args.get("content", ""), args.get("metadata")
            ),
            "getfact": lambda args: self.get_fact(
                args.get("fact_id"), args.get("query")
            ),
            "typetext": lambda args: self.type_text(args.get("text", "")),
            "clickelement": lambda args: self.click_element(args.get("image_path", "")),
            "bringwindowtofront": lambda args: self.bring_window_to_front(
                args.get("window_title", "")
            ),
            "askuserformanual": lambda args: self.ask_user_for_manual(
                args.get("program_name", ""), args.get("question_text", "")
            ),
            "respondconversationally": lambda args: self.respond_conversationally(
                args.get("response_text", "")
            ),
        }
        return dispatch.get(tool_name)

    async def execute_tool(
        self, tool_name: str, tool_args: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Execute a tool by name with arguments. This method provides a unified
        interface for both orchestrators to call tools using string names and
        arguments.
        """
        # Normalize tool name variations
        normalized_name = tool_name.lower().replace("_", "").replace("-", "")

        # Get handler from dispatch table (Issue #315 - depth 16 -> 1)
        handler = self._get_tool_handler(normalized_name)

        if handler:
            return await handler(tool_args)

        # Fallback for unknown tools
        return {
            "tool_name": tool_name,
            "tool_args": tool_args,
            "result": f"Unknown tool: {tool_name}",
            "status": "error",
        }

    def get_available_tools(self) -> List[str]:
        """Get list of available tool names."""
        return [
            "execute_system_command",
            "query_system_information",
            "list_system_services",
            "manage_service",
            "get_process_info",
            "terminate_process",
            "web_fetch",
            "search_knowledge_base",
            "add_file_to_knowledge_base",
            "store_fact",
            "get_fact",
            "type_text",
            "click_element",
            "bring_window_to_front",
            "ask_user_for_manual",
            "respond_conversationally",
        ]
