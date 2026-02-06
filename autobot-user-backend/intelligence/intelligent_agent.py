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
from typing import Any, AsyncGenerator, Dict, FrozenSet, List, Optional

from intelligence.goal_processor import GoalProcessor, ProcessedGoal

# Issue #380: Module-level frozenset for package managers requiring sudo
_SUDO_PACKAGE_MANAGERS: FrozenSet[str] = frozenset(
    {"apt", "yum", "dn", "pacman", "zypper"}
)

from constants.threshold_constants import TimingConstants

# Import our new intelligent agent components
from intelligence.os_detector import OSDetector, OSInfo, get_os_detector
from intelligence.streaming_executor import (
    ChunkType,
    StreamChunk,
    StreamingCommandExecutor,
)
from intelligence.tool_selector import OSAwareToolSelector
from knowledge_base import KnowledgeBase

# Import existing AutoBot components
from llm_interface import LLMInterface
from utils.command_validator import CommandValidator
from worker_node import WorkerNode

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

    # Issue #321: Helper methods to reduce message chains (Law of Demeter)
    def get_os_type_value(self) -> Optional[str]:
        """Get OS type value, reducing self.state.os_info.os_type.value chains."""
        return self.os_info.os_type.value if self.os_info else None

    def get_distro_value(self) -> Optional[str]:
        """Get distro value, reducing self.state.os_info.distro.value chains."""
        if self.os_info and self.os_info.distro:
            return self.os_info.distro.value
        return None

    def get_os_info_dict(self) -> Dict[str, Any]:
        """Get OS info as dictionary, reducing multiple attribute chains."""
        if not self.os_info:
            return {}
        return {
            "os_type": self.os_info.os_type.value,
            "distro": self.os_info.distro.value if self.os_info.distro else None,
            "version": self.os_info.version,
            "architecture": self.os_info.architecture,
            "user": self.os_info.user,
            "is_root": self.os_info.is_root,
            "is_wsl": self.os_info.is_wsl,
            "package_manager": self.os_info.package_manager,
            "shell": self.os_info.shell,
            "capabilities": list(self.os_info.capabilities)
            if self.os_info.capabilities
            else [],
        }

    def add_to_context(self, entry_type: str, content: Any, **extra) -> None:
        """Add entry to conversation context, reducing append chain usage."""
        entry = {"type": entry_type, "content": content, "timestamp": time.time()}
        entry.update(extra)
        self.conversation_context.append(entry)


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

    async def _init_core_components(self) -> None:
        """Issue #665: Extracted from initialize to reduce function length.

        Initialize OS detector, tool selector, and streaming executor.
        """
        self.os_detector = await get_os_detector()
        self.state.os_info = await self.os_detector.detect_system()
        self.tool_selector = OSAwareToolSelector(self.os_detector)
        self.streaming_executor = StreamingCommandExecutor(
            llm_interface=self.llm_interface,
            command_validator=self.command_validator,
        )

    async def _get_init_capabilities(self) -> tuple[bool, str, Dict[str, Any]]:
        """Issue #665: Extracted from initialize to reduce function length.

        Validate installation capabilities and get capability summary.
        Returns (can_install, install_reason, capabilities_info) tuple.
        """
        (
            can_install,
            install_reason,
        ) = await self.os_detector.validate_installation_capability()
        capabilities_info = await self.os_detector.get_capabilities_info()
        return can_install, install_reason, capabilities_info

    def _build_init_result(
        self,
        initialization_time: float,
        can_install: bool,
        install_reason: str,
        capabilities_info: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Issue #665: Extracted from initialize to reduce function length.

        Build the initialization result dictionary.
        """
        return {
            "status": "initialized",
            "initialization_time": initialization_time,
            "os_info": self.state.get_os_info_dict(),
            "capabilities": capabilities_info,
            "can_install_tools": can_install,
            "install_capability_reason": install_reason,
            "supported_categories": self.goal_processor.get_supported_categories(),
        }

    def _log_init_success(
        self, initialization_time: float, capabilities_info: Dict[str, Any]
    ) -> None:
        """Issue #665: Extracted from initialize to reduce function length.

        Log successful initialization details.
        """
        logger.info("Agent initialized successfully in %.2fs", initialization_time)
        logger.info("OS: %s", self.state.get_os_type_value())
        distro_value = self.state.get_distro_value()
        if distro_value:
            logger.info("Distribution: %s", distro_value)
        logger.info("Total capabilities: %s", capabilities_info.get("total_count", 0))

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
            await self._init_core_components()
            await self._update_system_context()
            (
                can_install,
                install_reason,
                capabilities_info,
            ) = await self._get_init_capabilities()

            initialization_time = time.time() - start_time
            self.state.initialized = True

            init_result = self._build_init_result(
                initialization_time, can_install, install_reason, capabilities_info
            )
            self._log_init_success(initialization_time, capabilities_info)
            return init_result

        except Exception as e:
            logger.error("Agent initialization failed: %s", e)
            return {
                "status": "initialization_failed",
                "error": str(e),
                "initialization_time": time.time() - start_time,
            }

    async def _handle_high_confidence_goal(
        self, processed_goal: ProcessedGoal, user_input: str
    ) -> AsyncGenerator[StreamChunk, None]:
        """Handle goals with high confidence (>0.5)."""
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

        for warning in processed_goal.warnings:
            yield StreamChunk(
                timestamp=self._get_timestamp(),
                chunk_type=ChunkType.COMMENTARY,
                content=f"⚠️ {warning}",
                metadata={"type": "warning"},
            )

        yield StreamChunk(
            timestamp=self._get_timestamp(),
            chunk_type=ChunkType.STATUS,
            content="🔧 Selecting the best tools for your system...",
            metadata={"step": "tool_selection"},
        )

        tool_selection = await self.tool_selector.select_tool(processed_goal)
        # Issue #321: Use helper method to reduce message chains
        self.state.add_to_context("tool_selection", tool_selection)

        async for chunk in self._execute_tool_selection(
            tool_selection, processed_goal, user_input
        ):
            yield chunk
            if chunk.chunk_type in (ChunkType.ERROR, ChunkType.COMPLETE):
                break

    async def _handle_partial_confidence_goal(
        self, processed_goal: ProcessedGoal, user_input: str
    ) -> AsyncGenerator[StreamChunk, None]:
        """Handle goals with partial confidence (0.2-0.5)."""
        yield StreamChunk(
            timestamp=self._get_timestamp(),
            chunk_type=ChunkType.COMMENTARY,
            content="🤔 I'm not entirely sure what you want. Let me suggest some possibilities...",
            metadata={
                "partial_understanding": True,
                "confidence": processed_goal.confidence,
            },
        )

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
                    content=f"{i}. {intent.explanation} (confidence: {intent.confidence:.2f})",
                    metadata={"suggestion": True, "intent": intent.intent},
                )

        async for chunk in self._handle_complex_goal(user_input):
            yield chunk

    async def _handle_low_confidence_goal(
        self, user_input: str
    ) -> AsyncGenerator[StreamChunk, None]:
        """Handle goals with low confidence (<0.2)."""
        yield StreamChunk(
            timestamp=self._get_timestamp(),
            chunk_type=ChunkType.COMMENTARY,
            content="🧠 This is a complex request. Let me analyze it using advanced reasoning...",
            metadata={"llm_processing": True},
        )
        async for chunk in self._handle_complex_goal(user_input):
            yield chunk

    def _create_not_initialized_chunk(self) -> StreamChunk:
        """Create chunk for uninitialized agent error. Issue #620."""
        return StreamChunk(
            timestamp=self._get_timestamp(),
            chunk_type=ChunkType.ERROR,
            content="❌ Agent not initialized. Please initialize first.",
            metadata={"initialization_required": True},
        )

    def _create_processing_error_chunk(self, error: Exception) -> StreamChunk:
        """Create chunk for processing error. Issue #620."""
        return StreamChunk(
            timestamp=self._get_timestamp(),
            chunk_type=ChunkType.ERROR,
            content=f"❌ Error processing request: {str(error)}",
            metadata={"error": True, "exception": str(error)},
        )

    async def _route_goal_by_confidence(
        self, processed_goal: ProcessedGoal, user_input: str
    ) -> AsyncGenerator[StreamChunk, None]:
        """Route goal to handler based on confidence level. Issue #620."""
        if processed_goal.confidence > 0.5:
            async for chunk in self._handle_high_confidence_goal(
                processed_goal, user_input
            ):
                yield chunk
        elif processed_goal.confidence > 0.2:
            async for chunk in self._handle_partial_confidence_goal(
                processed_goal, user_input
            ):
                yield chunk
        else:
            async for chunk in self._handle_low_confidence_goal(user_input):
                yield chunk

    async def process_natural_language_goal(
        self, user_input: str, context: Optional[Dict[str, Any]] = None
    ) -> AsyncGenerator[StreamChunk, None]:
        """Process natural language input and execute appropriate commands. Issue #620."""
        if not self.state.initialized:
            yield self._create_not_initialized_chunk()
            return

        logger.info("Processing natural language goal: %s", user_input)
        self.state.add_to_context("user_input", user_input, context=context or {})

        try:
            yield StreamChunk(
                timestamp=self._get_timestamp(),
                chunk_type=ChunkType.STATUS,
                content="🤔 Understanding your request...",
                metadata={"step": "goal_processing", "input": user_input},
            )

            processed_goal = await self.goal_processor.process_goal(user_input)
            self.state.add_to_context("processed_goal", processed_goal)
            async for chunk in self._route_goal_by_confidence(
                processed_goal, user_input
            ):
                yield chunk

        except Exception as e:
            logger.error("Error processing goal: %s", e)
            yield self._create_processing_error_chunk(e)

    def _create_install_required_chunk(self) -> StreamChunk:
        """Create chunk indicating tool installation is required. Issue #620."""
        return StreamChunk(
            timestamp=self._get_timestamp(),
            chunk_type=ChunkType.COMMENTARY,
            content="📦 Need to install required tool first",
            metadata={"install_required": True},
        )

    def _create_install_failed_chunk(self) -> StreamChunk:
        """Create chunk indicating tool installation cannot proceed. Issue #620."""
        return StreamChunk(
            timestamp=self._get_timestamp(),
            chunk_type=ChunkType.ERROR,
            content="❌ Required tool cannot be installed on this system",
            metadata={"installation_failed": True},
        )

    def _create_no_command_chunk(self) -> StreamChunk:
        """Create chunk indicating no suitable command was found. Issue #620."""
        return StreamChunk(
            timestamp=self._get_timestamp(),
            chunk_type=ChunkType.ERROR,
            content="❌ No suitable command found for this goal",
            metadata={"no_command_found": True},
        )

    def _yield_tool_warnings(self, tool_selection) -> List[StreamChunk]:
        """Generate warning chunks for tool selection warnings. Issue #620."""
        chunks = []
        chunks.append(
            StreamChunk(
                timestamp=self._get_timestamp(),
                chunk_type=ChunkType.COMMENTARY,
                content=f"🛠️ {tool_selection.explanation}",
                metadata={"tool_explanation": True},
            )
        )
        for warning in tool_selection.warnings:
            chunks.append(
                StreamChunk(
                    timestamp=self._get_timestamp(),
                    chunk_type=ChunkType.COMMENTARY,
                    content=f"⚠️ {warning}",
                    metadata={"type": "tool_warning"},
                )
            )
        return chunks

    async def _execute_tool_selection(
        self, tool_selection, processed_goal: ProcessedGoal, user_input: str
    ) -> AsyncGenerator[StreamChunk, None]:
        """Execute tool with optional installation. Issue #620."""
        if tool_selection.requires_install:
            yield self._create_install_required_chunk()
            if not tool_selection.install_command:
                yield self._create_install_failed_chunk()
                return
            async for chunk in self._install_tool(
                tool_selection.install_command, processed_goal
            ):
                yield chunk

        if not tool_selection.primary_command:
            yield self._create_no_command_chunk()
            return

        for chunk in self._yield_tool_warnings(tool_selection):
            yield chunk

        async for chunk in self.streaming_executor.execute_with_streaming(
            tool_selection.primary_command,
            user_input,
            timeout=TimingConstants.VERY_LONG_TIMEOUT,
        ):
            yield chunk
            if chunk.chunk_type == ChunkType.COMPLETE:
                self.state.add_to_context(
                    "command_result",
                    tool_selection.primary_command,
                    command=tool_selection.primary_command,
                    metadata=chunk.metadata,
                )
                return

    async def _handle_complex_goal(
        self, user_input: str
    ) -> AsyncGenerator[StreamChunk, None]:
        """Issue #665: Refactored to use extracted helper methods."""
        try:
            yield self._create_analysis_status_chunk()

            llm_response = await self._get_llm_analysis(user_input)
            yield self._create_analysis_result_chunk(llm_response)

            commands = self._parse_llm_commands(llm_response)
            async for chunk in self._process_parsed_commands(commands, user_input):
                yield chunk

        except Exception as e:
            logger.error("Error in complex goal handling: %s", e)
            yield self._create_llm_error_chunk(e)

    def _create_analysis_status_chunk(self) -> StreamChunk:
        """Issue #665: Extracted from _handle_complex_goal to reduce function length."""
        return StreamChunk(
            timestamp=self._get_timestamp(),
            chunk_type=ChunkType.STATUS,
            content="🧠 Analyzing request with AI reasoning...",
            metadata={"llm_analysis": True},
        )

    async def _get_llm_analysis(self, user_input: str) -> str:
        """Issue #665: Extracted from _handle_complex_goal to reduce function length.

        Get LLM analysis response for a complex goal.
        """
        system_prompt = self._build_llm_system_prompt(user_input)
        return await self.llm_interface.generate_response(
            system_prompt,
            temperature=0.3,
            max_tokens=500,
        )

    def _create_analysis_result_chunk(self, llm_response: str) -> StreamChunk:
        """Issue #665: Extracted from _handle_complex_goal to reduce function length."""
        return StreamChunk(
            timestamp=self._get_timestamp(),
            chunk_type=ChunkType.COMMENTARY,
            content=f"🎯 AI Analysis: {llm_response}",
            metadata={"llm_response": True},
        )

    async def _process_parsed_commands(
        self, commands: List[Dict[str, str]], user_input: str
    ) -> AsyncGenerator[StreamChunk, None]:
        """Issue #665: Extracted from _handle_complex_goal to reduce function length.

        Process parsed commands with safety validation and execution.
        """
        if not commands:
            yield StreamChunk(
                timestamp=self._get_timestamp(),
                chunk_type=ChunkType.COMMENTARY,
                content=(
                    "🤷 I couldn't determine specific commands for this request. "
                    "Could you try rephrasing or being more specific?"
                ),
                metadata={"no_commands_parsed": True},
            )
            return

        for i, command_info in enumerate(commands, 1):
            command = command_info.get("command")
            if not command:
                continue

            explanation = command_info.get("explanation", "")
            yield StreamChunk(
                timestamp=self._get_timestamp(),
                chunk_type=ChunkType.COMMENTARY,
                content=f"➡️ Step {i}: {explanation}",
                metadata={"explanation": True, "step": i},
            )

            async for chunk in self._execute_command_with_safety(command, user_input):
                yield chunk

    def _create_llm_error_chunk(self, error: Exception) -> StreamChunk:
        """Issue #665: Extracted from _handle_complex_goal to reduce function length."""
        return StreamChunk(
            timestamp=self._get_timestamp(),
            chunk_type=ChunkType.ERROR,
            content=f"❌ Error in AI analysis: {str(error)}",
            metadata={"llm_error": True},
        )

    async def _execute_command_with_safety(
        self, command: str, user_input: str
    ) -> AsyncGenerator[StreamChunk, None]:
        """Execute a command with safety validation (Issue #315)."""
        if self.command_validator.is_command_safe(command):
            async for chunk in self.streaming_executor.execute_with_streaming(
                command, user_input, timeout=300
            ):
                yield chunk
                if chunk.chunk_type == ChunkType.COMPLETE:
                    break
        else:
            yield StreamChunk(
                timestamp=self._get_timestamp(),
                chunk_type=ChunkType.ERROR,
                content=f"⚠️ Command blocked by security policy: {command}",
                metadata={"security_blocked": True},
            )

    def _prepare_install_command(self, install_command: str) -> str:
        """Prepare install command with sudo if needed. Issue #620."""
        if not self.state.os_info.is_root and "sudo" not in install_command:
            if any(pm in install_command for pm in _SUDO_PACKAGE_MANAGERS):
                return f"sudo {install_command}"
        return install_command

    def _create_install_result_chunk(self, success: bool) -> StreamChunk:
        """Create chunk for installation result. Issue #620."""
        if success:
            return StreamChunk(
                timestamp=self._get_timestamp(),
                chunk_type=ChunkType.STATUS,
                content="✅ Tool installed successfully",
                metadata={"installation_success": True},
            )
        return StreamChunk(
            timestamp=self._get_timestamp(),
            chunk_type=ChunkType.ERROR,
            content="❌ Tool installation failed",
            metadata={"installation_failed": True},
        )

    async def _install_tool(
        self, install_command: str, goal: ProcessedGoal
    ) -> AsyncGenerator[StreamChunk, None]:
        """Install a required tool. Issue #620."""
        yield StreamChunk(
            timestamp=self._get_timestamp(),
            chunk_type=ChunkType.STATUS,
            content="📦 Installing required tool...",
            metadata={"installing": True, "install_command": install_command},
        )

        install_command = self._prepare_install_command(install_command)
        async for chunk in self.streaming_executor.execute_with_streaming(
            install_command,
            f"Install tool for: {goal.original_goal}",
            timeout=600,
        ):
            yield chunk
            if chunk.chunk_type == ChunkType.COMPLETE:
                success = chunk.metadata.get("success", False)
                yield self._create_install_result_chunk(success)
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
            # Cache stripped line to avoid repeated calls (Issue #624)
            line_stripped = line.strip()
            if line_stripped.startswith("COMMAND:"):
                if current_command.get("command"):
                    commands.append(current_command)
                current_command = {"command": line_stripped[8:].strip()}
            elif line_stripped.startswith("EXPLANATION:"):
                current_command["explanation"] = line_stripped[12:].strip()
            elif line_stripped.startswith("NEXT:"):
                current_command["next"] = line_stripped[5:].strip()

        if current_command.get("command"):
            commands.append(current_command)

        return commands

    async def _update_system_context(self):
        """Update LLM and knowledge base with current system context."""
        # Issue #321: Use helper method to reduce message chains
        os_info = self.state.get_os_info_dict()
        context = f"""System Information for Intelligent Agent:
- OS: {os_info.get('os_type', 'Unknown')}
- Distribution: {os_info.get('distro', 'N/A')}
- Version: {os_info.get('version', 'Unknown')}
- Architecture: {os_info.get('architecture', 'Unknown')}
- User: {os_info.get('user', 'Unknown')}
- Root Access: {os_info.get('is_root', False)}
- WSL Environment: {os_info.get('is_wsl', False)}
- Package Manager: {os_info.get('package_manager', 'Unknown')}
- Shell: {os_info.get('shell', 'Unknown')}
- Available Capabilities: {', '.join(os_info.get('capabilities', []))}

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
                    "os_type": os_info.get("os_type", "Unknown"),
                    "timestamp": time.time(),
                    "agent_version": "1.0",
                },
            )
        except Exception as e:
            logger.warning("Failed to store system context in knowledge base: %s", e)

    def _get_timestamp(self) -> str:
        """Get current timestamp in ISO format."""
        from utils.command_utils import get_timestamp

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

        # Issue #321: Use helper method to reduce message chains
        return {
            "status": "initialized",
            "os_info": self.state.get_os_info_dict(),
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


# Global instance for reuse (thread-safe)
import asyncio as _asyncio

_agent_instance: Optional[IntelligentAgent] = None
_agent_lock = _asyncio.Lock()


async def get_intelligent_agent(
    llm_interface: LLMInterface = None,
    knowledge_base: KnowledgeBase = None,
    worker_node: WorkerNode = None,
    command_validator: CommandValidator = None,
) -> IntelligentAgent:
    """
    Get singleton intelligent agent instance (thread-safe).

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
        async with _agent_lock:
            # Double-check after acquiring lock
            if _agent_instance is None:
                if not all(
                    [llm_interface, knowledge_base, worker_node, command_validator]
                ):
                    raise ValueError("All components required for first initialization")

                _agent_instance = IntelligentAgent(
                    llm_interface, knowledge_base, worker_node, command_validator
                )
                await _agent_instance.initialize()

    return _agent_instance


if __name__ == "__main__":
    """Test the intelligent agent functionality."""
    import sys
    from pathlib import Path

    # Add project root for test imports
    project_root = Path(__file__).parent.parent.parent
    sys.path.insert(0, str(project_root))

    # Import mock components from test fixtures (Issue #458)
    from tests.fixtures.mocks import (
        MockCommandValidator,
        MockKnowledgeBase,
        MockLLMInterface,
        MockWorkerNode,
    )

    async def test_agent():
        """Test intelligent agent with mock components."""
        # Create mock components from tests/fixtures/mocks.py
        llm = MockLLMInterface()
        kb = MockKnowledgeBase()
        wn = MockWorkerNode()
        cv = MockCommandValidator()

        # Create and initialize agent
        agent = IntelligentAgent(llm, kb, wn, cv)
        init_result = await agent.initialize()

        logger.info("=== Initialization Result ===")
        logger.info("Status: %s", init_result["status"])
        logger.info("OS: %s", init_result["os_info"]["os_type"])
        logger.info("Capabilities: %s", init_result["capabilities"]["total_count"])
        print()

        # Test natural language processing
        test_goals = [
            "what is my ip address?",
            "list the files in current directory",
            "show system information",
        ]

        for goal in test_goals:
            logger.info("=== Testing Goal: %s ===", goal)

            async for chunk in agent.process_natural_language_goal(goal):
                timestamp = chunk.timestamp.split("T")[1][:8]
                chunk_type = chunk.chunk_type.value.upper()
                content = chunk.content

                logger.info("[%s] %s: %s", timestamp, chunk_type, content)

                if chunk.chunk_type == ChunkType.COMPLETE:
                    break

            print()

    asyncio.run(test_agent())
