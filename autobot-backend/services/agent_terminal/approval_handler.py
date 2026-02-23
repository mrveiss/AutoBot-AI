# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Agent Terminal Approval Handler

Manages command approval workflow and auto-approval rules.
"""

import asyncio
import logging
import time
from typing import Dict, Optional

from backend.services.command_approval_manager import CommandApprovalManager
from secure_command_executor import CommandRisk

from .models import AgentTerminalSession

logger = logging.getLogger(__name__)


class ApprovalHandler:
    """Manages command approval workflow"""

    def __init__(
        self,
        approval_manager: CommandApprovalManager,
        chat_history_manager=None,
        command_queue=None,
    ):
        """
        Initialize approval handler.

        Args:
            approval_manager: CommandApprovalManager instance
            chat_history_manager: ChatHistoryManager instance
            command_queue: Command execution queue
        """
        self.approval_manager = approval_manager
        self.chat_history_manager = chat_history_manager
        self.command_queue = command_queue
        self._approval_locks: Dict[str, asyncio.Lock] = {}
        self._approval_locks_lock = asyncio.Lock()

    async def _get_approval_lock(self, session_id: str) -> asyncio.Lock:
        """
        Get or create a per-session lock for approval operations.

        This prevents race conditions where concurrent approve/deny calls
        for the same session could both see pending_approval and execute.

        Args:
            session_id: Session identifier

        Returns:
            asyncio.Lock for this session
        """
        async with self._approval_locks_lock:
            if session_id not in self._approval_locks:
                self._approval_locks[session_id] = asyncio.Lock()
            return self._approval_locks[session_id]

    async def cleanup_approval_lock(self, session_id: str):
        """Clean up approval lock when session is closed."""
        async with self._approval_locks_lock:
            self._approval_locks.pop(session_id, None)

    def check_agent_permission(
        self, agent_role, command_risk: CommandRisk
    ) -> tuple[bool, str]:
        """
        Check if agent has permission to execute command at given risk level.

        Args:
            agent_role: Role of the agent
            command_risk: Risk level of the command

        Returns:
            Tuple of (allowed, reason)
        """
        return CommandApprovalManager.check_permission(
            agent_role=agent_role,
            command_risk=command_risk,
            permissions=self.approval_manager.agent_permissions,
        )

    def needs_approval(self, agent_role, command_risk: CommandRisk) -> bool:
        """
        Check if command needs user approval.

        In supervised mode: HIGH/CRITICAL/FORBIDDEN commands are allowed but ALWAYS require approval
        In normal mode: Only commands up to max_risk are allowed, HIGH+ require approval

        Args:
            agent_role: Role of the agent
            command_risk: Risk level of the command

        Returns:
            True if approval is required
        """
        return CommandApprovalManager.needs_approval(
            agent_role=agent_role,
            command_risk=command_risk,
            permissions=self.approval_manager.agent_permissions,
        )

    async def store_auto_approve_rule(
        self, user_id: str, command: str, risk_level: str
    ):
        """
        Store an auto-approve rule for future similar commands.

        Args:
            user_id: User who created the rule
            command: Command that was approved
            risk_level: Risk level of the command
        """
        await self.approval_manager.store_auto_approve_rule(
            user_id=user_id,
            command=command,
            risk_level=risk_level,
        )

    async def check_auto_approve_rules(
        self, user_id: str, command: str, risk_level: str
    ) -> bool:
        """
        Check if command matches any auto-approve rules.

        Args:
            user_id: User ID to check rules for
            command: Command to check
            risk_level: Risk level of the command

        Returns:
            True if command should be auto-approved
        """
        return await self.approval_manager.check_auto_approve_rules(
            user_id=user_id,
            command=command,
            risk_level=risk_level,
        )

    async def broadcast_approval_status(
        self,
        session: AgentTerminalSession,
        command: str,
        approved: bool,
        comment: Optional[str] = None,
        pre_approved: bool = False,
    ):
        """
        Broadcast approval status update to WebSocket clients. Ref: #1088.

        Status values: pre_approved (blue), approved (green), denied (red).
        """
        try:
            # Only broadcast if there's a linked conversation
            if not session.conversation_id:
                logger.debug("No conversation_id - skipping WebSocket broadcast")
                return

            # Determine status based on approval type
            if pre_approved:
                status = "pre_approved"
            elif approved:
                status = "approved"
            else:
                status = "denied"

            # IMPLEMENTED: Real-time WebSocket broadcasting via event_manager
            try:
                from event_manager import event_manager

                await event_manager.publish(
                    event_type="command_approval_status",
                    payload={
                        "conversation_id": session.conversation_id,
                        "terminal_session_id": session.session_id,
                        "command": command,
                        "status": status,
                        "approved": approved,
                        "comment": comment,
                        "pre_approved": pre_approved,
                    },
                )
                logger.info(
                    f"✅ Approval status broadcast sent: "
                    f"conversation_id={session.conversation_id}, "
                    f"status={status}, "
                    f"command={command}, "
                    f"comment={comment}"
                )
            except Exception as broadcast_error:
                logger.warning(
                    f"Failed to broadcast approval status (non-fatal): {broadcast_error}"
                )
                # Continue - don't fail the approval process if broadcast fails

        except Exception as e:
            logger.error("Error in approval status update: %s", e, exc_info=True)
            # Don't fail the approval process if broadcast fails

    async def _persist_chat_approval_update(
        self,
        session: AgentTerminalSession,
        command: str,
        approved: bool,
        user_id: Optional[str],
        comment: Optional[str],
    ) -> None:
        """Helper for update_chat_approval_status. Ref: #1088."""
        updated = await self.chat_history_manager.update_message_metadata(
            session_id=session.conversation_id,
            metadata_filter={
                "terminal_session_id": session.session_id,
                "requires_approval": True,
            },
            metadata_updates={
                "approval_status": "approved" if approved else "denied",
                "approval_comment": comment,
                f"{'approved' if approved else 'denied'}_by": user_id,
                f"{'approved' if approved else 'denied'}_at": time.time(),
            },
        )
        if updated:
            logger.info(
                f"✅ Updated chat message with {'approval' if approved else 'denial'} status: "
                f"session={session.conversation_id}, terminal_session={session.session_id}"
            )
        else:
            logger.warning(
                f"⚠️ Could not find chat message to update {'approval' if approved else 'denial'} status: "
                f"session={session.conversation_id}, terminal_session={session.session_id}"
            )
        status_text = (
            "✅ Command approved and executed" if approved else "❌ Command denied"
        )
        await self.chat_history_manager.add_message(
            session_id=session.conversation_id,
            role="system",
            text=f"{status_text}: `{command}`" + (f" - {comment}" if comment else ""),
            message_type="command_approval_response",
            metadata={
                "command": command,
                "terminal_session_id": session.session_id,
                "approval_status": "approved" if approved else "denied",
                f"{'approved' if approved else 'denied'}_by": user_id,
                f"{'approved' if approved else 'denied'}_at": time.time(),
            },
        )
        logger.info(
            f"✅ [CHAT MESSAGE] Added command_approval_response to chat history: "
            f"command={command}, status={'approved' if approved else 'denied'}"
        )

    async def update_chat_approval_status(
        self,
        session: AgentTerminalSession,
        command: str,
        approved: bool,
        user_id: Optional[str] = None,
        comment: Optional[str] = None,
    ):
        """Update chat message metadata to persist approval status. Ref: #1088."""
        if not session.conversation_id or not self.chat_history_manager:
            return
        try:
            await self._persist_chat_approval_update(
                session, command, approved, user_id, comment
            )
        except Exception as e:
            logger.error(
                f"Failed to update chat approval status (non-fatal): {e}", exc_info=True
            )

    async def update_command_queue_status(
        self,
        command_id: Optional[str],
        approved: bool,
        user_id: Optional[str] = None,
        comment: Optional[str] = None,
        output: str = "",
        stderr: str = "",
        return_code: int = 0,
    ):
        """Update command queue status after approval or denial. Ref: #1088."""
        if not command_id or not self.command_queue:
            return

        try:
            if approved:
                # Mark as approved and executing
                await self.command_queue.approve_command(
                    command_id=command_id,
                    user_id=user_id or "web_user",
                    comment=comment,
                )
                logger.info(
                    f"✅ [QUEUE] Command {command_id} approved in queue by {user_id or 'web_user'}"
                )

                # Mark execution start
                await self.command_queue.start_execution(command_id)
                logger.info(
                    f"✅ [QUEUE] Command {command_id} marked as EXECUTING in queue"
                )

                # Complete if output provided
                if output or stderr or return_code != 0:
                    await self.command_queue.complete_command(
                        command_id=command_id,
                        output=output,
                        stderr=stderr,
                        return_code=return_code,
                    )
                    logger.info(
                        f"✅ [QUEUE] Command {command_id} completed in queue: "
                        f"stdout={len(output)} chars, stderr={len(stderr)} chars, "
                        f"return_code={return_code}"
                    )
            else:
                # Deny command
                await self.command_queue.deny_command(
                    command_id=command_id,
                    user_id=user_id or "web_user",
                    comment=comment,
                )
                logger.info(
                    f"✅ [QUEUE] Command {command_id} denied in queue by {user_id or 'web_user'}"
                )

        except Exception as e:
            logger.error("Failed to update command queue status: %s", e, exc_info=True)
