# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Main Intelligent Agent Orchestrator for OS-Aware Command Processing

This module orchestrates the complete workflow from natural language goals
to OS-aware command execution with real-time streaming and intelligent commentary.
"""

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Any, AsyncGenerator, Dict, List, Optional

from src.intelligence.goal_processor import GoalProcessor, ProcessedGoal

# Import our new intelligent agent components
from src.intelligence.os_detector import OSDetector, OSInfo, get_os_detector
from src.intelligence.streaming_executor import (
    ChunkType,
    StreamChunk,
    StreamingCommandExecutor,
)
from src.intelligence.tool_selector import OSAwareToolSelector
from src.knowledge_base import KnowledgeBase

# Import existing AutoBot components
from src.llm_interface import LLMInterface
from src.utils.command_validator import CommandValidator
from src.worker_node import WorkerNode

logger = logging.getLogger(__name__)


@dataclass
class AgentState:
    """Current state of the intelligent agent."""

    os_info: Optional[OSInfo] = None
    conversation_context: List[Dict[str, Any]] = None
    last_command_result: Optional[Dict[str, Any]] = None
    active_processes: List[str] = None
    initialized: bool = False

    def __post_init__(self):
        """Initialize lists if None."""
        if self.conversation_context is None:
            self.conversation_context = []
        if self.active_processes is None:
            self.active_processes = []


class IntelligentAgent:
    """Main intelligent agent orchestrator."""

    def __init__(
        self,
        llm_interface: LLMInterface,
        knowledge_base: KnowledgeBase,
        worker_node: WorkerNode,
        command_validator: CommandValidator,
    ):
        """
        Initialize the intelligent agent.

        Args:
            llm_interface: LLM interface for natural language processing
            knowledge_base: Knowledge base for storing facts and context
            worker_node: Worker node for task execution
            command_validator: Command validator for security checks
        """
        self.llm_interface = llm_interface
        self.knowledge_base = knowledge_base
        self.worker_node = worker_node
        self.command_validator = command_validator

        # Initialize intelligent agent components
        self.os_detector: Optional[OSDetector] = None
        self.goal_processor = GoalProcessor()
        self.tool_selector: Optional[OSAwareToolSelector] = None
        self.streaming_executor: Optional[StreamingCommandExecutor] = None

        # Agent state
        self.state = AgentState()

        logger.info("Intelligent Agent initialized")

    async def initialize(self) -> Dict[str, Any]:
        """
        Initialize the agent system with OS detection and capability assessment.

        Returns:
            Dict[str, Any]: Initialization results and system information
        """
        if self.state.initialized:
            return {"status": "already_initialized", "os_info": self.state.os_info}

        logger.info("Initializing Intelligent Agent system...")

        start_time = time.time()

        try:
            # Initialize OS detector
            self.os_detector = await get_os_detector()
            self.state.os_info = await self.os_detector.detect_system()

            # Initialize tool selector with OS detector
            self.tool_selector = OSAwareToolSelector(self.os_detector)

            # Initialize streaming executor with LLM and validator
            self.streaming_executor = StreamingCommandExecutor(
                llm_interface=self.llm_interface,
                command_validator=self.command_validator,
            )

            # Update system context in LLM and knowledge base
            await self._update_system_context()

            # Validate installation capabilities
            (
                can_install,
                install_reason,
            ) = await self.os_detector.validate_installation_capability()

            # Get capability summary
            capabilities_info = await self.os_detector.get_capabilities_info()

            initialization_time = time.time() - start_time

            self.state.initialized = True

            init_result = {
                "status": "initialized",
                "initialization_time": initialization_time,
                "os_info": {
                    "os_type": self.state.os_info.os_type.value,
                    "distro": (
                        self.state.os_info.distro.value
                        if self.state.os_info.distro
                        else None
                    ),
                    "version": self.state.os_info.version,
                    "architecture": self.state.os_info.architecture,
                    "user": self.state.os_info.user,
                    "is_root": self.state.os_info.is_root,
                    "is_wsl": self.state.os_info.is_wsl,
                    "package_manager": self.state.os_info.package_manager,
                },
                "capabilities": capabilities_info,
                "can_install_tools": can_install,
                "install_capability_reason": install_reason,
                "supported_categories": self.goal_processor.get_supported_categories(),
            }

            logger.info(f"Agent initialized successfully in {initialization_time:.2f}s")
            logger.info(f"OS: {self.state.os_info.os_type.value}")
            if self.state.os_info.distro:
                logger.info(f"Distribution: {self.state.os_info.distro.value}")
            logger.info(
                f"Total capabilities: {capabilities_info.get('total_count', 0)}"
            )

            return init_result

        except Exception as e:
            logger.error(f"Agent initialization failed: {e}")
            return {
                "status": "initialization_failed",
                "error": str(e),
                "initialization_time": time.time() - start_time,
            }

    async def process_natural_language_goal(
        self, user_input: str, context: Optional[Dict[str, Any]] = None
    ) -> AsyncGenerator[StreamChunk, None]:
        """
        Process natural language input and execute appropriate commands.

        Args:
            user_input: Natural language goal from user
            context: Additional context information

        Yields:
            StreamChunk: Stream of processing and execution results
        """
        if not self.state.initialized:
            yield StreamChunk(
                timestamp=self._get_timestamp(),
                chunk_type=ChunkType.ERROR,
                content="❌ Agent not initialized. Please initialize first.",
                metadata={"initialization_required": True},
            )
            return

        logger.info(f"Processing natural language goal: {user_input}")

        # Add to conversation context
        self.state.conversation_context.append(
            {
                "type": "user_input",
                "content": user_input,
                "timestamp": time.time(),
                "context": context or {},
            }
        )

        try:
            # Step 1: Process the goal into structured intent
            yield StreamChunk(
                timestamp=self._get_timestamp(),
                chunk_type=ChunkType.STATUS,
                content="🤔 Understanding your request...",
                metadata={"step": "goal_processing", "input": user_input},
            )

            processed_goal = await self.goal_processor.process_goal(user_input)

            # Add goal to conversation context
            self.state.conversation_context.append(
                {
                    "type": "processed_goal",
                    "content": processed_goal,
                    "timestamp": time.time(),
                }
            )

            if processed_goal.confidence > 0.5:
                # We have a good understanding of the goal
                yield StreamChunk(
                    timestamp=self._get_timestamp(),
                    chunk_type=ChunkType.COMMENTARY,
                    content=f"💡 I understand you want to: {processed_goal.explanation}",
                    metadata={
                        "intent": processed_goal.intent,
                        "confidence": processed_goal.confidence,
                        "category": processed_goal.category.value,
                        "risk_level": processed_goal.risk_level.value,
                    },
                )

                # Show warnings if any
                if processed_goal.warnings:
                    for warning in processed_goal.warnings:
                        yield StreamChunk(
                            timestamp=self._get_timestamp(),
                            chunk_type=ChunkType.COMMENTARY,
                            content=f"⚠️ {warning}",
                            metadata={"type": "warning"},
                        )

                # Step 2: Select appropriate tools
                yield StreamChunk(
                    timestamp=self._get_timestamp(),
                    chunk_type=ChunkType.STATUS,
                    content="🔧 Selecting the best tools for your system...",
                    metadata={"step": "tool_selection"},
                )

                tool_selection = await self.tool_selector.select_tool(processed_goal)

                # Add tool selection to context
                self.state.conversation_context.append(
                    {
                        "type": "tool_selection",
                        "content": tool_selection,
                        "timestamp": time.time(),
                    }
                )

                # Step 3: Handle tool installation if needed
                if tool_selection.requires_install:
                    yield StreamChunk(
                        timestamp=self._get_timestamp(),
                        chunk_type=ChunkType.COMMENTARY,
                        content="📦 Need to install required tool first",
                        metadata={"install_required": True},
                    )

                    if tool_selection.install_command:
                        async for chunk in self._install_tool(
                            tool_selection.install_command, processed_goal
                        ):
                            yield chunk
                    else:
                        yield StreamChunk(
                            timestamp=self._get_timestamp(),
                            chunk_type=ChunkType.ERROR,
                            content=(
                                "❌ Required tool cannot be installed on this system"
                            ),
                            metadata={"installation_failed": True},
                        )
                        return

                # Step 4: Execute the command
                if tool_selection.primary_command:
                    # Show tool selection explanation
                    yield StreamChunk(
                        timestamp=self._get_timestamp(),
                        chunk_type=ChunkType.COMMENTARY,
                        content=f"🛠️ {tool_selection.explanation}",
                        metadata={"tool_explanation": True},
                    )

                    # Show any tool warnings
                    for warning in tool_selection.warnings:
                        yield StreamChunk(
                            timestamp=self._get_timestamp(),
                            chunk_type=ChunkType.COMMENTARY,
                            content=f"⚠️ {warning}",
                            metadata={"type": "tool_warning"},
                        )

                    # Execute the command with streaming
                    async for chunk in self.streaming_executor.execute_with_streaming(
                        tool_selection.primary_command,
                        user_input,
                        timeout=300,  # 5 minute timeout
                    ):
                        yield chunk

                        # Track process completion
                        if chunk.chunk_type == ChunkType.COMPLETE:
                            # Update conversation context with result
                            self.state.conversation_context.append(
                                {
                                    "type": "command_result",
                                    "command": tool_selection.primary_command,
                                    "timestamp": time.time(),
                                    "metadata": chunk.metadata,
                                }
                            )
                            break
                else:
                    yield StreamChunk(
                        timestamp=self._get_timestamp(),
                        chunk_type=ChunkType.ERROR,
                        content="❌ No suitable command found for this goal",
                        metadata={"no_command_found": True},
                    )

            elif processed_goal.confidence > 0.2:
                # Partial understanding - offer alternatives
                yield StreamChunk(
                    timestamp=self._get_timestamp(),
                    chunk_type=ChunkType.COMMENTARY,
                    content=(
                        "🤔 I'm not entirely sure what you want. "
                        "Let me suggest some possibilities..."
                    ),
                    metadata={
                        "partial_understanding": True,
                        "confidence": processed_goal.confidence,
                    },
                )

                # Get similar intents
                similar_intents = await self.goal_processor.get_similar_intents(
                    user_input, limit=3
                )

                if similar_intents:
                    yield StreamChunk(
                        timestamp=self._get_timestamp(),
                        chunk_type=ChunkType.COMMENTARY,
                        content="💭 Here are some similar requests I can help with:",
                        metadata={"suggestions": True},
                    )

                    for i, intent in enumerate(similar_intents, 1):
                        yield StreamChunk(
                            timestamp=self._get_timestamp(),
                            chunk_type=ChunkType.COMMENTARY,
                            content=(
                                f"{i}. {intent.explanation} "
                                f"(confidence: {intent.confidence:.2f})"
                            ),
                            metadata={"suggestion": True, "intent": intent.intent},
                        )

                # Fall back to LLM processing
                async for chunk in self._handle_complex_goal(user_input):
                    yield chunk

            else:
                # Unknown goal - use LLM to figure it out
                yield StreamChunk(
                    timestamp=self._get_timestamp(),
                    chunk_type=ChunkType.COMMENTARY,
                    content=(
                        "🧠 This is a complex request. "
                        "Let me analyze it using advanced reasoning..."
                    ),
                    metadata={"llm_processing": True},
                )

                async for chunk in self._handle_complex_goal(user_input):
                    yield chunk

        except Exception as e:
            logger.error(f"Error processing goal: {e}")
            yield StreamChunk(
                timestamp=self._get_timestamp(),
                chunk_type=ChunkType.ERROR,
                content=f"❌ Error processing request: {str(e)}",
                metadata={"error": True, "exception": str(e)},
            )

    async def _handle_complex_goal(
        self, user_input: str
    ) -> AsyncGenerator[StreamChunk, None]:
        """
        Handle complex goals that require LLM reasoning.

        Args:
            user_input: Original user input

        Yields:
            StreamChunk: Processing results
        """
        try:
            # Create comprehensive system prompt with current context
            system_prompt = self._build_llm_system_prompt(user_input)

            yield StreamChunk(
                timestamp=self._get_timestamp(),
                chunk_type=ChunkType.STATUS,
                content="🧠 Analyzing request with AI reasoning...",
                metadata={"llm_analysis": True},
            )

            # Use LLM to break down the goal and suggest commands
            llm_response = await self.llm_interface.generate_response(
                system_prompt,
                temperature=0.3,  # Lower temperature for more focused responses
                max_tokens=500,
            )

            yield StreamChunk(
                timestamp=self._get_timestamp(),
                chunk_type=ChunkType.COMMENTARY,
                content=f"🎯 AI Analysis: {llm_response}",
                metadata={"llm_response": True},
            )

            # Parse LLM response and extract commands
            commands = self._parse_llm_commands(llm_response)

            if commands:
                for i, command_info in enumerate(commands, 1):
                    command = command_info.get("command")
                    explanation = command_info.get("explanation", "")

                    if command:
                        yield StreamChunk(
                            timestamp=self._get_timestamp(),
                            chunk_type=ChunkType.COMMENTARY,
                            content=f"➡️ Step {i}: {explanation}",
                            metadata={"explanation": True, "step": i},
                        )

                        # Validate command safety
                        if self.command_validator.is_command_safe(command):
                            # Execute the command
                            async for (
                                chunk
                            ) in self.streaming_executor.execute_with_streaming(
                                command, user_input, timeout=300
                            ):
                                yield chunk

                                if chunk.chunk_type == ChunkType.COMPLETE:
                                    break
                        else:
                            yield StreamChunk(
                                timestamp=self._get_timestamp(),
                                chunk_type=ChunkType.ERROR,
                                content=(
                                    f"⚠️ Command blocked by security policy: {command}"
                                ),
                                metadata={"security_blocked": True},
                            )
            else:
                yield StreamChunk(
                    timestamp=self._get_timestamp(),
                    chunk_type=ChunkType.COMMENTARY,
                    content=(
                        "🤷 I couldn't determine specific commands for this request. "
                        "Could you try rephrasing or being more specific?"
                    ),
                    metadata={"no_commands_parsed": True},
                )

        except Exception as e:
            logger.error(f"Error in complex goal handling: {e}")
            yield StreamChunk(
                timestamp=self._get_timestamp(),
                chunk_type=ChunkType.ERROR,
                content=f"❌ Error in AI analysis: {str(e)}",
                metadata={"llm_error": True},
            )

    async def _install_tool(
        self, install_command: str, goal: ProcessedGoal
    ) -> AsyncGenerator[StreamChunk, None]:
        """
        Install a required tool.

        Args:
            install_command: Command to install the tool
            goal: Original processed goal

        Yields:
            StreamChunk: Installation progress
        """
        yield StreamChunk(
            timestamp=self._get_timestamp(),
            chunk_type=ChunkType.STATUS,
            content="📦 Installing required tool...",
            metadata={"installing": True, "install_command": install_command},
        )

        # Check if installation requires root and we don't have it
        if not self.state.os_info.is_root and "sudo" not in install_command:
            # Add sudo if needed for common package managers
            if any(
                pm in install_command for pm in ["apt", "yum", "dn", "pacman", "zypper"]
            ):
                install_command = f"sudo {install_command}"

        # Execute installation command
        async for chunk in self.streaming_executor.execute_with_streaming(
            install_command,
            f"Install tool for: {goal.original_goal}",
            timeout=600,  # Longer timeout for installations
        ):
            yield chunk

            if chunk.chunk_type == ChunkType.COMPLETE:
                # Check if installation was successful
                success = chunk.metadata.get("success", False)
                if success:
                    yield StreamChunk(
                        timestamp=self._get_timestamp(),
                        chunk_type=ChunkType.STATUS,
                        content="✅ Tool installed successfully",
                        metadata={"installation_success": True},
                    )
                else:
                    yield StreamChunk(
                        timestamp=self._get_timestamp(),
                        chunk_type=ChunkType.ERROR,
                        content="❌ Tool installation failed",
                        metadata={"installation_failed": True},
                    )
                break

    def _build_llm_system_prompt(self, user_input: str) -> str:
        """
        Build comprehensive system prompt for LLM analysis.

        Args:
            user_input: User's request

        Returns:
            str: System prompt for LLM
        """
        os_info = self.state.os_info
        distro_value = os_info.distro.value if os_info.distro else "N/A"

        system_prompt = f"""You are an intelligent system administrator assistant.

SYSTEM INFORMATION:
- OS: {os_info.os_type.value}
- Distribution: {distro_value}
- Version: {os_info.version}
- Architecture: {os_info.architecture}
- User: {os_info.user}
- Root Access: {os_info.is_root}
- Package Manager: {os_info.package_manager}
- Available Capabilities: {len(os_info.capabilities)} tools detected

USER REQUEST: "{user_input}"

Your task is to analyze this request and provide specific, executable \
commands for this system.
Consider the OS, available tools, and security implications.

IMPORTANT INSTRUCTIONS:
1. Provide commands that are appropriate for {os_info.os_type.value}
2. Consider whether the user has root access ({os_info.is_root})
3. Use the package manager {os_info.package_manager} if needed
4. Be security-conscious and warn about risky operations
5. Provide step-by-step commands if multiple steps are needed

Format your response as:
COMMAND: [specific command]
EXPLANATION: [what this command does]
NEXT: [what to do with the results, if anything]

If multiple commands are needed, provide them in order.
If the request is unclear or potentially dangerous, explain why and \
suggest alternatives.
"""

        return system_prompt

    def _parse_llm_commands(self, llm_response: str) -> List[Dict[str, str]]:
        """
        Parse commands from LLM response.

        Args:
            llm_response: Response from LLM

        Returns:
            List[Dict[str, str]]: Parsed command information
        """
        commands = []
        lines = llm_response.split("\n")
        current_command = {}

        for line in lines:
            line = line.strip()
            if line.startswith("COMMAND:"):
                if current_command.get("command"):
                    commands.append(current_command)
                current_command = {"command": line[8:].strip()}
            elif line.startswith("EXPLANATION:"):
                current_command["explanation"] = line[12:].strip()
            elif line.startswith("NEXT:"):
                current_command["next"] = line[5:].strip()

        if current_command.get("command"):
            commands.append(current_command)

        return commands

    async def _update_system_context(self):
        """Update LLM and knowledge base with current system context."""
        context = """System Information for Intelligent Agent:
- OS: {self.state.os_info.os_type.value}
- Distribution: {
            self.state.os_info.distro.value if self.state.os_info.distro else 'N/A'
        }
- Version: {self.state.os_info.version}
- Architecture: {self.state.os_info.architecture}
- User: {self.state.os_info.user}
- Root Access: {self.state.os_info.is_root}
- WSL Environment: {self.state.os_info.is_wsl}
- Package Manager: {self.state.os_info.package_manager}
- Shell: {self.state.os_info.shell}
- Available Capabilities: {', '.join(self.state.os_info.capabilities)}

I am an intelligent system assistant running on this system.
I can execute commands, install tools, and provide real-time analysis of results.
I understand natural language goals and translate them into appropriate \
OS-specific commands.
"""

        # Store in knowledge base for future reference
        try:
            await self.knowledge_base.store_fact(
                content=context,
                metadata={
                    "type": "system_context",
                    "os_type": self.state.os_info.os_type.value,
                    "timestamp": time.time(),
                    "agent_version": "1.0",
                },
            )
        except Exception as e:
            logger.warning(f"Failed to store system context in knowledge base: {e}")

    def _get_timestamp(self) -> str:
        """Get current timestamp in ISO format."""
        from src.utils.command_utils import get_timestamp

        return get_timestamp()

    async def get_system_status(self) -> Dict[str, Any]:
        """
        Get current system status and agent information.

        Returns:
            Dict[str, Any]: System status information
        """
        if not self.state.initialized:
            return {"status": "not_initialized"}

        # Get active processes
        active_processes = []
        if self.streaming_executor:
            active_processes = self.streaming_executor.get_active_processes()

        # Get capability summary
        capabilities_info = await self.os_detector.get_capabilities_info()

        return {
            "status": "initialized",
            "os_info": {
                "os_type": self.state.os_info.os_type.value,
                "distro": (
                    self.state.os_info.distro.value
                    if self.state.os_info.distro
                    else None
                ),
                "version": self.state.os_info.version,
                "user": self.state.os_info.user,
                "is_root": self.state.os_info.is_root,
                "package_manager": self.state.os_info.package_manager,
            },
            "capabilities": capabilities_info,
            "active_processes": len(active_processes),
            "conversation_context_length": len(self.state.conversation_context),
            "supported_categories": self.goal_processor.get_supported_categories(),
        }

    async def get_conversation_context(self) -> List[Dict[str, Any]]:
        """
        Get conversation context history.

        Returns:
            List[Dict[str, Any]]: Conversation context
        """
        return self.state.conversation_context

    async def clear_conversation_context(self):
        """Clear conversation context history."""
        self.state.conversation_context = []
        logger.info("Conversation context cleared")

    async def kill_process(self, process_id: str) -> bool:
        """
        Kill a specific running process.

        Args:
            process_id: Process identifier

        Returns:
            bool: True if process was killed successfully
        """
        if self.streaming_executor:
            return await self.streaming_executor.kill_process(process_id)
        return False

    async def kill_all_processes(self):
        """Kill all managed processes."""
        if self.streaming_executor:
            self.streaming_executor.kill_all_processes()
        self.state.active_processes = []
        logger.info("All processes killed")


# Global instance for reuse
_agent_instance: Optional[IntelligentAgent] = None


async def get_intelligent_agent(
    llm_interface: LLMInterface = None,
    knowledge_base: KnowledgeBase = None,
    worker_node: WorkerNode = None,
    command_validator: CommandValidator = None,
) -> IntelligentAgent:
    """
    Get singleton intelligent agent instance.

    Args:
        llm_interface: LLM interface instance
        knowledge_base: Knowledge base instance
        worker_node: Worker node instance
        command_validator: Command validator instance

    Returns:
        IntelligentAgent: Global agent instance
    """
    global _agent_instance
    if _agent_instance is None:
        if not all([llm_interface, knowledge_base, worker_node, command_validator]):
            raise ValueError("All components required for first initialization")

        _agent_instance = IntelligentAgent(
            llm_interface, knowledge_base, worker_node, command_validator
        )
        await _agent_instance.initialize()

    return _agent_instance


if __name__ == "__main__":
    """Test the intelligent agent functionality."""

    # Mock components for testing
    class MockLLMInterface:
        async def generate_response(self, prompt, **kwargs):
            return (
                "COMMAND: echo 'This is a test response'\n"
                "EXPLANATION: Testing the system"
            )

    class MockKnowledgeBase:
        async def store_fact(self, content, metadata=None):
            print(f"Storing: {content[:100]}...")

    class MockWorkerNode:
        pass

    class MockCommandValidator:
        def is_command_safe(self, command):
            return True

    async def test_agent():
        # Create mock components
        llm = MockLLMInterface()
        kb = MockKnowledgeBase()
        wn = MockWorkerNode()
        cv = MockCommandValidator()

        # Create and initialize agent
        agent = IntelligentAgent(llm, kb, wn, cv)
        init_result = await agent.initialize()

        print("=== Initialization Result ===")
        print(f"Status: {init_result['status']}")
        print(f"OS: {init_result['os_info']['os_type']}")
        print(f"Capabilities: {init_result['capabilities']['total_count']}")
        print()

        # Test natural language processing
        test_goals = [
            "what is my ip address?",
            "list the files in current directory",
            "show system information",
        ]

        for goal in test_goals:
            print(f"=== Testing Goal: {goal} ===")

            async for chunk in agent.process_natural_language_goal(goal):
                timestamp = chunk.timestamp.split("T")[1][:8]
                chunk_type = chunk.chunk_type.value.upper()
                content = chunk.content

                print(f"[{timestamp}] {chunk_type}: {content}")

                if chunk.chunk_type == ChunkType.COMPLETE:
                    break

            print()

    asyncio.run(test_agent())
