# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Overseer WebSocket Handlers

Provides WebSocket endpoints for:
- Task decomposition and planning
- Step-by-step execution with streaming output
- Real-time progress updates to frontend
"""

import asyncio
import json
import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from src.agents.overseer import (
    OverseerAgent,
    OverseerUpdate,
    StepExecutorAgent,
    StepResult,
    StreamChunk,
)

logger = logging.getLogger(__name__)

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
            self.executor = StepExecutorAgent(self.session_id)

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
            await self.send_json({
                "type": "status",
                "status": "planning",
                "message": "Analyzing your request...",
            })

            plan = await self.overseer.analyze_query(query, context)

            # Send plan overview
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

            # Phase 3: Complete
            await self.send_json({
                "type": "status",
                "status": "complete",
                "message": "All steps completed.",
                "plan_id": plan.plan_id,
            })

        except Exception as e:
            logger.error("[OverseerWS] Query processing failed: %s", e)
            await self.send_json({
                "type": "error",
                "error": str(e),
                "message": "Failed to process query.",
            })

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
                await self.send_json({
                    "type": "error",
                    "error": "No query provided",
                })

        elif msg_type == "cancel":
            # TODO: Implement cancellation
            await self.send_json({
                "type": "status",
                "status": "cancelled",
                "message": "Execution cancelled.",
            })

        elif msg_type == "status":
            summary = self.overseer.get_plan_summary() if self.overseer else None
            await self.send_json({
                "type": "status",
                "status": "active" if self.overseer else "idle",
                "summary": summary,
            })

        else:
            await self.send_json({
                "type": "error",
                "error": f"Unknown message type: {msg_type}",
            })


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
async def submit_query(session_id: str, query: str, context: Optional[Dict] = None):
    """
    HTTP endpoint for submitting queries (non-WebSocket alternative).

    Returns immediately with plan_id. Use WebSocket for real-time updates.
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
async def get_status(session_id: str):
    """Get current overseer status for a session."""
    if session_id in _active_overseers:
        overseer = _active_overseers[session_id]
        return {
            "active": True,
            "summary": overseer.get_plan_summary(),
        }
    return {"active": False, "summary": None}
