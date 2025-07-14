import asyncio
import json
import logging
from typing import Dict, Any, List, Optional, Callable
import uuid
import time

from langchain.agents import initialize_agent, Tool
from langchain.agents.agent_types import AgentType
from langchain.schema import BaseMessage, HumanMessage, AIMessage, SystemMessage

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
            logging.warning("Ollama integration not available. Install 'langchain-community' package for Ollama support.")

from src.worker_node import WorkerNode
from src.knowledge_base import KnowledgeBase
from src.event_manager import event_manager


class LangChainAgentOrchestrator:
    def __init__(self, config: Dict[str, Any], worker_node: Optional[WorkerNode], knowledge_base: KnowledgeBase):
        self.config = config
        self.worker_node = worker_node
        self.knowledge_base = knowledge_base
        self.available = worker_node is not None
        
        if not self.available:
            logging.warning("LangChain Agent Orchestrator disabled due to missing worker node")
            return
        
        if Ollama is None:
            logging.warning("LangChain Agent Orchestrator disabled due to missing Ollama import")
            self.available = False
            return
        
        # Initialize LLM for LangChain
        llm_config = config.get('llm_interface', {})
        llm_model = llm_config.get('orchestrator_llm', 'phi')
        llm_base_url = llm_config.get('ollama', {}).get('base_url', 'http://localhost:11434')
        
        try:
            self.llm = Ollama(
                model=llm_model,
                base_url=llm_base_url,
                temperature=0.7
            )
        except Exception as e:
            logging.warning(f"Failed to initialize Ollama LLM: {e}")
            self.available = False
            return
        
        # Initialize tools
        self.tools = self._create_tools()
        
        # Initialize agent
        self.agent = initialize_agent(
            tools=self.tools,
            llm=self.llm,
            agent=AgentType.ZERO_SHOT_REACT_DESCRIPTION,
            verbose=True,
            max_iterations=10,
            handle_parsing_errors=True
        )
        
        logging.info("LangChain Agent Orchestrator initialized")

    def _create_tools(self) -> List[Tool]:
        """Create LangChain Tools that wrap existing AutoBot functionality."""
        tools = []
        
        # System Integration Tools
        tools.append(Tool(
            name="execute_system_command",
            description="Execute a system command. Use this for running shell commands, checking system status, or performing system operations. Input should be the command to execute.",
            func=self._execute_system_command
        ))
        
        tools.append(Tool(
            name="query_system_information",
            description="Get system information including OS details, hardware specs, and system status. No input required.",
            func=self._query_system_information
        ))
        
        tools.append(Tool(
            name="list_system_services",
            description="List all system services and their status. No input required.",
            func=self._list_system_services
        ))
        
        tools.append(Tool(
            name="manage_service",
            description="Manage a system service (start, stop, restart, enable, disable). Input should be 'service_name action' where action is one of: start, stop, restart, enable, disable.",
            func=self._manage_service
        ))
        
        tools.append(Tool(
            name="get_process_info",
            description="Get information about running processes. Input can be a process name or PID.",
            func=self._get_process_info
        ))
        
        tools.append(Tool(
            name="terminate_process",
            description="Terminate a process by PID. Input should be the process ID (PID).",
            func=self._terminate_process
        ))
        
        tools.append(Tool(
            name="web_fetch",
            description="Fetch content from a web URL. Input should be the URL to fetch.",
            func=self._web_fetch
        ))
        
        # Knowledge Base Tools
        tools.append(Tool(
            name="search_knowledge_base",
            description="Search the knowledge base for relevant information. Input should be the search query.",
            func=self._search_knowledge_base
        ))
        
        tools.append(Tool(
            name="add_file_to_knowledge_base",
            description="Add a file to the knowledge base. Input should be 'file_path file_type' where file_type is one of: txt, pdf, csv, docx.",
            func=self._add_file_to_knowledge_base
        ))
        
        tools.append(Tool(
            name="store_fact",
            description="Store a fact in the knowledge base. Input should be the fact content to store.",
            func=self._store_fact
        ))
        
        tools.append(Tool(
            name="get_fact",
            description="Get facts from the knowledge base. Input can be a fact ID or search query.",
            func=self._get_fact
        ))
        
        # GUI Automation Tools (if available)
        if self.worker_node and hasattr(self.worker_node, 'gui_controller') and self.worker_node.gui_controller:
            tools.append(Tool(
                name="type_text",
                description="Type text into the currently active window. Input should be the text to type.",
                func=self._type_text
            ))
            
            tools.append(Tool(
                name="click_element",
                description="Click on a GUI element by image path. Input should be the path to the image template.",
                func=self._click_element
            ))
            
            tools.append(Tool(
                name="bring_window_to_front",
                description="Bring a window to the front by application title. Input should be the window title.",
                func=self._bring_window_to_front
            ))
        
        # User Interaction Tools
        tools.append(Tool(
            name="ask_user_for_manual",
            description="Ask the user for a manual or help information about a specific program. Input should be 'program_name question_text'.",
            func=self._ask_user_for_manual
        ))
        
        tools.append(Tool(
            name="respond_conversationally",
            description="Respond to the user conversationally when no other tools are needed. Input should be the response text.",
            func=self._respond_conversationally
        ))
        
        return tools

    def _execute_task(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """Helper method to execute tasks via worker node."""
        if not self.worker_node:
            return {"status": "error", "message": "Worker node not available"}
        
        try:
            # Run async task in sync context
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            result = loop.run_until_complete(self.worker_node.execute_task(task))
            loop.close()
            return result
        except Exception as e:
            logging.error(f"Error executing task: {e}")
            return {"status": "error", "message": str(e)}

    def _execute_system_command(self, command: str) -> str:
        """Execute a system command."""
        task = {
            "task_id": str(uuid.uuid4()),
            "type": "system_execute_command",
            "command": command,
            "user_role": "user",
            "timestamp": time.time()
        }
        result = self._execute_task(task)
        return result.get("output", result.get("message", "Command execution failed"))

    def _query_system_information(self, input_text: str = "") -> str:
        """Query system information."""
        task = {
            "task_id": str(uuid.uuid4()),
            "type": "system_query_info",
            "user_role": "user",
            "timestamp": time.time()
        }
        result = self._execute_task(task)
        return result.get("output", result.get("message", "Failed to get system information"))

    def _list_system_services(self, input_text: str = "") -> str:
        """List system services."""
        task = {
            "task_id": str(uuid.uuid4()),
            "type": "system_list_services",
            "user_role": "user",
            "timestamp": time.time()
        }
        result = self._execute_task(task)
        return result.get("output", result.get("message", "Failed to list services"))

    def _manage_service(self, service_action: str) -> str:
        """Manage a system service."""
        try:
            parts = service_action.split()
            if len(parts) < 2:
                return "Invalid input. Expected 'service_name action'"
            
            service_name = parts[0]
            action = parts[1]
            
            task = {
                "task_id": str(uuid.uuid4()),
                "type": "system_manage_service",
                "service_name": service_name,
                "action": action,
                "user_role": "user",
                "timestamp": time.time()
            }
            result = self._execute_task(task)
            return result.get("output", result.get("message", "Failed to manage service"))
        except Exception as e:
            return f"Error managing service: {e}"

    def _get_process_info(self, process_input: str) -> str:
        """Get process information."""
        task = {
            "task_id": str(uuid.uuid4()),
            "type": "system_get_process_info",
            "process_name": process_input if not process_input.isdigit() else None,
            "pid": process_input if process_input.isdigit() else None,
            "user_role": "user",
            "timestamp": time.time()
        }
        result = self._execute_task(task)
        return result.get("output", result.get("message", "Failed to get process info"))

    def _terminate_process(self, pid: str) -> str:
        """Terminate a process by PID."""
        task = {
            "task_id": str(uuid.uuid4()),
            "type": "system_terminate_process",
            "pid": pid,
            "user_role": "user",
            "timestamp": time.time()
        }
        result = self._execute_task(task)
        return result.get("output", result.get("message", "Failed to terminate process"))

    def _web_fetch(self, url: str) -> str:
        """Fetch content from a web URL."""
        task = {
            "task_id": str(uuid.uuid4()),
            "type": "web_fetch",
            "url": url,
            "user_role": "user",
            "timestamp": time.time()
        }
        result = self._execute_task(task)
        return result.get("output", result.get("message", "Failed to fetch web content"))

    def _search_knowledge_base(self, query: str) -> str:
        """Search the knowledge base."""
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            results = loop.run_until_complete(self.knowledge_base.search(query, n_results=5))
            loop.close()
            
            if results:
                formatted_results = []
                for result in results:
                    formatted_results.append(f"Content: {result['content'][:200]}...")
                return "\n".join(formatted_results)
            else:
                return "No relevant information found in knowledge base"
        except Exception as e:
            return f"Error searching knowledge base: {e}"

    def _add_file_to_knowledge_base(self, file_info: str) -> str:
        """Add a file to the knowledge base."""
        try:
            parts = file_info.split()
            if len(parts) < 2:
                return "Invalid input. Expected 'file_path file_type'"
            
            file_path = parts[0]
            file_type = parts[1]
            
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            result = loop.run_until_complete(self.knowledge_base.add_file(file_path, file_type))
            loop.close()
            
            return result.get("message", "File added to knowledge base")
        except Exception as e:
            return f"Error adding file to knowledge base: {e}"

    def _store_fact(self, fact_content: str) -> str:
        """Store a fact in the knowledge base."""
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            result = loop.run_until_complete(self.knowledge_base.store_fact(fact_content))
            loop.close()
            
            return result.get("message", "Fact stored successfully")
        except Exception as e:
            return f"Error storing fact: {e}"

    def _get_fact(self, fact_query: str) -> str:
        """Get facts from the knowledge base."""
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            if fact_query.isdigit():
                results = loop.run_until_complete(self.knowledge_base.get_fact(fact_id=int(fact_query)))
            else:
                results = loop.run_until_complete(self.knowledge_base.get_fact(query=fact_query))
            
            loop.close()
            
            if results:
                formatted_results = []
                for result in results:
                    formatted_results.append(f"Fact {result['id']}: {result['content']}")
                return "\n".join(formatted_results)
            else:
                return "No facts found"
        except Exception as e:
            return f"Error getting facts: {e}"

    def _type_text(self, text: str) -> str:
        """Type text into the active window."""
        task = {
            "task_id": str(uuid.uuid4()),
            "type": "gui_type_text",
            "text": text,
            "user_role": "user",
            "timestamp": time.time()
        }
        result = self._execute_task(task)
        return result.get("output", result.get("message", "Failed to type text"))

    def _click_element(self, image_path: str) -> str:
        """Click on a GUI element by image."""
        task = {
            "task_id": str(uuid.uuid4()),
            "type": "gui_click_element",
            "image_path": image_path,
            "user_role": "user",
            "timestamp": time.time()
        }
        result = self._execute_task(task)
        return result.get("output", result.get("message", "Failed to click element"))

    def _bring_window_to_front(self, window_title: str) -> str:
        """Bring a window to the front."""
        task = {
            "task_id": str(uuid.uuid4()),
            "type": "gui_bring_window_to_front",
            "window_title": window_title,
            "user_role": "user",
            "timestamp": time.time()
        }
        result = self._execute_task(task)
        return result.get("output", result.get("message", "Failed to bring window to front"))

    def _ask_user_for_manual(self, program_question: str) -> str:
        """Ask user for manual information."""
        try:
            parts = program_question.split(' ', 1)
            if len(parts) < 2:
                return "Invalid input. Expected 'program_name question_text'"
            
            program_name = parts[0]
            question_text = parts[1]
            
            task = {
                "task_id": str(uuid.uuid4()),
                "type": "ask_user_for_manual",
                "program_name": program_name,
                "question_text": question_text,
                "user_role": "user",
                "timestamp": time.time()
            }
            result = self._execute_task(task)
            return result.get("output", result.get("message", "Failed to ask user for manual"))
        except Exception as e:
            return f"Error asking user for manual: {e}"

    def _respond_conversationally(self, response_text: str) -> str:
        """Respond conversationally to the user."""
        task = {
            "task_id": str(uuid.uuid4()),
            "type": "respond_conversationally",
            "response_text": response_text,
            "user_role": "user",
            "timestamp": time.time()
        }
        result = self._execute_task(task)
        return result.get("output", result.get("message", response_text))

    async def execute_goal(self, goal: str, conversation_history: Optional[List[Dict[str, str]]] = None) -> Dict[str, Any]:
        """Execute a goal using the LangChain agent."""
        try:
            await event_manager.publish("log_message", {
                "level": "INFO", 
                "message": f"LangChain Agent executing goal: {goal}"
            })
            
            # Build context from conversation history
            context = ""
            if conversation_history:
                context = "\n".join([f"{msg['role']}: {msg['content']}" for msg in conversation_history[-5:]])
                context = f"Recent conversation:\n{context}\n\n"
            
            # Add knowledge base context
            try:
                kb_results = await self.knowledge_base.search(goal, n_results=3)
                if kb_results:
                    kb_context = "\n".join([f"KB: {result['content'][:200]}..." for result in kb_results])
                    context += f"Relevant knowledge:\n{kb_context}\n\n"
            except Exception as e:
                logging.warning(f"Failed to search knowledge base: {e}")
            
            # Execute the goal using LangChain agent
            full_goal = f"{context}Current goal: {goal}"
            
            # Run the agent in a thread pool to avoid blocking
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(None, self.agent.run, full_goal)
            
            await event_manager.publish("log_message", {
                "level": "INFO", 
                "message": f"LangChain Agent result: {result}"
            })
            
            return {
                "status": "success",
                "tool_name": "respond_conversationally",
                "tool_args": {"response_text": result}
            }
            
        except Exception as e:
            error_msg = f"LangChain Agent error: {str(e)}"
            await event_manager.publish("error", {"message": error_msg})
            logging.error(error_msg)
            
            return {
                "status": "error",
                "tool_name": "respond_conversationally",
                "tool_args": {"response_text": error_msg}
            }

    def get_available_tools(self) -> List[str]:
        """Get list of available tool names."""
        return [tool.name for tool in self.tools]
