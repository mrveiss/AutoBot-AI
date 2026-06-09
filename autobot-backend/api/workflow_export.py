# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Workflow Export/Import/Share API (#2165)

FastAPI router for workflow export, import, and sharing endpoints.

Registered in feature_routers.py as:
    ("api.workflow_export", "/workflow-export", ["workflow-export"], "workflow_export")
"""

from fastapi import APIRouter, Depends, HTTPException

from api.schemas_workflows import (
    CloneWorkflowRequest,
    ImportWorkflowRequest,
    ShareWorkflowRequest,
    WorkflowExportResponse,
    WorkflowImportResponse,
    WorkflowListSharesResponse,
    WorkflowShareResponse,
    WorkflowUnshareResponse,
    WorkflowValidateImportResponse,
)
from auth_middleware import get_current_user
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from autobot_shared.logging_manager import get_logger
from services.workflow_automation.routes import get_workflow_manager
from services.workflow_serializer import WorkflowSerializer
from services.workflow_sharing_service import WorkflowSharingService

logger = get_logger(__name__)

router = APIRouter(tags=["workflow-export"])


# ---------------------------------------------------------------------------
# Dependency helpers
# ---------------------------------------------------------------------------


def _get_serializer() -> WorkflowSerializer:
    """Return a WorkflowSerializer backed by the global workflow manager."""
    return WorkflowSerializer(get_workflow_manager())


def _get_sharing_service() -> WorkflowSharingService:
    """Return a WorkflowSharingService backed by the global serializer."""
    return WorkflowSharingService(_get_serializer())


# ---------------------------------------------------------------------------
# Export endpoint
# ---------------------------------------------------------------------------


@router.get("/export/{workflow_id}", response_model=WorkflowExportResponse)
@with_error_handling(category=ErrorCategory.SERVER_ERROR)
async def export_workflow(
    workflow_id: str,
    current_user: dict = Depends(get_current_user),
    serializer: WorkflowSerializer = Depends(_get_serializer),
):
    """
    Export a workflow as a portable JSON document.

    Returns the full WorkflowExportFormat payload that can be saved to disk
    or passed to the import endpoint on another instance.
    """
    try:
        doc = await serializer.export_workflow(workflow_id)
        if doc is None:
            raise HTTPException(status_code=404, detail=f"Workflow '{workflow_id}' not found.")

        logger.info(
            "User %s exported workflow %s",
            current_user.get("user_id"),
            workflow_id,
        )
        return {"success": True, "export": doc.to_dict()}

    except HTTPException:
        raise
    except Exception as exc:
        logger.error("export_workflow failed for %s: %s", workflow_id, exc)
        raise HTTPException(status_code=500, detail="Internal server error")


# ---------------------------------------------------------------------------
# Validate endpoint
# ---------------------------------------------------------------------------


@router.post("/validate", response_model=WorkflowValidateImportResponse)
@with_error_handling(category=ErrorCategory.SERVER_ERROR)
async def validate_import(
    body: ImportWorkflowRequest,
    current_user: dict = Depends(get_current_user),
    serializer: WorkflowSerializer = Depends(_get_serializer),
):
    """
    Validate an export document without creating a workflow.

    Returns a list of issues.  An empty list means the document is safe to
    import.
    """
    try:
        issues = serializer.validate_import(body.export_document)
        return {"success": True, "valid": len(issues) == 0, "issues": issues}

    except Exception as exc:
        logger.error("validate_import failed: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error")


# ---------------------------------------------------------------------------
# Import endpoint
# ---------------------------------------------------------------------------


@router.post("/import", response_model=WorkflowImportResponse)
@with_error_handling(category=ErrorCategory.SERVER_ERROR)
async def import_workflow(
    body: ImportWorkflowRequest,
    current_user: dict = Depends(get_current_user),
    serializer: WorkflowSerializer = Depends(_get_serializer),
):
    """
    Import a workflow from an export document and create it under the requesting user.
    """
    try:
        owner_id = current_user.get("user_id")
        new_id = await serializer.import_workflow(
            data=body.export_document,
            owner_id=owner_id,
            session_id=body.session_id,
        )
        if new_id is None:
            issues = serializer.validate_import(body.export_document)
            raise HTTPException(
                status_code=422,
                detail={"message": "Import validation failed.", "issues": issues},
            )

        logger.info("User %s imported workflow as %s", owner_id, new_id)
        return {"success": True, "workflow_id": new_id}

    except HTTPException:
        raise
    except Exception as exc:
        logger.error("import_workflow failed: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error")


# ---------------------------------------------------------------------------
# Share endpoints
# ---------------------------------------------------------------------------


@router.post("/share", response_model=WorkflowShareResponse)
@with_error_handling(category=ErrorCategory.SERVER_ERROR)
async def share_workflow(
    body: ShareWorkflowRequest,
    current_user: dict = Depends(get_current_user),
    sharing: WorkflowSharingService = Depends(_get_sharing_service),
):
    """
    Share a workflow.  Returns a share_id that others can use to clone it.
    """
    try:
        owner_id = current_user.get("user_id")
        share_id = await sharing.share_workflow(
            workflow_id=body.workflow_id,
            owner_id=owner_id,
            target_user_id=body.target_user_id,
            public=body.public,
        )
        if share_id is None:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Could not share workflow.  Ensure the workflow exists and "
                    "that at least one of 'target_user_id' or 'public' is specified."
                ),
            )

        logger.info("User %s shared workflow %s as %s", owner_id, body.workflow_id, share_id)
        return {"success": True, "share_id": share_id}

    except HTTPException:
        raise
    except Exception as exc:
        logger.error("share_workflow failed: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.delete("/share/{share_id}", response_model=WorkflowUnshareResponse)
@with_error_handling(category=ErrorCategory.SERVER_ERROR)
async def unshare_workflow(
    share_id: str,
    current_user: dict = Depends(get_current_user),
    sharing: WorkflowSharingService = Depends(_get_sharing_service),
):
    """Revoke a workflow share."""
    try:
        deleted = await sharing.unshare_workflow(share_id)
        if not deleted:
            raise HTTPException(status_code=404, detail=f"Share '{share_id}' not found.")

        logger.info("User %s revoked share %s", current_user.get("user_id"), share_id)
        return {"success": True, "share_id": share_id}

    except HTTPException:
        raise
    except Exception as exc:
        logger.error("unshare_workflow failed for %s: %s", share_id, exc)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/shares", response_model=WorkflowListSharesResponse)
@with_error_handling(category=ErrorCategory.SERVER_ERROR)
async def list_shared_workflows(
    current_user: dict = Depends(get_current_user),
    sharing: WorkflowSharingService = Depends(_get_sharing_service),
):
    """
    List workflow shares visible to the requesting user.

    Returns shares that are public, targeted at the user, or owned by the user.
    The embedded workflow payload is omitted to keep the response lightweight.
    """
    try:
        user_id = current_user.get("user_id")
        shares = await sharing.list_shared(user_id=user_id)
        return {"success": True, "shares": shares, "total_count": len(shares)}

    except Exception as exc:
        logger.error("list_shared_workflows failed: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/share/{share_id}/clone", response_model=WorkflowImportResponse)
@with_error_handling(category=ErrorCategory.SERVER_ERROR)
async def clone_shared_workflow(
    share_id: str,
    body: CloneWorkflowRequest,
    current_user: dict = Depends(get_current_user),
    sharing: WorkflowSharingService = Depends(_get_sharing_service),
):
    """
    Clone a shared workflow into the requesting user's workspace.

    Creates a new independent workflow owned by the requesting user.
    """
    try:
        new_owner_id = current_user.get("user_id")
        new_id = await sharing.clone_workflow(
            share_id=share_id,
            new_owner_id=new_owner_id,
            session_id=body.session_id,
        )
        if new_id is None:
            raise HTTPException(
                status_code=404,
                detail=f"Share '{share_id}' not found or could not be imported.",
            )

        logger.info("User %s cloned share %s as workflow %s", new_owner_id, share_id, new_id)
        return {"success": True, "workflow_id": new_id}

    except HTTPException:
        raise
    except Exception as exc:
        logger.error("clone_shared_workflow failed for share %s: %s", share_id, exc)
        raise HTTPException(status_code=500, detail="Internal server error")
