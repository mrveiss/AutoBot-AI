# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
import asyncio
import logging
from typing import Any, Dict, List, Optional

from langchain.agents import Tool, initialize_agent
from langchain.agents.agent_types import AgentType

try:
    from langchain_community.llms import Ollama  # type: ignore
except ImportError:
    try:
        from langchain.llms import Ollama
    except ImportError:
        try:
            from langchain_community.llms.ollama import Ollama  # type: ignore
        except ImportError:
            # Fallback - will cause runtime error if used
            Ollama = None
            logging.warning(
                "Ollama integration not available. Install 'langchain-community' "
                "package for Ollama support."
            )

from backend.constants.model_constants import ModelConstants
from event_manager import event_manager
from knowledge_base import KnowledgeBase
from tools import ToolRegistry
from backend.utils.service_registry import get_service_url
from worker_node import WorkerNode


class LangChainAgentOrchestrator:
    """Orchestrator for LangChain-based agents with AutoBot integration."""

    def __init__(
        self,
        config: Dict[str, Any],
        worker_node: Optional[WorkerNode],
        knowledge_base: Optional[KnowledgeBase],
    ):
        """Initialize orchestrator with config, worker node, and knowledge base."""
        self.config = config
        self.worker_node = worker_node
        self.knowledge_base = knowledge_base
        self.available = worker_node is not None

        if not self._validate_prerequisites():
            return

        if not self._initialize_llm():
            return

        self._initialize_components()
        logging.info("LangChain Agent Orchestrator initialized")

    def _validate_prerequisites(self) -> bool:
        """Validate prerequisites for orchestrator initialization."""
        if not self.available:
            logging.warning(
                "LangChain Agent Orchestrator disabled due to missing worker node"
            )
            return False

        if Ollama is None:
            logging.warning(
                "LangChain Agent Orchestrator disabled due to missing Ollama import"
            )
            self.available = False
            return False

        return True

    def _get_llm_config(self) -> tuple:
        """Get LLM model and base URL from config."""
        from config import config as global_config

        llm_config = global_config.get_llm_config()
        llm_model = ModelConstants.DEFAULT_OLLAMA_MODEL
        llm_base_url = llm_config.get("ollama", {}).get(
            "base_url", get_service_url("ollama")
        )
        return llm_model, llm_base_url

    def _initialize_llm(self) -> bool:
        """Initialize the LLM for LangChain."""
        llm_model, llm_base_url = self._get_llm_config()
        logging.info(
            f"LangChain Agent initializing with model: {llm_model}, base_url: {llm_base_url}"
        )

        try:
            logging.debug(
                f"Passing model='{llm_model}' and base_url='{llm_base_url}' to Ollama constructor."
            )
            self.llm = Ollama(model=llm_model, base_url=llm_base_url, temperature=0.7)
            logging.info(
                f"LangChain Agent LLM initialized successfully with model: {llm_model}"
            )
            return True
        except Exception as e:
            logging.error(f"Failed to initialize LangChain Agent: {e}", exc_info=True)
            self.available = False
            return False

    def _initialize_components(self) -> None:
        """Initialize tool registry, tools, and agent."""
        self.tool_registry = ToolRegistry(
            worker_node=self.worker_node, knowledge_base=self.knowledge_base
        )
        self.tools = self._create_tools()
        self.agent = initialize_agent(
            tools=self.tools,
            llm=self.llm,
            agent=AgentType.ZERO_SHOT_REACT_DESCRIPTION,
            verbose=True,
            max_iterations=10,
            handle_parsing_errors=True,
        )

    def _create_system_tools(self) -> List[Tool]:
        """Create system integration tools."""
        return [
            Tool(
                name="execute_system_command",
                description=(
                    "Execute a system command. Use this for running shell commands, "
                    "checking system status, or performing system operations. "
                    "Input should be the command to execute."
                ),
                func=self._execute_system_command,
            ),
            Tool(
                name="query_system_information",
                description=(
                    "Get system information including OS details, hardware specs, "
                    "and system status. No input required."
                ),
                func=self._query_system_information,
            ),
            Tool(
                name="list_system_services",
                description="List all system services and their status. No input required.",
                func=self._list_system_services,
            ),
            Tool(
                name="manage_service",
                description=(
                    "Manage a system service (start, stop, restart, enable, disable). "
                    "Input should be 'service_name action' where action is one of: "
                    "start, stop, restart, enable, disable."
                ),
                func=self._manage_service,
            ),
            Tool(
                name="get_process_info",
                description="Get information about running processes. Input can be a process name or PID.",
                func=self._get_process_info,
            ),
            Tool(
                name="terminate_process",
                description="Terminate a process by PID. Input should be the process ID (PID).",
                func=self._terminate_process,
            ),
            Tool(
                name="web_fetch",
                description="Fetch content from a web URL. Input should be the URL to fetch.",
                func=self._web_fetch,
            ),
        ]

    def _create_knowledge_tools(self) -> List[Tool]:
        """Create knowledge base tools."""
        return [
            Tool(
                name="search_knowledge_base",
                description="Search the knowledge base for relevant information. Input should be the search query.",
                func=self._search_knowledge_base,
            ),
            Tool(
                name="add_file_to_knowledge_base",
                description=(
                    "Add a file to the knowledge base. Input should be "
                    "'file_path file_type' where file_type is one of: txt, pdf, csv, docx."
                ),
                func=self._add_file_to_knowledge_base,
            ),
            Tool(
                name="store_fact",
                description="Store a fact in the knowledge base. Input should be the fact content to store.",
                func=self._store_fact,
            ),
            Tool(
                name="get_fact",
                description="Get facts from the knowledge base. Input can be a fact ID or search query.",
                func=self._get_fact,
            ),
        ]

    def _create_gui_tools(self) -> List[Tool]:
        """Create GUI automation tools if available."""
        if not (
            self.worker_node
            and hasattr(self.worker_node, "gui_controller")
            and self.worker_node.gui_controller
        ):
            return []

        return [
            Tool(
                name="type_text",
                description="Type text into the currently active window. Input should be the text to type.",
                func=self._type_text,
            ),
            Tool(
                name="click_element",
                description="Click on a GUI element by image path. Input should be the path to the image template.",
                func=self._click_element,
            ),
            Tool(
                name="bring_window_to_front",
                description="Bring a window to the front by application title. Input should be the window title.",
                func=self._bring_window_to_front,
            ),
        ]

    def _create_user_interaction_tools(self) -> List[Tool]:
        """Create user interaction tools."""
        return [
            Tool(
                name="ask_user_for_manual",
                description=(
                    "Ask the user for a manual or help information about "
                    "a specific program. Input should be 'program_name question_text'."
                ),
                func=self._ask_user_for_manual,
            ),
            Tool(
                name="respond_conversationally",
                description=(
                    "Respond to the user conversationally when no other tools are "
                    "needed. Input should be the response text."
                ),
                func=self._respond_conversationally,
            ),
        ]

    def _create_tools(self) -> List[Tool]:
        """Create LangChain Tools that wrap existing AutoBot functionality."""
        tools = []
        tools.extend(self._create_system_tools())
        tools.extend(self._create_knowledge_tools())
        tools.extend(self._create_gui_tools())
        tools.extend(self._create_user_interaction_tools())
        return tools

    # All tool methods now use the unified ToolRegistry to eliminate code duplication

    def _execute_system_command(self, command: str) -> str:
        """Execute a system command using unified tool registry."""
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            result = loop.run_until_complete(
                self.tool_registry.execute_system_command(command)
            )
            loop.close()
            return result.get("result", "Command executed")
        except Exception as e:
            return f"Error: {e}"

    def _query_system_information(self, input_text: str = "") -> str:
        """Query system information using unified tool registry."""
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            result = loop.run_until_complete(
                self.tool_registry.query_system_information()
            )
            loop.close()
            return result.get("result", "System info retrieved")
        except Exception as e:
            return f"Error: {e}"

    def _list_system_services(self, input_text: str = "") -> str:
        """List system services using unified tool registry."""
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            result = loop.run_until_complete(self.tool_registry.list_system_services())
            loop.close()
            return result.get("result", "Services listed")
        except Exception as e:
            return f"Error: {e}"

    def _manage_service(self, service_action: str) -> str:
        """Manage a system service using unified tool registry."""
        try:
            parts = service_action.split()
            if len(parts) < 2:
                return "Invalid input. Expected 'service_name action'"

            service_name = parts[0]
            action = parts[1]

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            result = loop.run_until_complete(
                self.tool_registry.manage_service(service_name, action)
            )
            loop.close()
            return result.get("result", "Service managed")
        except Exception as e:
            return f"Error: {e}"

    def _get_process_info(self, process_input: str) -> str:
        """Get process information using unified tool registry."""
        try:
            process_name = process_input if not process_input.isdigit() else None
            pid = process_input if process_input.isdigit() else None

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            result = loop.run_until_complete(
                self.tool_registry.get_process_info(process_name, pid)
            )
            loop.close()
            return result.get("result", "Process info retrieved")
        except Exception as e:
            return f"Error: {e}"

    def _terminate_process(self, pid: str) -> str:
        """Terminate a process using unified tool registry."""
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            result = loop.run_until_complete(self.tool_registry.terminate_process(pid))
            loop.close()
            return result.get("result", "Process terminated")
        except Exception as e:
            return f"Error: {e}"

    def _web_fetch(self, url: str) -> str:
        """Fetch web content using unified tool registry."""
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            result = loop.run_until_complete(self.tool_registry.web_fetch(url))
            loop.close()
            return result.get("result", "Web content fetched")
        except Exception as e:
            return f"Error: {e}"

    def _search_knowledge_base(self, query: str) -> str:
        """Search knowledge base using unified tool registry."""
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            result = loop.run_until_complete(
                self.tool_registry.search_knowledge_base(query, n_results=5)
            )
            loop.close()
            return result.get("result", "Knowledge base searched")
        except Exception as e:
            return f"Error: {e}"

    def _add_file_to_knowledge_base(self, file_info: str) -> str:
        """Add file to knowledge base using unified tool registry."""
        try:
            parts = file_info.split()
            if len(parts) < 2:
                return "Invalid input. Expected 'file_path file_type'"

            file_path = parts[0]
            file_type = parts[1]

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            result = loop.run_until_complete(
                self.tool_registry.add_file_to_knowledge_base(file_path, file_type)
            )
            loop.close()
            return result.get("result", "File added to knowledge base")
        except Exception as e:
            return f"Error: {e}"

    def _store_fact(self, fact_content: str) -> str:
        """Store fact using unified tool registry."""
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            result = loop.run_until_complete(
                self.tool_registry.store_fact(fact_content)
            )
            loop.close()
            return result.get("result", "Fact stored")
        except Exception as e:
            return f"Error: {e}"

    def _get_fact(self, fact_query: str) -> str:
        """Get facts using unified tool registry."""
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            if fact_query.isdigit():
                result = loop.run_until_complete(
                    self.tool_registry.get_fact(fact_id=int(fact_query))
                )
            else:
                result = loop.run_until_complete(
                    self.tool_registry.get_fact(query=fact_query)
                )

            loop.close()
            return result.get("result", "Facts retrieved")
        except Exception as e:
            return f"Error: {e}"

    def _type_text(self, text: str) -> str:
        """Type text using unified tool registry."""
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            result = loop.run_until_complete(self.tool_registry.type_text(text))
            loop.close()
            return result.get("result", "Text typed")
        except Exception as e:
            return f"Error: {e}"

    def _click_element(self, image_path: str) -> str:
        """Click element using unified tool registry."""
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            result = loop.run_until_complete(
                self.tool_registry.click_element(image_path)
            )
            loop.close()
            return result.get("result", "Element clicked")
        except Exception as e:
            return f"Error: {e}"

    def _bring_window_to_front(self, window_title: str) -> str:
        """Bring window to front using unified tool registry."""
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            result = loop.run_until_complete(
                self.tool_registry.bring_window_to_front(window_title)
            )
            loop.close()
            return result.get("result", "Window brought to front")
        except Exception as e:
            return f"Error: {e}"

    def _ask_user_for_manual(self, program_question: str) -> str:
        """Ask user for manual using unified tool registry."""
        try:
            parts = program_question.split(" ", 1)
            if len(parts) < 2:
                return "Invalid input. Expected 'program_name question_text'"

            program_name = parts[0]
            question_text = parts[1]

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            result = loop.run_until_complete(
                self.tool_registry.ask_user_for_manual(program_name, question_text)
            )
            loop.close()
            return result.get("result", "User manual request sent")
        except Exception as e:
            return f"Error: {e}"

    def _respond_conversationally(self, response_text: str) -> str:
        """Respond conversationally using unified tool registry."""
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            result = loop.run_until_complete(
                self.tool_registry.respond_conversationally(response_text)
            )
            loop.close()
            return result.get("result", response_text)
        except Exception as e:
            return f"Error: {e}"

    def _build_conversation_context(
        self, conversation_history: Optional[List[Dict[str, str]]]
    ) -> str:
        """Build context string from conversation history. Issue #620."""
        if not conversation_history:
            return ""
        context = "\n".join(
            [f"{msg['role']}: {msg['content']}" for msg in conversation_history[-5:]]
        )
        return f"Recent conversation:\n{context}\n\n"

    async def _build_knowledge_base_context(self, goal: str) -> str:
        """Fetch and format knowledge base context for a goal. Issue #620."""
        if not self.knowledge_base:
            return ""
        try:
            kb_results = await self.knowledge_base.search(goal, n_results=3)
            if kb_results:
                kb_context = "\n".join(
                    [f"KB: {result['content'][:200]}..." for result in kb_results]
                )
                return f"Relevant knowledge:\n{kb_context}\n\n"
        except Exception as e:
            logging.warning(f"Failed to search knowledge base: {e}")
        return ""

    async def execute_goal(
        self, goal: str, conversation_history: Optional[List[Dict[str, str]]] = None
    ) -> Dict[str, Any]:
        """Execute a goal using the LangChain agent."""
        try:
            await event_manager.publish(
                "log_message",
                {"level": "INFO", "message": f"LangChain Agent executing goal: {goal}"},
            )

            # Build context from conversation history and knowledge base
            context = self._build_conversation_context(conversation_history)
            context += await self._build_knowledge_base_context(goal)

            # Execute the goal using LangChain agent
            full_goal = f"{context}Current goal: {goal}"
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(None, self.agent.run, full_goal)

            await event_manager.publish(
                "log_message",
                {"level": "INFO", "message": f"LangChain Agent result: {result}"},
            )

            return {
                "status": "success",
                "tool_name": "respond_conversationally",
                "tool_args": {"response_text": result},
            }

        except Exception as e:
            error_msg = f"LangChain Agent error: {str(e)}"
            await event_manager.publish("error", {"message": error_msg})
            logging.error(error_msg)

            return {
                "status": "error",
                "tool_name": "respond_conversationally",
                "tool_args": {"response_text": error_msg},
            }

    def get_available_tools(self) -> List[str]:
        """Get list of available tool names."""
        return [tool.name for tool in self.tools]
