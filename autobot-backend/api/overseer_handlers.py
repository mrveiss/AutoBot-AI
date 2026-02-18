# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Overseer WebSocket Handlers

Provides WebSocket endpoints for:
- Task decomposition and planning
- Step-by-step execution with streaming output
- Real-time progress updates to frontend
- Saving explanations to chat history
"""

import logging
from typing import Any, Dict, Optional

from agents.overseer import OverseerAgent, OverseerUpdate, StepExecutorAgent, StepResult
from agents.overseer.types import (
    CommandBreakdownPart,
    CommandExplanation,
    OutputExplanation,
    StepStatus,
)
from auth_middleware import get_current_user
from chat_history import ChatHistoryManager
from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)


def _dict_to_step_result(step_data: Dict[str, Any]) -> StepResult:
    """
    Convert a dictionary to a StepResult object.

    Issue #665: Extracted from handle_query to reduce function length and
    improve code reusability.

    Args:
        step_data: Dictionary containing step result data

    Returns:
        StepResult object populated from the dict
    """
    cmd_exp = None
    if step_data.get("command_explanation"):
        ce = step_data["command_explanation"]
        cmd_exp = CommandExplanation(
            summary=ce.get("summary", ""),
            breakdown=[
                CommandBreakdownPart(
                    part=p.get("part", ""),
                    explanation=p.get("explanation", ""),
                )
                for p in ce.get("breakdown", [])
            ],
        )

    out_exp = None
    if step_data.get("output_explanation"):
        oe = step_data["output_explanation"]
        out_exp = OutputExplanation(
            summary=oe.get("summary", ""),
            key_findings=oe.get("key_findings", []),
        )

    # Handle status with defensive error handling
    try:
        status = StepStatus(step_data.get("status", "completed"))
    except ValueError:
        logger.warning(
            "Invalid status '%s', defaulting to COMPLETED", step_data.get("status")
        )
        status = StepStatus.COMPLETED

    return StepResult(
        task_id=step_data.get("task_id", ""),
        step_number=step_data.get("step_number", 0),
        total_steps=step_data.get("total_steps", 0),
        status=status,
        command=step_data.get("command"),
        command_explanation=cmd_exp,
        output=step_data.get("output"),
        output_explanation=out_exp,
        return_code=step_data.get("return_code"),
        execution_time=step_data.get("execution_time", 0.0),
        error=step_data.get("error"),
        is_streaming=step_data.get("is_streaming", False),
        stream_complete=step_data.get("stream_complete", False),
    )


# Shared chat history manager
_chat_history_manager: Optional[ChatHistoryManager] = None


def _get_chat_history_manager() -> ChatHistoryManager:
    """Get or create chat history manager."""
    global _chat_history_manager
    if _chat_history_manager is None:
        _chat_history_manager = ChatHistoryManager()
    return _chat_history_manager


router = APIRouter(prefix="/api/overseer", tags=["overseer"])

# Active sessions (session_id -> OverseerAgent)
_active_overseers: Dict[str, OverseerAgent] = {}


class OverseerWebSocketHandler:
    """Handles WebSocket communication for Overseer Agent."""

    def __init__(self, websocket: WebSocket, session_id: str):
        """Initialize handler with websocket and session."""
        self.websocket = websocket
        self.session_id = session_id
        self.overseer: Optional[OverseerAgent] = None
        self.executor: Optional[StepExecutorAgent] = None
        self.chat_history = _get_chat_history_manager()

    async def connect(self) -> bool:
        """Accept WebSocket connection."""
        try:
            await self.websocket.accept()

            # Get or create overseer for this session
            if self.session_id in _active_overseers:
                self.overseer = _active_overseers[self.session_id]
            else:
                self.overseer = OverseerAgent(self.session_id)
                _active_overseers[self.session_id] = self.overseer

            # Create executor for this session
            # Pass session_id as both chat session and PTY session (they should match)
            self.executor = StepExecutorAgent(
                session_id=self.session_id,
                pty_session_id=self.session_id,  # PTY session uses same ID
            )

            logger.info("[OverseerWS] Connected: session=%s", self.session_id)
            return True

        except Exception as e:
            logger.error("[OverseerWS] Connection failed: %s", e)
            return False

    async def disconnect(self):
        """Clean up on disconnect."""
        logger.info("[OverseerWS] Disconnected: session=%s", self.session_id)
        # Keep overseer alive for reconnection

    async def send_update(self, update: OverseerUpdate):
        """Send an update to the frontend."""
        try:
            await self.websocket.send_json(update.to_dict())
        except Exception as e:
            logger.error("[OverseerWS] Failed to send update: %s", e)

    async def send_json(self, data: Dict[str, Any]):
        """Send raw JSON to frontend."""
        try:
            await self.websocket.send_json(data)
        except Exception as e:
            logger.error("[OverseerWS] Failed to send JSON: %s", e)

    async def save_plan_to_chat(self, plan) -> None:
        """Save execution plan to chat history."""
        try:
            # Format plan as a message
            steps_text = "\n".join(
                [
                    f"  {s.step_number}. {s.description}"
                    + (f"\n     $ {s.command}" if s.command else "")
                    for s in plan.steps
                ]
            )

            message_text = f"""📋 **Execution Plan**

{plan.analysis}

**Steps:**
{steps_text}
"""
            # Build plan object for frontend component rendering
            plan_data = {
                "plan_id": plan.plan_id,
                "analysis": plan.analysis,
                "steps": [
                    {
                        "step_number": s.step_number,
                        "description": s.description,
                        "command": s.command,
                    }
                    for s in plan.steps
                ],
            }

            await self.chat_history.add_message(
                sender="assistant",
                text=message_text,
                message_type="overseer_plan",
                session_id=self.session_id,
                metadata={
                    "plan": plan_data,  # Full plan object for OverseerPlanMessage component
                    "plan_id": plan.plan_id,
                    "total_steps": len(plan.steps),
                },
            )
            logger.info("[OverseerWS] Saved plan to chat: %s", plan.plan_id)
        except Exception as e:
            logger.error("[OverseerWS] Failed to save plan to chat: %s", e)

    async def save_step_result_to_chat(self, result: StepResult) -> None:
        """Save step result with explanations to chat history."""
        try:
            # Build command explanation text for display
            cmd_explanation = ""
            if result.command_explanation:
                breakdown_text = "\n".join(
                    [
                        f"  • `{p['part']}`: {p['explanation']}"
                        for p in (
                            result.to_dict()
                            .get("command_explanation", {})
                            .get("breakdown", [])
                        )
                    ]
                )
                cmd_explanation = f"""
📖 **What this command does:**
{result.command_explanation.summary}

{breakdown_text}
"""

            # Build output explanation text for display
            output_explanation = ""
            if result.output_explanation:
                findings_text = "\n".join(
                    [f"  • {f}" for f in result.output_explanation.key_findings]
                )
                output_explanation = f"""
📊 **What we found:**
{result.output_explanation.summary}

{findings_text}
"""

            message_text = f"""📌 **Step {result.step_number}/{result.total_steps}**

**Command:** `{result.command or 'N/A'}`
{cmd_explanation}
{output_explanation}
"""
            # Include full step object in metadata for frontend component rendering
            step_data = result.to_dict()
            step_data[
                "description"
            ] = f"Step {result.step_number}: {result.command or 'N/A'}"

            await self.chat_history.add_message(
                sender="assistant",
                text=message_text,
                message_type="overseer_step",
                session_id=self.session_id,
                metadata={
                    "step": step_data,  # Full step object for OverseerStepMessage component
                    "step_number": result.step_number,
                    "total_steps": result.total_steps,
                    "status": result.status.value,
                    "command": result.command,
                    "return_code": result.return_code,
                },
            )
            logger.info(
                "[OverseerWS] Saved step %d result to chat",
                result.step_number,
            )
        except Exception as e:
            logger.error("[OverseerWS] Failed to save step to chat: %s", e)

    async def handle_query(self, query: str, context: Optional[Dict] = None):
        """
        Handle a user query through the overseer.

        Args:
            query: The user's question or request
            context: Optional conversation context
        """
        logger.info("[OverseerWS] Processing query: %s", query[:100])

        try:
            # Phase 1: Analyze and create plan
            await self.send_json(
                {
                    "type": "status",
                    "status": "planning",
                    "message": "Analyzing your request...",
                }
            )

            plan = await self.overseer.analyze_query(query, context)

            # Save plan to chat history (so it appears in chat)
            await self.save_plan_to_chat(plan)

            # Send plan overview via WebSocket
            await self.send_update(
                OverseerUpdate(
                    update_type="plan",
                    plan_id=plan.plan_id,
                    total_steps=len(plan.steps),
                    content={
                        "analysis": plan.analysis,
                        "steps": [
                            {
                                "step_number": s.step_number,
                                "description": s.description,
                                "command": s.command,
                            }
                            for s in plan.steps
                        ],
                    },
                )
            )

            # Phase 2: Execute steps
            async for update in self.overseer.orchestrate_execution(
                plan, self.executor
            ):
                await self.send_update(update)

                # Save step results to chat history (Issue #665: uses helper)
                if update.update_type == "step_complete" and update.content:
                    if isinstance(update.content, dict):
                        result = _dict_to_step_result(update.content)
                        await self.save_step_result_to_chat(result)
                    elif isinstance(update.content, StepResult):
                        await self.save_step_result_to_chat(update.content)

            # Phase 3: Complete
            await self.send_json(
                {
                    "type": "status",
                    "status": "complete",
                    "message": "All steps completed.",
                    "plan_id": plan.plan_id,
                }
            )

        except Exception as e:
            logger.error("[OverseerWS] Query processing failed: %s", e)
            await self.send_json(
                {
                    "type": "error",
                    "error": str(e),
                    "message": "Failed to process query.",
                }
            )

    async def handle_message(self, data: Dict[str, Any]):
        """
        Handle incoming WebSocket message.

        Message types:
        - query: Process a new user query
        - cancel: Cancel current execution
        - status: Get current status
        """
        msg_type = data.get("type", "query")

        if msg_type == "query":
            query = data.get("query", "")
            context = data.get("context")
            if query:
                await self.handle_query(query, context)
            else:
                await self.send_json(
                    {
                        "type": "error",
                        "error": "No query provided",
                    }
                )

        elif msg_type == "cancel":
            # TODO: Implement cancellation
            await self.send_json(
                {
                    "type": "status",
                    "status": "cancelled",
                    "message": "Execution cancelled.",
                }
            )

        elif msg_type == "status":
            summary = self.overseer.get_plan_summary() if self.overseer else None
            await self.send_json(
                {
                    "type": "status",
                    "status": "active" if self.overseer else "idle",
                    "summary": summary,
                }
            )

        else:
            await self.send_json(
                {
                    "type": "error",
                    "error": f"Unknown message type: {msg_type}",
                }
            )


@router.websocket("/ws/{session_id}")
async def overseer_websocket(websocket: WebSocket, session_id: str):
    """
    WebSocket endpoint for Overseer Agent.

    Provides real-time task decomposition and execution with:
    - Streaming command output for long-running commands
    - Automatic command explanations (Part 1: what it does)
    - Automatic output explanations (Part 2: what we're looking at)
    """
    handler = OverseerWebSocketHandler(websocket, session_id)

    if not await handler.connect():
        return

    try:
        while True:
            # Receive message
            data = await websocket.receive_json()
            await handler.handle_message(data)

    except WebSocketDisconnect:
        await handler.disconnect()
    except Exception as e:
        logger.error("[OverseerWS] Error: %s", e)
        await handler.disconnect()


@router.post("/query/{session_id}")
async def submit_query(
    session_id: str,
    query: str,
    context: Optional[Dict] = None,
    current_user: dict = Depends(get_current_user),
):
    """
    HTTP endpoint for submitting queries (non-WebSocket alternative).

    Returns immediately with plan_id. Use WebSocket for real-time updates.

    Issue #744: Requires authenticated user.
    """
    try:
        # Get or create overseer
        if session_id in _active_overseers:
            overseer = _active_overseers[session_id]
        else:
            overseer = OverseerAgent(session_id)
            _active_overseers[session_id] = overseer

        # Create plan
        plan = await overseer.analyze_query(query, context)

        return {
            "success": True,
            "plan_id": plan.plan_id,
            "analysis": plan.analysis,
            "steps": [
                {
                    "step_number": s.step_number,
                    "description": s.description,
                    "command": s.command,
                }
                for s in plan.steps
            ],
            "message": "Plan created. Connect via WebSocket for execution.",
        }

    except Exception as e:
        logger.error("[OverseerAPI] Query failed: %s", e)
        return {"success": False, "error": str(e)}


@router.get("/status/{session_id}")
async def get_status(
    session_id: str,
    current_user: dict = Depends(get_current_user),
):
    """
    Get current overseer status for a session.

    Issue #744: Requires authenticated user.
    """
    if session_id in _active_overseers:
        overseer = _active_overseers[session_id]
        return {
            "active": True,
            "summary": overseer.get_plan_summary(),
        }
    return {"active": False, "summary": None}
