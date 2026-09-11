# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# autobot-backend/transcriber/routes/projects.py
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Project CRUD routes for the transcriber module."""

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response

from transcriber.database import Database
from transcriber.deps import DEFAULT_USER, authenticate, caller_can_access, caller_id_of, caller_is_admin, get_db
from transcriber.models import ProjectCreate, ProjectOut, ProjectUpdate

router = APIRouter(tags=["transcriber-projects"], dependencies=[Depends(authenticate)])


@router.post("/projects", response_model=ProjectOut, status_code=201)
async def create_project(body: ProjectCreate, request: Request, db: Database = Depends(get_db)):
    pid = await db.create_project(body.name, body.description, user_id=caller_id_of(request))
    project = await db.get_project(pid)
    return ProjectOut(**project)


@router.get("/projects", response_model=list[ProjectOut])
async def list_projects(
    request: Request,
    db: Database = Depends(get_db),
    limit: int = Query(200, ge=1, le=1000),
    offset: int = Query(0, ge=0),
):
    rows = await db.list_projects(
        user_id=caller_id_of(request),
        also_owner=DEFAULT_USER if caller_is_admin(request) else None,
        limit=limit,
        offset=offset,
    )
    return [ProjectOut(**r) for r in rows]


@router.get("/projects/{project_id}", response_model=ProjectOut)
async def get_project(project_id: int, request: Request, db: Database = Depends(get_db)):
    project = await db.get_project(project_id)
    if not project or not caller_can_access(project, request):
        raise HTTPException(404, "Project not found")
    return ProjectOut(**project)


@router.patch("/projects/{project_id}", response_model=ProjectOut)
async def update_project(
    project_id: int,
    body: ProjectUpdate,
    request: Request,
    db: Database = Depends(get_db),
):
    project = await db.get_project(project_id)
    if not project or not caller_can_access(project, request):
        raise HTTPException(404, "Project not found")
    try:
        await db.update_project(project_id, body.name, body.description)
    except KeyError:
        raise HTTPException(404, "Project not found")
    return ProjectOut(**await db.get_project(project_id))


@router.delete("/projects/{project_id}", status_code=204)
async def delete_project(project_id: int, request: Request, db: Database = Depends(get_db)):
    project = await db.get_project(project_id)
    if not project or not caller_can_access(project, request):
        raise HTTPException(404, "Project not found")
    try:
        await db.delete_project(project_id)
    except KeyError:
        raise HTTPException(404, "Project not found")
    return Response(status_code=204)
