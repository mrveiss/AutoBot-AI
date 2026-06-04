# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
from __future__ import annotations

"""
Unified Tool Registry

This module provides a centralized implementation of all tools used by both
the standard orchestrator and LangChain orchestrator, eliminating code
duplication.
"""

import asyncio
import time
import uuid
from typing import TYPE_CHECKING, Any, Dict, List

from tools.code_interpreter import execute_code

if TYPE_CHECKING:
    from knowledge_base import KnowledgeBase
    from worker_node import WorkerNode
from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)

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
        worker_node: "WorkerNode" | None = None,
        knowledge_base: "KnowledgeBase" | None = None,
    ):
        """
        Initialize the tool registry with required dependencies.

        Args:
            worker_node: Worker node for task execution
            knowledge_base: Knowledge base for information retrieval
        """
        self.worker_node = worker_node
        self.knowledge_base = knowledge_base
        self.logger = get_logger(__name__)

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
            self.logger.error("Error executing task %s: %s", task.get("task_id"), e)
            return {"status": "error", "message": "Task execution failed"}

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
            "result": result.get("output", result.get("message", "System info retrieved")),
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

    async def get_process_info(self, process_name: str | None = None, pid: str | None = None) -> Dict[str, Any]:
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
            "result": result.get("output", result.get("message", "Process info retrieved")),
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
            "result": result.get("output", result.get("message", f"Process {pid} terminated")),
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
            "result": result.get("output", result.get("message", "Web content fetched")),
            "status": result.get("status", "success"),
        }

    # Issue #7509: Web research tools — direct internal dispatch via web_fetch package.

    async def scrape_url(self, url: str, render: str = "auto") -> Dict[str, Any]:
        """Fetch a URL and return its markdown content."""
        from web_fetch import RenderMode, WebFetcher

        try:
            fetch_result = await WebFetcher.fetch(url, render=RenderMode(render))
            if not fetch_result.success:
                return {
                    "tool_name": "scrape_url",
                    "tool_args": {"url": url},
                    "result": f"Fetch failed: {fetch_result.error_code}",
                    "status": "error",
                }
            title = f"# {fetch_result.title}\n\n" if fetch_result.title else ""
            header = f"## Scraped: {url} (status {fetch_result.status_code}, source: {fetch_result.source})\n\n"
            return {
                "tool_name": "scrape_url",
                "tool_args": {"url": url},
                "result": header + title + (fetch_result.markdown or "*(no content)*"),
                "status": "success",
            }
        except Exception as exc:
            self.logger.error("scrape_url failed for %s: %s", url, exc)
            return {"tool_name": "scrape_url", "tool_args": {"url": url}, "result": f"Error: {exc}", "status": "error"}

    async def crawl_site(
        self,
        seed_urls: List[str],
        max_depth: int = 1,
        max_pages: int = 100,
        respect_robots: bool = True,
        ingest: bool = False,
        same_origin: bool = True,
    ) -> Dict[str, Any]:
        """BFS crawl seed URLs and return a markdown index of fetched pages."""
        from chat_workflow.tool_handler import _format_crawl_results
        from knowledge.connectors.models import ConnectorConfig
        from knowledge.connectors.web_crawler import WebCrawlerConnector

        try:
            cfg = ConnectorConfig(
                connector_id="registry_crawl",
                connector_type="web_crawler",
                name="registry_crawl",
                config={"urls": seed_urls},
            )
            connector = WebCrawlerConnector(cfg)
            results = await connector.crawl(
                seed_urls=seed_urls,
                max_depth=max_depth,
                max_pages=max_pages,
                respect_robots=respect_robots,
                ingest=ingest,
                same_origin=same_origin,
            )
            return {
                "tool_name": "crawl_site",
                "tool_args": {"seed_urls": seed_urls},
                "result": _format_crawl_results(seed_urls, results),
                "status": "success",
            }
        except Exception as exc:
            self.logger.error("crawl_site failed: %s", exc)
            return {
                "tool_name": "crawl_site",
                "tool_args": {"seed_urls": seed_urls},
                "result": f"Error: {exc}",
                "status": "error",
            }

    async def map_site(self, domain: str, max_urls: int = 500, respect_robots: bool = True) -> Dict[str, Any]:
        """Discover URLs for a domain via sitemap.xml or BFS crawl fallback."""
        from chat_workflow.tool_handler import _format_map_results
        from web_fetch.site_mapper import SiteMapper

        try:
            site_result = await SiteMapper.map_site(domain, max_urls=max_urls, respect_robots=respect_robots)
            return {
                "tool_name": "map_site",
                "tool_args": {"domain": domain},
                "result": _format_map_results(site_result),
                "status": "success",
            }
        except Exception as exc:
            self.logger.error("map_site failed for %s: %s", domain, exc)
            return {
                "tool_name": "map_site",
                "tool_args": {"domain": domain},
                "result": f"Error: {exc}",
                "status": "error",
            }

    async def extract_structured_data(self, url: str, schema: Dict[str, Any], render: str = "auto") -> Dict[str, Any]:
        """Extract structured data from a URL using a JSON Schema and LLM."""
        import json

        from web_fetch.extractors import extract_url

        try:
            result = await extract_url(url=url, schema=schema, render=render)
            json_str = json.dumps(result["data"], indent=2, ensure_ascii=False)
            return {
                "tool_name": "extract_structured_data",
                "tool_args": {"url": url},
                "result": f"## Extracted data from {url}\n\n```json\n{json_str}\n```",
                "status": "success",
            }
        except Exception as exc:
            self.logger.error("extract_structured_data failed for %s: %s", url, exc)
            return {
                "tool_name": "extract_structured_data",
                "tool_args": {"url": url},
                "result": f"Error: {exc}",
                "status": "error",
            }

    # Knowledge Base Tools

    async def search_knowledge_base(self, query: str, n_results: int = 5) -> Dict[str, Any]:
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
                        result["content"][:200] + "..." if len(result["content"]) > 200 else result["content"]
                    )
                    metadata = result.get("metadata", {})
                    filename = metadata.get("filename", "N/A")
                    chunk_index = metadata.get("chunk_index", "N/A")
                    formatted_results.append(f"[{filename} - Chunk {chunk_index}]: " f"{content_preview}")

                result_text = f"Found {len(results)} relevant results:\n" + "\n".join(formatted_results)
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
        self, file_path: str, file_type: str, metadata: Dict[str, Any] | None = None
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
            result = await self.knowledge_base.add_file(file_path, file_type, metadata or {})
            return {
                "tool_name": "add_file_to_knowledge_base",
                "tool_args": {
                    "file_path": file_path,
                    "file_type": file_type,
                    "metadata": metadata,
                },
                "result": result.get("message", f"File {file_path} added to knowledge base"),
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

    async def store_fact(self, content: str, metadata: Dict[str, Any] | None = None) -> Dict[str, Any]:
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

    async def get_fact(self, fact_id: int | None = None, query: str | None = None) -> Dict[str, Any]:
        """Get facts from the knowledge base."""
        if not self.knowledge_base:
            return {
                "tool_name": "get_fact",
                "tool_args": {"fact_id": fact_id, "query": query},
                "result": "Knowledge base is not available",
                "status": "error",
            }

        try:
            # Issue #788: get_fact() only accepts fact_id, use search() for queries
            if fact_id is not None:
                result = self.knowledge_base.get_fact(str(fact_id))
                results = [result] if result else []
            elif query:
                results = await self.knowledge_base.search(query, top_k=5)
            else:
                results = []

            if results:
                formatted_results = []
                for result in results:
                    rid = result.get("id", "N/A")
                    content = result.get("content", "No content")
                    formatted_results.append(f"Fact {rid}: {content}")

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
            "result": result.get("output", result.get("message", f"Typed text: {text}")),
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

    async def ask_user_for_manual(self, program_name: str, question_text: str) -> Dict[str, Any]:
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
            "result": result.get("output", result.get("message", "User manual request sent")),
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

    async def execute_code_tool(self, code: str, timeout_seconds: int = 30) -> Dict[str, Any]:
        """Execute Python code in a sandboxed subprocess and return stdout/stderr."""
        result = execute_code(code, timeout_seconds=timeout_seconds)
        return {
            "tool_name": "code_interpreter",
            "tool_args": {"code": code, "timeout_seconds": timeout_seconds},
            "result": result,
            "status": "success" if result["exit_code"] == 0 else "error",
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
            return lambda args: self.manage_service(args.get("service_name", ""), args.get("action", ""))
        if tool_name in GET_PROCESS_INFO_VARIANTS:
            return lambda args: self.get_process_info(args.get("process_name"), args.get("pid"))
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
            "storefact": lambda args: self.store_fact(args.get("content", ""), args.get("metadata")),
            "getfact": lambda args: self.get_fact(args.get("fact_id"), args.get("query")),
            "typetext": lambda args: self.type_text(args.get("text", "")),
            "clickelement": lambda args: self.click_element(args.get("image_path", "")),
            "bringwindowtofront": lambda args: self.bring_window_to_front(args.get("window_title", "")),
            "askuserformanual": lambda args: self.ask_user_for_manual(
                args.get("program_name", ""), args.get("question_text", "")
            ),
            "respondconversationally": lambda args: self.respond_conversationally(args.get("response_text", "")),
            "codeinterpreter": lambda args: self.execute_code_tool(
                args.get("code", ""), args.get("timeout_seconds", 30)
            ),
            # Issue #7509: Web research tools
            "scrapeurl": lambda args: self.scrape_url(args.get("url", ""), args.get("render", "auto")),
            "crawlsite": lambda args: self.crawl_site(
                args.get("seed_urls", []),
                args.get("max_depth", 1),
                args.get("max_pages", 100),
                args.get("respect_robots", True),
                args.get("ingest", False),
                args.get("same_origin", True),
            ),
            "mapsite": lambda args: self.map_site(
                args.get("domain", ""),
                args.get("max_urls", 500),
                args.get("respect_robots", True),
            ),
            "extractstructureddata": lambda args: self.extract_structured_data(
                args.get("url", ""),
                args.get("schema", {}),
                args.get("render", "auto"),
            ),
        }
        return dispatch.get(tool_name)

    async def _try_sdk_dispatch(self, tool_name: str, tool_args: Dict[str, Any]) -> Dict[str, Any] | None:
        """Attempt to dispatch via ToolSDKRegistry.

        Returns None if the tool is not registered in the SDK registry so the
        caller can fall through to the legacy dispatch table.

        Args:
            tool_name: Raw tool name (not normalised).
            tool_args: Argument dict to pass to the tool.

        Returns:
            Serialisable result dict on success/failure, or None if the tool
            is not in the SDK registry.
        """
        try:
            from tool_sdk.registry import ToolNotFoundError  # noqa: PLC0415
            from tool_sdk.registry import get_tool_registry as _get_sdk_registry  # noqa: PLC0415

            registry = _get_sdk_registry()
            # Probe registry without instantiating — raises ToolNotFoundError if absent
            try:
                registry.get(tool_name)
            except ToolNotFoundError:
                return None

            # Tool is registered; execute via the registry (handles validation + timing)
            from tool_sdk.base import ToolPermission

            result = await registry.execute(
                tool_name,
                tool_args,
                caller_permission=ToolPermission.SYSTEM,
            )
            return {
                "tool_name": tool_name,
                "tool_args": tool_args,
                "result": result.data if result.success else result.error,
                "status": "success" if result.success else "error",
            }
        except Exception as exc:
            self.logger.error("SDK tool dispatch failed for '%s': %s", tool_name, exc, exc_info=True)
            return None

    async def execute_tool(self, tool_name: str, tool_args: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a tool by name with arguments.

        Checks ToolSDKRegistry first for schema-validated tools registered via
        the Tool SDK (#3009), then falls back to the legacy dispatch table.
        This method provides a unified interface for both orchestrators to call
        tools using string names and arguments.
        """
        # Try SDK-registered tools first (#3009)
        sdk_result = await self._try_sdk_dispatch(tool_name, tool_args)
        if sdk_result is not None:
            return sdk_result

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

    def _tool_description(self, name: str) -> str:
        """Return the raw (uncompressed) description for a single tool. Issue #5871."""
        import inspect  # noqa: PLC0415

        method = getattr(self, name, None)
        if method is not None:
            doc = inspect.getdoc(method)
            if doc:
                return doc.split("\n")[0]
        try:
            from chat_workflow.tool_handler import _BUILTIN_TOOL_SCHEMAS  # noqa: PLC0415

            schema = _BUILTIN_TOOL_SCHEMAS.get(name, {})
            desc = (schema or {}).get("description", "")
            if desc:
                return desc
        except ImportError:
            pass
        return name

    def get_raw_descriptions(self) -> Dict[str, str]:
        """Return uncompressed descriptions for all registered tools. Issue #5871."""
        return {name: self._tool_description(name) for name in self.get_available_tools()}

    async def get_compressed_descriptions(self) -> Dict[str, str]:
        """Return a mapping of tool_name -> compressed description for all registered tools.

        Uses :func:`tools.description_compressor.compress_description` with Redis
        caching and Ollama LLM compression.  Falls back to the tool name string for
        any tool whose description cannot be resolved.
        """
        from tools.description_compressor import compress_description  # noqa: PLC0415

        tool_names = self.get_available_tools()
        tasks = [compress_description(name, {"description": self._tool_description(name)}) for name in tool_names]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        compressed: Dict[str, str] = {}
        for name, result in zip(tool_names, results):
            if isinstance(result, Exception):
                logger.warning("compress_description failed for tool '%s': %s", name, result)
                compressed[name] = self._tool_description(name)
            else:
                compressed[name] = result
        return compressed

    def get_available_tools(self) -> List[str]:
        """Get list of available tool names.

        Browser tool names are derived from BROWSER_TOOL_NAMES in
        chat_workflow.tool_handler (Issue #2609) so both layers share a single
        source of truth. Issue #2594: also includes web_search (Issue #2306).
        """
        # Registry-owned tools (system, knowledge-base, GUI, conversation)
        registry_tools = [
            "execute_system_command",
            "query_system_information",
            "list_system_services",
            "manage_service",
            "get_process_info",
            "terminate_process",
            "web_fetch",
            "web_search",
            "search_knowledge_base",
            "add_file_to_knowledge_base",
            "store_fact",
            "get_fact",
            "type_text",
            "click_element",
            "bring_window_to_front",
            "ask_user_for_manual",
            "respond_conversationally",
            "code_interpreter",
            # Issue #7509: Web research tools
            "scrape_url",
            "crawl_site",
            "map_site",
            "extract_structured_data",
        ]
        # Issue #1368/#2609: Browser tools are defined once in BROWSER_TOOL_NAMES
        # and imported here so the two lists cannot drift independently.
        # Lazy import breaks the circular dependency:
        #   chat_workflow -> tool_handler -> tools -> tool_registry -> chat_workflow
        # (#4557)
        from chat_workflow.tool_handler import BROWSER_TOOL_NAMES  # noqa: PLC0415

        return registry_tools + sorted(BROWSER_TOOL_NAMES)


from autobot_shared.singleton_factory import lazy_singleton  # noqa: E402

get_tool_registry = lazy_singleton(ToolRegistry)
