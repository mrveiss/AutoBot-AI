# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Command Execution Queue Manager - Handles Multiple Parallel Sessions

Supports:
- Multiple chat sessions simultaneously
- Multiple terminal sessions per chat
- Multiple pending commands per session
- Concurrent command execution
- Persistent storage (Redis + SQLite)
"""

import json
import logging
from typing import List, Optional

from backend.models.command_execution import CommandExecution, CommandState
from src.utils.redis_client import get_redis_client

logger = logging.getLogger(__name__)


class CommandExecutionQueue:
    """
    Central queue for all command executions across all sessions.

    Persistent storage ensures commands survive backend restarts.
    Indexed by command_id, terminal_session_id, and chat_id for fast lookups.
    """

    def __init__(self):
        """Initialize command queue with Redis backend"""
        self.redis_client = None
        self._initialize_redis()

    def _initialize_redis(self):
        """Initialize Redis connection"""
        try:
            # Use 'main' database for command queue
            self.redis_client = get_redis_client(async_client=False, database="main")
            if self.redis_client:
                logger.info("✅ Command execution queue initialized with Redis")
            else:
                logger.warning(
                    "⚠️ Redis not available for command queue - commands won't persist across restarts"
                )
        except Exception as e:
            logger.error(f"Failed to initialize Redis for command queue: {e}")

    def _get_command_key(self, command_id: str) -> str:
        """Get Redis key for command by ID"""
        return f"command:execution:{command_id}"

    def _get_session_commands_key(self, terminal_session_id: str) -> str:
        """Get Redis key for terminal session's command list"""
        return f"terminal:commands:{terminal_session_id}"

    def _get_chat_commands_key(self, chat_id: str) -> str:
        """Get Redis key for chat's command list"""
        return f"chat:commands:{chat_id}"

    def _get_pending_approvals_key(self) -> str:
        """Get Redis key for global pending approvals list"""
        return "commands:pending_approvals"

    async def add_command(self, command: CommandExecution) -> bool:
        """
        Add command to queue.

        Args:
            command: Command execution to add

        Returns:
            True if added successfully
        """
        if not self.redis_client:
            logger.error("Cannot add command - Redis not available")
            return False

        try:
            # Store command by ID (primary key)
            command_key = self._get_command_key(command.command_id)
            command_data = json.dumps(command.to_dict())
            self.redis_client.setex(command_key, 86400, command_data)  # 24 hour TTL

            # Add to terminal session's command list
            session_key = self._get_session_commands_key(command.terminal_session_id)
            self.redis_client.sadd(session_key, command.command_id)
            self.redis_client.expire(session_key, 86400)

            # Add to chat's command list
            chat_key = self._get_chat_commands_key(command.chat_id)
            self.redis_client.sadd(chat_key, command.command_id)
            self.redis_client.expire(chat_key, 86400)

            # If pending approval, add to global pending list
            if command.is_pending():
                pending_key = self._get_pending_approvals_key()
                self.redis_client.sadd(pending_key, command.command_id)

            logger.info(
                f"✅ [QUEUE] Added command {command.command_id} to queue: "
                f"terminal={command.terminal_session_id}, chat={command.chat_id}, "
                f"state={command.state.value}"
            )
            return True

        except Exception as e:
            logger.error(f"Failed to add command to queue: {e}")
            return False

    async def get_command(self, command_id: str) -> Optional[CommandExecution]:
        """
        Get command by ID.

        Args:
            command_id: Command ID to retrieve

        Returns:
            CommandExecution or None if not found
        """
        if not self.redis_client:
            return None

        try:
            command_key = self._get_command_key(command_id)
            command_data = self.redis_client.get(command_key)

            if not command_data:
                return None

            data = json.loads(command_data)
            return CommandExecution.from_dict(data)

        except Exception as e:
            logger.error(f"Failed to get command {command_id}: {e}")
            return None

    async def update_command(self, command: CommandExecution) -> bool:
        """
        Update command in queue.

        Args:
            command: Updated command

        Returns:
            True if updated successfully
        """
        if not self.redis_client:
            return False

        try:
            # Update command data
            command_key = self._get_command_key(command.command_id)
            command_data = json.dumps(command.to_dict())
            self.redis_client.setex(command_key, 86400, command_data)

            # Update pending approvals list
            pending_key = self._get_pending_approvals_key()
            if command.is_pending():
                self.redis_client.sadd(pending_key, command.command_id)
            else:
                self.redis_client.srem(pending_key, command.command_id)

            logger.debug(
                f"Updated command {command.command_id} in queue: state={command.state.value}"
            )
            return True

        except Exception as e:
            logger.error(f"Failed to update command {command.command_id}: {e}")
            return False

    async def get_terminal_commands(
        self, terminal_session_id: str, state_filter: Optional[CommandState] = None
    ) -> List[CommandExecution]:
        """
        Get all commands for a terminal session.

        Args:
            terminal_session_id: Terminal session ID
            state_filter: Optional filter by state

        Returns:
            List of commands for this terminal session
        """
        if not self.redis_client:
            return []

        try:
            session_key = self._get_session_commands_key(terminal_session_id)
            command_ids = self.redis_client.smembers(session_key)

            if not command_ids:
                return []

            # Decode command IDs
            decoded_ids = [cid.decode("utf-8") for cid in command_ids]

            # Batch fetch all commands using pipeline - eliminates N+1 queries
            pipe = self.redis_client.pipeline()
            for command_id in decoded_ids:
                pipe.get(self._get_command_key(command_id))
            results = pipe.execute()

            # Process results
            commands = []
            for command_data in results:
                if command_data:
                    try:
                        data = json.loads(command_data)
                        cmd = CommandExecution.from_dict(data)
                        if state_filter is None or cmd.state == state_filter:
                            commands.append(cmd)
                    except (json.JSONDecodeError, Exception) as e:
                        logger.debug(f"Failed to parse command data: {e}")

            # Sort by requested_at (newest first)
            commands.sort(key=lambda c: c.requested_at, reverse=True)
            return commands

        except Exception as e:
            logger.error(
                f"Failed to get terminal commands for {terminal_session_id}: {e}"
            )
            return []

    async def get_chat_commands(
        self, chat_id: str, state_filter: Optional[CommandState] = None
    ) -> List[CommandExecution]:
        """
        Get all commands for a chat session.

        Args:
            chat_id: Chat/conversation ID
            state_filter: Optional filter by state

        Returns:
            List of commands for this chat
        """
        if not self.redis_client:
            return []

        try:
            chat_key = self._get_chat_commands_key(chat_id)
            command_ids = self.redis_client.smembers(chat_key)

            if not command_ids:
                return []

            # Decode command IDs
            decoded_ids = [cid.decode("utf-8") for cid in command_ids]

            # Batch fetch all commands using pipeline - eliminates N+1 queries
            pipe = self.redis_client.pipeline()
            for command_id in decoded_ids:
                pipe.get(self._get_command_key(command_id))
            results = pipe.execute()

            # Process results
            commands = []
            for command_data in results:
                if command_data:
                    try:
                        data = json.loads(command_data)
                        cmd = CommandExecution.from_dict(data)
                        if state_filter is None or cmd.state == state_filter:
                            commands.append(cmd)
                    except (json.JSONDecodeError, Exception) as e:
                        logger.debug(f"Failed to parse command data: {e}")

            # Sort by requested_at (newest first)
            commands.sort(key=lambda c: c.requested_at, reverse=True)
            return commands

        except Exception as e:
            logger.error(f"Failed to get chat commands for {chat_id}: {e}")
            return []

    async def get_pending_approvals(self) -> List[CommandExecution]:
        """
        Get all pending approval commands across ALL sessions.

        Returns:
            List of commands awaiting approval
        """
        if not self.redis_client:
            return []

        try:
            pending_key = self._get_pending_approvals_key()
            command_ids = self.redis_client.smembers(pending_key)

            if not command_ids:
                return []

            # Decode command IDs
            decoded_ids = [cid.decode("utf-8") for cid in command_ids]

            # Batch fetch all commands using pipeline - eliminates N+1 queries
            pipe = self.redis_client.pipeline()
            for command_id in decoded_ids:
                pipe.get(self._get_command_key(command_id))
            results = pipe.execute()

            # Process results
            commands = []
            for command_data in results:
                if command_data:
                    try:
                        data = json.loads(command_data)
                        cmd = CommandExecution.from_dict(data)
                        if cmd.is_pending():
                            commands.append(cmd)
                    except (json.JSONDecodeError, Exception) as e:
                        logger.debug(f"Failed to parse command data: {e}")

            # Sort by requested_at (oldest first - FIFO)
            commands.sort(key=lambda c: c.requested_at)
            return commands

        except Exception as e:
            logger.error(f"Failed to get pending approvals: {e}")
            return []

    async def get_latest_pending_for_chat(
        self, chat_id: str
    ) -> Optional[CommandExecution]:
        """
        Get the most recent pending approval for a chat.

        Args:
            chat_id: Chat/conversation ID

        Returns:
            Latest pending command or None
        """
        commands = await self.get_chat_commands(
            chat_id, state_filter=CommandState.PENDING_APPROVAL
        )
        return commands[0] if commands else None

    async def approve_command(
        self, command_id: str, user_id: str, comment: Optional[str] = None
    ) -> bool:
        """
        Approve a pending command.

        Args:
            command_id: Command to approve
            user_id: User approving the command
            comment: Optional approval comment

        Returns:
            True if approved successfully
        """
        command = await self.get_command(command_id)
        if not command:
            logger.error(f"Cannot approve - command {command_id} not found")
            return False

        if not command.is_pending():
            logger.warning(
                f"Cannot approve - command {command_id} is not pending (state={command.state.value})"
            )
            return False

        command.approve(user_id, comment)
        return await self.update_command(command)

    async def deny_command(
        self, command_id: str, user_id: str, comment: Optional[str] = None
    ) -> bool:
        """
        Deny a pending command.

        Args:
            command_id: Command to deny
            user_id: User denying the command
            comment: Optional denial comment

        Returns:
            True if denied successfully
        """
        command = await self.get_command(command_id)
        if not command:
            logger.error(f"Cannot deny - command {command_id} not found")
            return False

        if not command.is_pending():
            logger.warning(
                f"Cannot deny - command {command_id} is not pending (state={command.state.value})"
            )
            return False

        command.deny(user_id, comment)
        return await self.update_command(command)

    async def start_execution(self, command_id: str) -> bool:
        """
        Mark command as executing.

        Args:
            command_id: Command to mark as executing

        Returns:
            True if marked successfully
        """
        command = await self.get_command(command_id)
        if not command:
            logger.error(f"Cannot start execution - command {command_id} not found")
            return False

        if not command.is_approved():
            logger.error(
                f"Cannot execute - command {command_id} is not approved (state={command.state.value})"
            )
            return False

        command.start_execution()
        return await self.update_command(command)

    async def complete_command(
        self, command_id: str, output: str, stderr: str = "", return_code: int = 0
    ) -> bool:
        """
        Mark command as completed with results.

        Args:
            command_id: Command to complete
            output: stdout output
            stderr: stderr output
            return_code: Command return code

        Returns:
            True if completed successfully
        """
        command = await self.get_command(command_id)
        if not command:
            logger.error(f"Cannot complete - command {command_id} not found")
            return False

        command.complete(output, stderr, return_code)
        return await self.update_command(command)


# Global singleton instance (thread-safe)
import threading

_command_queue: Optional[CommandExecutionQueue] = None
_command_queue_lock = threading.Lock()


def get_command_queue() -> CommandExecutionQueue:
    """Get global command queue instance (thread-safe)."""
    global _command_queue
    if _command_queue is None:
        with _command_queue_lock:
            # Double-check after acquiring lock
            if _command_queue is None:
                _command_queue = CommandExecutionQueue()
    return _command_queue
