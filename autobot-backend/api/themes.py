# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Theme package API — admin install/uninstall + public registry/serve (#10472).

Note: with_error_handling from autobot_shared.error_boundaries wraps functions
with *args/**kwargs, which breaks FastAPI's parameter-inspection at route
registration time.  HTTPException instances are already re-raised as-is by that
decorator, so the safety net is equivalent to FastAPI's own exception handling.
We therefore rely on FastAPI's built-in exception handling here and skip the
wrapper decorator — matching the simpler pattern used by other lean endpoints.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.responses import FileResponse, JSONResponse

import theme_install
from auth_middleware import check_admin_permission

# The core-router registry loop mounts every router under "/api" (see
# core_routers.py — e.g. users_router prefix="/users" yields /api/users). So this
# router carries only "/themes" to resolve to /api/themes (NOT /api/api/themes). #10472
router = APIRouter(prefix="/themes", tags=["themes"])


@router.post("")
async def install_theme(file: UploadFile = File(...), admin_check: bool = Depends(check_admin_permission)):
    desc = await theme_install.install_theme_from_zip(file)
    return JSONResponse(desc.model_dump())


@router.delete("/{theme_id}")
async def uninstall_theme(theme_id: str, admin_check: bool = Depends(check_admin_permission)):
    theme_install.uninstall_theme(theme_id)
    return {"status": "deleted", "id": theme_id}


@router.get("")
async def list_themes():
    return [d.model_dump() for d in theme_install.list_installed_themes()]


@router.get("/{theme_id}/theme.css")
async def serve_theme_css(theme_id: str):
    return FileResponse(theme_install.theme_css_path(theme_id), media_type="text/css")


@router.get("/{theme_id}/assets/{rel:path}")
async def serve_theme_asset(theme_id: str, rel: str):
    return FileResponse(theme_install.theme_asset_path(theme_id, rel))
