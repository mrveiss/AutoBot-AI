# autobot-backend/transcriber/routes/projects.py
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Project CRUD routes for the transcriber module."""
from fastapi import APIRouter, Depends, HTTPException, Response, Request

from transcriber.database import Database
from transcriber.deps import get_db
from transcriber.models import ProjectCreate, ProjectOut, ProjectUpdate

router = APIRouter(tags=["transcriber-projects"])

_DEFAULT_USER = "default"  # replaced by real auth in Plan 2


def _user_id(request: Request) -> str:
    user = getattr(request.state, "user", None)
    return user.id if user else _DEFAULT_USER


@router.post("/projects", response_model=ProjectOut, status_code=201)
async def create_project(body: ProjectCreate, request: Request, db: Database = Depends(get_db)):
    pid = await db.create_project(body.name, body.description, user_id=_user_id(request))
    project = await db.get_project(pid)
    return ProjectOut(**project)


@router.get("/projects", response_model=list[ProjectOut])
async def list_projects(request: Request, db: Database = Depends(get_db)):
    rows = await db.list_projects(user_id=_user_id(request))
    return [ProjectOut(**r) for r in rows]


@router.get("/projects/{project_id}", response_model=ProjectOut)
async def get_project(project_id: int, db: Database = Depends(get_db)):
    project = await db.get_project(project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    return ProjectOut(**project)


@router.patch("/projects/{project_id}", response_model=ProjectOut)
async def update_project(project_id: int, body: ProjectUpdate, db: Database = Depends(get_db)):
    if not await db.get_project(project_id):
        raise HTTPException(404, "Project not found")
    await db.update_project(project_id, body.name, body.description)
    return ProjectOut(**await db.get_project(project_id))


@router.delete("/projects/{project_id}", status_code=204)
async def delete_project(project_id: int, db: Database = Depends(get_db)):
    if not await db.get_project(project_id):
        raise HTTPException(404, "Project not found")
    await db.delete_project(project_id)
    return Response(status_code=204)
