# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Advanced Workflow API Routes

FastAPI router endpoints for advanced workflow operations.
"""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Request

from autobot_shared.error_boundaries import ErrorCategory, with_error_handling

from .orchestrator import AdvancedWorkflowOrchestrator

logger = logging.getLogger(__name__)

router = APIRouter(tags=["advanced_workflow"])

# Global instance (lazy initialized)
_orchestrator: Optional[AdvancedWorkflowOrchestrator] = None


async def get_orchestrator_instance(request: Request = None):
    """Get orchestrator instance, preferring pre-initialized app.state"""
    global _orchestrator

    # Try to use pre-initialized orchestrator from app state first
    if request is not None:
        app_orchestrator = getattr(
            request.app.state, "advanced_workflow_orchestrator", None
        )
        if app_orchestrator is not None:
            logger.debug(
                "Using pre-initialized advanced workflow orchestrator from app.state"
            )
            return app_orchestrator

    # Try to use global instance
    if _orchestrator is not None:
        logger.debug("Using global advanced workflow orchestrator instance")
        return _orchestrator

    # Create new instance as last resort
    logger.info(
        "Creating new AdvancedWorkflowOrchestrator instance (expensive operation)"
    )
    _orchestrator = AdvancedWorkflowOrchestrator()

    # Cache in app state if request available
    if request is not None:
        request.app.state.advanced_workflow_orchestrator = _orchestrator
        logger.info("Cached new orchestrator in app.state for future requests")

    return _orchestrator


@with_error_handling(category=ErrorCategory.SERVER_ERROR)
@router.post("/generate_intelligent")
async def generate_intelligent_workflow(request_data: dict, request: Request):
    """Generate AI-optimized workflow from user request"""
    try:
        orchestrator = await get_orchestrator_instance(request)

        user_request = request_data.get("user_request", "")
        session_id = request_data.get("session_id", "")
        context = request_data.get("context", {})

        if not user_request or not session_id:
            raise HTTPException(
                status_code=400, detail="user_request and session_id required"
            )

        workflow_id = await orchestrator.generate_intelligent_workflow(
            user_request, session_id, context
        )

        return {
            "success": True,
            "workflow_id": workflow_id,
            "message": "AI-optimized workflow generated successfully",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to generate intelligent workflow: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@with_error_handling(category=ErrorCategory.SERVER_ERROR)
@router.get("/intelligence/{workflow_id}")
async def get_workflow_intelligence(workflow_id: str, request: Request):
    """Get AI intelligence data for workflow"""
    try:
        orchestrator = await get_orchestrator_instance(request)

        if workflow_id not in orchestrator.workflow_intelligence:
            raise HTTPException(
                status_code=404, detail="Workflow intelligence not found"
            )

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
        raise HTTPException(status_code=500, detail=str(e))


@with_error_handling(category=ErrorCategory.SERVER_ERROR)
@router.get("/analytics")
async def get_advanced_analytics(request: Request):
    """Get advanced workflow analytics"""
    try:
        orchestrator = await get_orchestrator_instance(request)

        return {
            "success": True,
            "analytics": orchestrator.analytics,
            "learning_insights": {
                "total_patterns_learned": len(
                    orchestrator.learning_model.learning_data["user_patterns"]
                ),
                "optimization_effectiveness": orchestrator.learning_model.learning_data[
                    "optimization_effectiveness"
                ],
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
        raise HTTPException(status_code=500, detail=str(e))


@with_error_handling(category=ErrorCategory.SERVER_ERROR)
@router.get("/templates")
async def get_workflow_templates(request: Request):
    """Get all available intelligent workflow templates (Issue #372 - uses model methods)"""
    try:
        orchestrator = await get_orchestrator_instance(request)

        # Issue #372: Use model method to reduce feature envy
        templates = [
            template.to_summary_dict()
            for template in orchestrator.workflow_templates.values()
        ]

        return {"success": True, "templates": templates, "total_count": len(templates)}

    except Exception as e:
        logger.error("Failed to get workflow templates: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@with_error_handling(category=ErrorCategory.SERVER_ERROR)
@router.post("/templates/{template_id}/execute")
async def execute_workflow_template(
    template_id: str, request_data: dict, request: Request
):
    """Execute a workflow template with customizations"""
    try:
        orchestrator = await get_orchestrator_instance(request)

        if template_id not in orchestrator.workflow_templates:
            raise HTTPException(
                status_code=404, detail=f"Template {template_id} not found"
            )

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
        raise HTTPException(status_code=500, detail=str(e))
