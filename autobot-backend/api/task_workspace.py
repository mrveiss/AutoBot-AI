# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Task workspace info endpoint (GH#6471).

GET /api/tasks/{task_id}/workspace — returns the per-task git worktree
workspace information for the agent currently assigned to that task.
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.user_management.dependencies import get_db_session
from auth_middleware import get_current_user
from autobot_shared.logging_manager import get_logger
from models.heartbeat import AgentRuntimeState
from services.task_workspace import _SAFE_TASK_ID_RE

logger = get_logger(__name__)
router = APIRouter()


class TaskWorkspaceResponse(BaseModel):
    """Workspace info for a task (GH#6471)."""

    task_id: str
    agent_id: Optional[str]
    workspace_dir: Optional[str]
    branch: Optional[str]
    preview_url: Optional[str]


@router.get(
    "/tasks/{task_id}/workspace",
    response_model=TaskWorkspaceResponse,
    summary="Get workspace info for a task",
    tags=["task-workspace"],
)
async def get_task_workspace(
    task_id: str,
    session: AsyncSession = Depends(get_db_session),
    _user: dict = Depends(get_current_user),
) -> TaskWorkspaceResponse:
    """
    Return the git worktree workspace directory, branch, and preview URL
    for the agent currently running the given task (GH#6471).

    Requires authentication.  Returns 404 when no agent has an active workspace
    for this task.
    """
    if not _SAFE_TASK_ID_RE.match(task_id):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid task_id format",
        )

    result = await session.execute(select(AgentRuntimeState).where(AgentRuntimeState.current_task_id == task_id))
    state = result.scalar_one_or_none()

    if state is None or state.workspace_dir is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No active workspace found for task {task_id}",
        )

    branch = f"task-{task_id}"
    return TaskWorkspaceResponse(
        task_id=task_id,
        agent_id=state.agent_id,
        workspace_dir=state.workspace_dir,
        branch=branch,
        preview_url=state.preview_url,
    )
