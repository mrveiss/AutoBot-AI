# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Human-in-the-Loop Takeover Manager for AutoBot Phase 8
Provides interrupt/takeover capabilities for autonomous operations
"""

import asyncio
import logging
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set

from memory import EnhancedMemoryManager, TaskPriority

logger = logging.getLogger(__name__)

# Performance optimization: O(1) lookup for datetime field keys (Issue #326)
DATETIME_FIELD_KEYS = {"started_at", "ended_at"}


class TakeoverTrigger(Enum):
    """Types of takeover triggers"""

    MANUAL_REQUEST = "manual_request"
    CRITICAL_ERROR = "critical_error"
    SECURITY_CONCERN = "security_concern"
    USER_INTERVENTION_REQUIRED = "user_intervention_required"
    SYSTEM_OVERLOAD = "system_overload"
    APPROVAL_REQUIRED = "approval_required"
    TIMEOUT_EXCEEDED = "timeout_exceeded"


class TakeoverState(Enum):
    """Takeover session states"""

    REQUESTED = "requested"
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


@dataclass
class TakeoverRequest:
    """Takeover request data structure"""

    request_id: str
    trigger: TakeoverTrigger
    priority: TaskPriority
    requesting_agent: Optional[str]
    affected_tasks: List[str]
    reason: str
    context_data: Dict[str, Any]
    requested_at: datetime
    expires_at: Optional[datetime]
    auto_approve: bool = False


@dataclass
class TakeoverSession:
    """Active takeover session"""

    session_id: str
    request: TakeoverRequest
    state: TakeoverState
    human_operator: Optional[str]
    started_at: Optional[datetime]
    ended_at: Optional[datetime]
    actions_taken: List[Dict[str, Any]]
    system_snapshot: Dict[str, Any]
    resolution: Optional[str] = None


class TakeoverManager:
    """
    Manages human-in-the-loop takeover capabilities for autonomous operations
    """

    def __init__(self, memory_manager: Optional[EnhancedMemoryManager] = None):
        """Initialize takeover manager with memory and session tracking."""
        self.memory_manager = memory_manager or EnhancedMemoryManager()

        # Active state tracking
        self.pending_requests: Dict[str, TakeoverRequest] = {}
        self.active_sessions: Dict[str, TakeoverSession] = {}
        self.paused_tasks: Set[str] = set()

        # Callbacks and handlers
        self.trigger_handlers: Dict[TakeoverTrigger, List[Callable]] = {}
        self.state_change_callbacks: List[Callable] = []

        # Configuration
        self.max_concurrent_sessions = 5
        self.default_timeout = timedelta(minutes=30)
        self.auto_approve_triggers = {TakeoverTrigger.SYSTEM_OVERLOAD}

        logger.info("Takeover Manager initialized")

    def _create_takeover_request(
        self,
        request_id: str,
        trigger: TakeoverTrigger,
        reason: str,
        requesting_agent: Optional[str],
        affected_tasks: Optional[List[str]],
        priority: TaskPriority,
        context_data: Optional[Dict[str, Any]],
        timeout_minutes: Optional[int],
        auto_approve: bool,
    ) -> TakeoverRequest:
        """
        Create a TakeoverRequest object with computed fields.

        Issue #665: Extracted from request_takeover to reduce function length.

        Args:
            request_id: Unique request identifier
            trigger: Type of takeover trigger
            reason: Reason for takeover request
            requesting_agent: Agent requesting takeover
            affected_tasks: List of affected task IDs
            priority: Request priority
            context_data: Additional context
            timeout_minutes: Optional timeout override
            auto_approve: Whether to auto-approve

        Returns:
            Configured TakeoverRequest object
        """
        timeout = (
            timedelta(minutes=timeout_minutes)
            if timeout_minutes
            else self.default_timeout
        )
        expires_at = datetime.now() + timeout

        return TakeoverRequest(
            request_id=request_id,
            trigger=trigger,
            priority=priority,
            requesting_agent=requesting_agent,
            affected_tasks=affected_tasks or [],
            reason=reason,
            context_data=context_data or {},
            requested_at=datetime.now(),
            expires_at=expires_at,
            auto_approve=auto_approve or trigger in self.auto_approve_triggers,
        )

    def _record_takeover_in_memory(
        self,
        trigger: TakeoverTrigger,
        reason: str,
        priority: TaskPriority,
        requesting_agent: Optional[str],
        affected_tasks: Optional[List[str]],
    ) -> str:
        """
        Record takeover request in memory system.

        Issue #665: Extracted from request_takeover to reduce function length.

        Args:
            trigger: Type of takeover trigger
            reason: Reason for takeover request
            priority: Request priority
            requesting_agent: Agent requesting takeover
            affected_tasks: List of affected task IDs

        Returns:
            Task ID from memory system
        """
        task_id = self.memory_manager.create_task_record(
            task_name="Takeover Request",
            description=f"Human takeover requested: {reason}",
            priority=priority,
            agent_type="takeover_manager",
            inputs={
                "trigger": trigger.value,
                "reason": reason,
                "affected_tasks": affected_tasks,
                "requesting_agent": requesting_agent,
            },
        )
        self.memory_manager.start_task(task_id)
        return task_id

    def _is_critical_trigger(self, trigger: TakeoverTrigger) -> bool:
        """Check if trigger requires immediate task pause. Issue #620.

        Args:
            trigger: The takeover trigger type

        Returns:
            True if trigger is critical. Issue #620.
        """
        return trigger in {
            TakeoverTrigger.CRITICAL_ERROR,
            TakeoverTrigger.SECURITY_CONCERN,
        }

    async def _handle_post_request_actions(
        self, request: TakeoverRequest, request_id: str
    ) -> None:
        """Handle actions after takeover request is created. Issue #620.

        Args:
            request: The created takeover request
            request_id: Unique request identifier. Issue #620.
        """
        await self._execute_trigger_handlers(request)

        if self._is_critical_trigger(request.trigger):
            await self._pause_affected_tasks(request.affected_tasks)

        if request.auto_approve:
            await self._auto_approve_request(request_id)

        logger.info(
            "Takeover requested: %s - %s - %s",
            request_id,
            request.trigger.value,
            request.reason,
        )
        await self._notify_state_change("request_created", request_id)

    async def request_takeover(
        self,
        trigger: TakeoverTrigger,
        reason: str,
        requesting_agent: Optional[str] = None,
        affected_tasks: Optional[List[str]] = None,
        priority: TaskPriority = TaskPriority.HIGH,
        context_data: Optional[Dict[str, Any]] = None,
        timeout_minutes: Optional[int] = None,
        auto_approve: bool = False,
    ) -> str:
        """Request human takeover of autonomous operations. Issue #665, #620."""
        request_id = f"takeover_{int(time.time() * 1000)}"

        request = self._create_takeover_request(
            request_id,
            trigger,
            reason,
            requesting_agent,
            affected_tasks,
            priority,
            context_data,
            timeout_minutes,
            auto_approve,
        )

        self._record_takeover_in_memory(
            trigger, reason, priority, requesting_agent, affected_tasks
        )

        self.pending_requests[request_id] = request
        await self._handle_post_request_actions(request, request_id)

        return request_id

    async def _validate_takeover_request(self, request_id: str) -> TakeoverRequest:
        """Validate takeover request exists, not expired, and capacity available. Issue #620."""
        if request_id not in self.pending_requests:
            raise ValueError(f"Takeover request not found: {request_id}")

        request = self.pending_requests[request_id]

        if request.expires_at and datetime.now() > request.expires_at:
            await self._expire_request(request_id)
            raise ValueError(f"Takeover request has expired: {request_id}")

        if len(self.active_sessions) >= self.max_concurrent_sessions:
            raise RuntimeError("Maximum concurrent takeover sessions reached")

        return request

    async def _create_takeover_session(
        self, request_id: str, request: TakeoverRequest, human_operator: str
    ) -> TakeoverSession:
        """Create and register a new takeover session. Issue #620."""
        session_id = f"session_{request_id}_{int(time.time())}"
        system_snapshot = await self._capture_system_snapshot()

        session = TakeoverSession(
            session_id=session_id,
            request=request,
            state=TakeoverState.ACTIVE,
            human_operator=human_operator,
            started_at=datetime.now(),
            ended_at=None,
            actions_taken=[],
            system_snapshot=system_snapshot,
        )

        del self.pending_requests[request_id]
        self.active_sessions[session_id] = session
        return session

    async def approve_takeover(
        self,
        request_id: str,
        human_operator: str,
        takeover_scope: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Approve a takeover request and start session"""
        request = await self._validate_takeover_request(request_id)
        session = await self._create_takeover_session(
            request_id, request, human_operator
        )

        await self._pause_affected_tasks(request.affected_tasks)

        self.memory_manager.complete_task(
            self._get_task_id_for_request(request_id),
            outputs={
                "session_id": session.session_id,
                "human_operator": human_operator,
                "status": "approved_and_active",
            },
        )

        logger.info(
            f"Takeover approved and session started: {session.session_id} by {human_operator}"
        )
        await self._notify_state_change("session_started", session.session_id)

        return session.session_id

    async def execute_takeover_action(
        self, session_id: str, action_type: str, action_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Execute an action during takeover session"""

        if session_id not in self.active_sessions:
            raise ValueError(f"Active takeover session not found: {session_id}")

        session = self.active_sessions[session_id]

        if session.state != TakeoverState.ACTIVE:
            raise ValueError(f"Session is not active: {session.state.value}")

        # Record action
        action_record = {
            "timestamp": datetime.now().isoformat(),
            "action_type": action_type,
            "action_data": action_data,
            "operator": session.human_operator,
        }

        # Execute action based on type
        result = await self._execute_action(action_type, action_data, session)

        action_record["result"] = result
        session.actions_taken.append(action_record)

        logger.info(
            "Takeover action executed: %s in session %s", action_type, session_id
        )

        return result

    def _action_pause_task(self, action_data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle pause_task action (Issue #315)."""
        task_id = action_data.get("task_id")
        if task_id:
            self.paused_tasks.add(task_id)
            return {"status": "task_paused", "task_id": task_id}
        return {"status": "error", "reason": "No task_id provided"}

    def _action_resume_task(self, action_data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle resume_task action (Issue #315)."""
        task_id = action_data.get("task_id")
        if task_id and task_id in self.paused_tasks:
            self.paused_tasks.remove(task_id)
            return {"status": "task_resumed", "task_id": task_id}
        return {"status": "error", "reason": "Task not found or not paused"}

    def _action_modify_parameters(self, action_data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle modify_parameters action (Issue #315)."""
        parameter_changes = action_data.get("changes", {})
        return {"status": "parameters_modified", "changes": parameter_changes}

    def _action_approve_operation(self, action_data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle approve_operation action (Issue #315)."""
        operation_id = action_data.get("operation_id")
        return {"status": "operation_approved", "operation_id": operation_id}

    def _action_reject_operation(self, action_data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle reject_operation action (Issue #315)."""
        operation_id = action_data.get("operation_id")
        reason = action_data.get("reason", "Rejected by human operator")
        return {
            "status": "operation_rejected",
            "operation_id": operation_id,
            "reason": reason,
        }

    def _action_system_command(self, action_data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle system_command action (Issue #315)."""
        command = action_data.get("command")
        if self._is_safe_command(command):
            return {"status": "command_executed", "command": command}
        return {"status": "command_rejected", "reason": "Command not in safe list"}

    def _action_custom_script(self, action_data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle custom_script action (Issue #315)."""
        script_name = action_data.get("script_name")
        script_params = action_data.get("parameters", {})
        return {
            "status": "script_executed",
            "script": script_name,
            "parameters": script_params,
        }

    async def _execute_action(
        self, action_type: str, action_data: Dict[str, Any], session: TakeoverSession
    ) -> Dict[str, Any]:
        """Execute specific takeover actions (Issue #315 - dispatch table)."""
        action_handlers = {
            "pause_task": self._action_pause_task,
            "resume_task": self._action_resume_task,
            "modify_parameters": self._action_modify_parameters,
            "approve_operation": self._action_approve_operation,
            "reject_operation": self._action_reject_operation,
            "system_command": self._action_system_command,
            "custom_script": self._action_custom_script,
        }

        handler = action_handlers.get(action_type)
        if handler:
            return handler(action_data)

        return {"status": "unknown_action", "action_type": action_type}

    def _is_safe_command(self, command: str) -> bool:
        """Check if a command is safe for execution during takeover"""
        safe_commands = {
            "ps",
            "top",
            "htop",
            "d",
            "free",
            "uptime",
            "whoami",
            "pwd",
            "ls",
            "cat",
            "less",
            "head",
            "tail",
            "grep",
            "systemctl status",
            "docker ps",
            "docker logs",
        }

        # Check if command starts with any safe command
        return any(command.startswith(safe_cmd) for safe_cmd in safe_commands)

    async def pause_takeover_session(self, session_id: str) -> bool:
        """Pause an active takeover session"""
        if session_id not in self.active_sessions:
            return False

        session = self.active_sessions[session_id]
        if session.state == TakeoverState.ACTIVE:
            session.state = TakeoverState.PAUSED

            # Resume paused tasks temporarily
            await self._resume_affected_tasks(session.request.affected_tasks)

            logger.info("Takeover session paused: %s", session_id)
            await self._notify_state_change("session_paused", session_id)
            return True

        return False

    async def resume_takeover_session(self, session_id: str) -> bool:
        """Resume a paused takeover session"""
        if session_id not in self.active_sessions:
            return False

        session = self.active_sessions[session_id]
        if session.state == TakeoverState.PAUSED:
            session.state = TakeoverState.ACTIVE

            # Pause affected tasks again
            await self._pause_affected_tasks(session.request.affected_tasks)

            logger.info("Takeover session resumed: %s", session_id)
            await self._notify_state_change("session_resumed", session_id)
            return True

        return False

    async def complete_takeover_session(
        self, session_id: str, resolution: str, handback_notes: Optional[str] = None
    ) -> bool:
        """Complete a takeover session and return control to autonomous system"""

        if session_id not in self.active_sessions:
            return False

        session = self.active_sessions[session_id]
        session.state = TakeoverState.COMPLETED
        session.ended_at = datetime.now()
        session.resolution = resolution

        # Resume all paused tasks
        await self._resume_affected_tasks(session.request.affected_tasks)

        # Create completion record
        completion_data = {
            "session_id": session_id,
            "duration_minutes": (
                (session.ended_at - session.started_at).total_seconds() / 60
            ),
            "actions_count": len(session.actions_taken),
            "resolution": resolution,
            "handback_notes": handback_notes,
        }

        # Store in memory system
        completion_task_id = self.memory_manager.create_task_record(
            task_name="Takeover Session Completion",
            description=f"Takeover session completed: {resolution}",
            priority=session.request.priority,
            agent_type="takeover_manager",
            inputs={"session_id": session_id},
            metadata={"original_request": asdict(session.request)},
        )

        self.memory_manager.start_task(completion_task_id)
        self.memory_manager.complete_task(completion_task_id, outputs=completion_data)

        logger.info("Takeover session completed: %s - %s", session_id, resolution)

        # Notify state change
        await self._notify_state_change("session_completed", session_id)

        return True

    async def _pause_affected_tasks(self, task_ids: List[str]):
        """Pause specified autonomous tasks"""
        for task_id in task_ids:
            self.paused_tasks.add(task_id)
            # Here you would integrate with your task execution system
            # to actually pause the tasks

        if task_ids:
            logger.info("Paused %s autonomous tasks", len(task_ids))

    async def _resume_affected_tasks(self, task_ids: List[str]):
        """Resume specified autonomous tasks"""
        for task_id in task_ids:
            self.paused_tasks.discard(task_id)
            # Here you would integrate with your task execution system
            # to actually resume the tasks

        if task_ids:
            logger.info("Resumed %s autonomous tasks", len(task_ids))

    async def _capture_system_snapshot(self) -> Dict[str, Any]:
        """Capture current system state for takeover context"""
        import psutil

        try:
            snapshot = {
                "timestamp": datetime.now().isoformat(),
                "system_info": {
                    "cpu_percent": psutil.cpu_percent(),
                    "memory_percent": psutil.virtual_memory().percent,
                    "disk_usage": psutil.disk_usage("/").percent,
                    "load_average": (
                        psutil.getloadavg() if hasattr(psutil, "getloadavg") else None
                    ),
                },
                "active_processes": len(psutil.pids()),
                "paused_tasks_count": len(self.paused_tasks),
                "active_takeover_sessions": len(self.active_sessions),
            }

            return snapshot

        except Exception as e:
            logger.error("Failed to capture system snapshot: %s", e)
            return {"error": str(e), "timestamp": datetime.now().isoformat()}

    async def _execute_trigger_handlers(self, request: TakeoverRequest):
        """Execute registered handlers for takeover triggers"""
        handlers = self.trigger_handlers.get(request.trigger, [])

        for handler in handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(request)
                else:
                    handler(request)
            except Exception as e:
                logger.error("Trigger handler error: %s", e)

    async def _auto_approve_request(self, request_id: str):
        """Automatically approve a takeover request"""
        try:
            session_id = await self.approve_takeover(
                request_id, human_operator="system_auto_approval"
            )
            logger.info(
                "Auto-approved takeover request: %s -> %s", request_id, session_id
            )
        except Exception as e:
            logger.error("Auto-approval failed for %s: %s", request_id, e)

    async def _expire_request(self, request_id: str):
        """Handle expired takeover request"""
        if request_id in self.pending_requests:
            del self.pending_requests[request_id]

            # Complete the associated task as failed
            task_id = self._get_task_id_for_request(request_id)
            if task_id:
                self.memory_manager.fail_task(task_id, "Takeover request expired")

            logger.info("Takeover request expired: %s", request_id)
            await self._notify_state_change("request_expired", request_id)

    def _get_task_id_for_request(self, request_id: str) -> Optional[str]:
        """Get the memory task ID associated with a takeover request"""
        # This would need to be implemented based on how you store the mapping
        # For now, returning None as placeholder
        return None

    async def _notify_state_change(self, event_type: str, identifier: str):
        """Notify registered callbacks of state changes"""
        for callback in self.state_change_callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(event_type, identifier)
                else:
                    callback(event_type, identifier)
            except Exception as e:
                logger.error("State change callback error: %s", e)

    def register_trigger_handler(self, trigger: TakeoverTrigger, handler: Callable):
        """Register a handler for specific takeover triggers"""
        if trigger not in self.trigger_handlers:
            self.trigger_handlers[trigger] = []
        self.trigger_handlers[trigger].append(handler)

    def register_state_change_callback(self, callback: Callable):
        """Register a callback for takeover state changes"""
        self.state_change_callbacks.append(callback)

    def get_pending_requests(self) -> List[Dict[str, Any]]:
        """Get all pending takeover requests"""
        result = []
        for request in self.pending_requests.values():
            request_dict = asdict(request)
            # Convert enum to string for JSON serialization
            request_dict["trigger"] = request.trigger.value
            request_dict["priority"] = request.priority.value
            # Convert datetime to ISO string
            request_dict["requested_at"] = request.requested_at.isoformat()
            if request.expires_at:
                request_dict["expires_at"] = request.expires_at.isoformat()
            result.append(request_dict)
        return result

    def get_active_sessions(self) -> List[Dict[str, Any]]:
        """Get all active takeover sessions"""
        sessions = []
        for session in self.active_sessions.values():
            session_dict = asdict(session)
            # Convert datetime objects to ISO strings
            for key in DATETIME_FIELD_KEYS:
                if session_dict[key]:
                    session_dict[key] = session_dict[key].isoformat()
            sessions.append(session_dict)

        return sessions

    def get_system_status(self) -> Dict[str, Any]:
        """Get current takeover system status"""
        return {
            "pending_requests": len(self.pending_requests),
            "active_sessions": len(self.active_sessions),
            "paused_tasks": len(self.paused_tasks),
            "max_concurrent_sessions": self.max_concurrent_sessions,
            "default_timeout_minutes": int(self.default_timeout.total_seconds() / 60),
            "available_triggers": [trigger.value for trigger in TakeoverTrigger],
            "auto_approve_triggers": [
                trigger.value for trigger in self.auto_approve_triggers
            ],
        }


# Global instance
takeover_manager = TakeoverManager()
