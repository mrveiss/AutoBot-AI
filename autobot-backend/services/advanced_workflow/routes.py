# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Advanced Workflow API Routes

FastAPI router endpoints for advanced workflow operations.
"""

from fastapi import APIRouter, Depends, HTTPException, Request

from auth_middleware import check_admin_permission
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from autobot_shared.logging_manager import get_logger

from .coordinator import WorkflowCoordinator

logger = get_logger(__name__)

router = APIRouter(tags=["advanced_workflow"])

# Global instance (lazy initialized)
_coordinator: WorkflowCoordinator | None = None


async def get_orchestrator_instance(request: Request = None):
    """Get WorkflowCoordinator instance, preferring pre-initialized app.state."""
    global _coordinator

    # Try to use pre-initialized coordinator from app state first
    if request is not None:
        app_coordinator = getattr(request.app.state, "advanced_workflow_orchestrator", None)
        if app_coordinator is not None:
            logger.debug("Using pre-initialized WorkflowCoordinator from app.state")
            return app_coordinator

    # Try to use global instance
    if _coordinator is not None:
        logger.debug("Using global WorkflowCoordinator instance")
        return _coordinator

    # Create new instance as last resort
    logger.info("Creating new WorkflowCoordinator instance (expensive operation)")
    _coordinator = WorkflowCoordinator()

    # Cache in app state if request available
    if request is not None:
        request.app.state.advanced_workflow_orchestrator = _coordinator
        logger.info("Cached new WorkflowCoordinator in app.state for future requests")

    return _coordinator


@with_error_handling(category=ErrorCategory.SERVER_ERROR)
@router.post("/generate_intelligent")
async def generate_intelligent_workflow(
    request_data: dict,
    request: Request,
    admin_check: bool = Depends(check_admin_permission),
):
    """Generate AI-optimized workflow from user request"""
    try:
        orchestrator = await get_orchestrator_instance(request)

        user_request = request_data.get("user_request", "")
        session_id = request_data.get("session_id", "")
        context = request_data.get("context", {})

        if not user_request or not session_id:
            raise HTTPException(status_code=400, detail="user_request and session_id required")

        workflow_id = await orchestrator.generate_intelligent_workflow(user_request, session_id, context)

        return {
            "success": True,
            "workflow_id": workflow_id,
            "message": "AI-optimized workflow generated successfully",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to generate intelligent workflow: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")


@with_error_handling(category=ErrorCategory.SERVER_ERROR)
@router.get("/intelligence/{workflow_id}")
async def get_workflow_intelligence(
    workflow_id: str,
    request: Request,
    admin_check: bool = Depends(check_admin_permission),
):
    """Get AI intelligence data for workflow"""
    try:
        orchestrator = await get_orchestrator_instance(request)

        if workflow_id not in orchestrator.workflow_intelligence:
            raise HTTPException(status_code=404, detail="Workflow intelligence not found")

        intelligence = orchestrator.workflow_intelligence[workflow_id]

        return {
            "success": True,
            "intelligence": {
                "workflow_id": intelligence.workflow_id,
                "estimated_completion_time": intelligence.estimated_completion_time,
                "confidence_score": intelligence.confidence_score,
                "optimization_suggestions": intelligence.optimization_suggestions,
                "risk_mitigation_strategies": intelligence.risk_mitigation_strategies,
            },
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get workflow intelligence: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")


@with_error_handling(category=ErrorCategory.SERVER_ERROR)
@router.get("/analytics")
async def get_advanced_analytics(
    request: Request,
    admin_check: bool = Depends(check_admin_permission),
):
    """Get advanced workflow analytics"""
    try:
        orchestrator = await get_orchestrator_instance(request)

        return {
            "success": True,
            "analytics": orchestrator.analytics,
            "learning_insights": {
                "total_patterns_learned": len(orchestrator.learning_model.learning_data["user_patterns"]),
                "optimization_effectiveness": orchestrator.learning_model.learning_data["optimization_effectiveness"],
                "top_intents": [
                    "installation",
                    "configuration",
                    "security",
                ],
                "success_rate_trend": "improving",
            },
        }

    except Exception as e:
        logger.error("Failed to get analytics: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")


@with_error_handling(category=ErrorCategory.SERVER_ERROR)
@router.get("/templates")
async def get_workflow_templates(
    request: Request,
    admin_check: bool = Depends(check_admin_permission),
):
    """Get all available intelligent workflow templates (Issue #372 - uses model methods)"""
    try:
        orchestrator = await get_orchestrator_instance(request)

        # Issue #372: Use model method to reduce feature envy
        templates = [template.to_summary_dict() for template in orchestrator.workflow_templates.values()]

        return {"success": True, "templates": templates, "total_count": len(templates)}

    except Exception as e:
        logger.error("Failed to get workflow templates: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")


@with_error_handling(category=ErrorCategory.SERVER_ERROR)
@router.post("/templates/{template_id}/execute")
async def execute_workflow_template(
    template_id: str,
    request_data: dict,
    request: Request,
    admin_check: bool = Depends(check_admin_permission),
):
    """Execute a workflow template with customizations"""
    try:
        orchestrator = await get_orchestrator_instance(request)

        if template_id not in orchestrator.workflow_templates:
            raise HTTPException(status_code=404, detail=f"Template {template_id} not found")

        session_id = request_data.get("session_id", "")
        customizations = request_data.get("customizations", {})

        if not session_id:
            raise HTTPException(status_code=400, detail="session_id required")

        # Generate workflow from template
        template = orchestrator.workflow_templates[template_id]
        user_request = f"Execute {template.name} workflow template"

        workflow_id = await orchestrator.generate_intelligent_workflow(
            user_request, session_id, {"template_id": template_id, **customizations}
        )

        return {
            "success": True,
            "workflow_id": workflow_id,
            "template_name": template.name,
            "message": f"Template '{template.name}' executed successfully",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to execute template %s: %s", template_id, e)
        raise HTTPException(status_code=500, detail="Internal server error")
