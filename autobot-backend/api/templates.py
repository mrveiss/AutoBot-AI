# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Workflow Templates API endpoints
Provides access to pre-configured workflow templates with intelligent caching

Route ordering: Static paths (/templates/search, /templates/categories,
/templates/stats) MUST be defined before parameterized paths
(/templates/{template_id}) to prevent FastAPI from capturing static
segments as path parameters.
"""

import logging
from typing import Dict, Optional

from auth_middleware import check_admin_permission
from autobot_types import TaskComplexity
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from utils.advanced_cache_manager import smart_cache
from workflow_templates import TemplateCategory, workflow_template_manager

from autobot_shared.error_boundaries import ErrorCategory, with_error_handling

logger = logging.getLogger(__name__)

router = APIRouter(
    dependencies=[Depends(check_admin_permission)],
)


class TemplateExecutionRequest(BaseModel):
    template_id: str
    variables: Optional[Dict[str, str]] = None
    auto_approve: bool = False


class TemplateValidationRequest(BaseModel):
    template_id: str
    variables: Dict[str, str]


def _generate_templates_cache_key(category, tags, complexity):
    """Generate cache key for template list"""
    key_parts = []
    if category:
        key_parts.append(f"cat:{category}")
    if tags:
        key_parts.append(f"tags:{tags}")
    if complexity:
        key_parts.append(f"comp:{complexity}")
    return "list:" + (":".join(key_parts) if key_parts else "all")


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_templates_root",
    error_code_prefix="TEMPLATES",
)
@router.get("/")
async def get_templates_root():
    """Root endpoint for templates API - redirects to /templates"""
    return {
        "message": "Templates API",
        "endpoints": {
            "list_templates": "/api/templates/templates",
            "get_template": "/api/templates/templates/{template_id}",
            "search_templates": "/api/templates/templates/search",
            "categories": "/api/templates/templates/categories",
            "stats": "/api/templates/templates/stats",
        },
    }


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="list_workflow_templates",
    error_code_prefix="TEMPLATES",
)
@router.get("/templates")
@smart_cache(
    data_type="templates",
    key_func=lambda category=None, tags=None, complexity=None: _generate_templates_cache_key(
        category, tags, complexity
    ),
)
async def list_workflow_templates(
    category: Optional[str] = Query(None, description="Filter by template category"),
    tags: Optional[str] = Query(None, description="Filter by tags (comma-separated)"),
    complexity: Optional[str] = Query(None, description="Filter by complexity level"),
):
    """List all available workflow templates with optional filtering"""
    try:
        templates = []

        # Apply category filter
        category_filter = None
        if category:
            try:
                category_filter = TemplateCategory(category.lower())
            except ValueError:
                raise HTTPException(
                    status_code=400, detail=f"Invalid category: {category}"
                )

        # Apply tags filter
        tags_filter = None
        if tags:
            tags_filter = [tag.strip() for tag in tags.split(",")]

        # Get filtered templates
        if category_filter or tags_filter:
            template_list = workflow_template_manager.list_templates(
                category=category_filter, tags=tags_filter
            )
        else:
            template_list = workflow_template_manager.list_templates()

        # Apply complexity filter
        if complexity:
            try:
                complexity_filter = TaskComplexity(complexity.lower())
                template_list = [
                    t for t in template_list if t.complexity == complexity_filter
                ]
            except ValueError:
                raise HTTPException(
                    status_code=400, detail=f"Invalid complexity: {complexity}"
                )

        # Convert to response format using model method (Issue #372 - reduces feature envy)
        templates = [template.to_summary_dict() for template in template_list]

        return {"success": True, "templates": templates, "total": len(templates)}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to list templates: {str(e)}"
        )


# --- Static paths MUST be registered before /templates/{template_id} ---


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_secrets_usage",
    error_code_prefix="TEMPLATES",
)
@router.get("/templates/secrets-usage")
async def get_secrets_usage():
    """Map secret keys to the templates that require them (#1415)."""
    try:
        all_templates = workflow_template_manager.list_templates()
        usage_map: Dict[str, list] = {}
        for template in all_templates:
            for secret_key, meta in (template.required_secrets or {}).items():
                if secret_key not in usage_map:
                    usage_map[secret_key] = []
                usage_map[secret_key].append(
                    {
                        "template_id": template.id,
                        "template_name": template.name,
                        "required": meta.get("required", True),
                        "scope": meta.get("scope", ""),
                    }
                )
        return {"success": True, "secrets_usage": usage_map}
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get secrets usage: {str(e)}",
        )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="search_templates",
    error_code_prefix="TEMPLATES",
)
@router.get("/templates/search")
async def search_templates(
    q: str = Query(
        ..., description="Search query for template name, description, or tags"
    )
):
    """Search workflow templates by query string (Issue #372 - uses model methods)"""
    try:
        templates = workflow_template_manager.search_templates(q)

        # Issue #372: Use model method to reduce feature envy
        search_results = [template.to_summary_dict() for template in templates]

        return {
            "success": True,
            "query": q,
            "results": search_results,
            "total": len(search_results),
        }

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to search templates: {str(e)}"
        )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="list_template_categories",
    error_code_prefix="TEMPLATES",
)
@router.get("/templates/categories")
async def list_template_categories():
    """List all available template categories"""
    try:
        categories = []
        for category in TemplateCategory:
            # Count templates in each category
            template_count = len(
                workflow_template_manager.list_templates(category=category)
            )
            categories.append(
                {
                    "name": category.value,
                    "display_name": category.value.replace("_", " ").title(),
                    "template_count": template_count,
                }
            )

        return {"success": True, "categories": categories}

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to list categories: {str(e)}"
        )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_template_statistics",
    error_code_prefix="TEMPLATES",
)
@router.get("/templates/stats")
async def get_template_statistics():
    """Get statistics about available templates"""
    try:
        all_templates = workflow_template_manager.list_templates()

        # Category statistics
        category_stats = {}
        for category in TemplateCategory:
            category_stats[category.value] = len(
                workflow_template_manager.list_templates(category=category)
            )

        # Complexity statistics
        complexity_stats = {}
        for complexity in TaskComplexity:
            complexity_stats[complexity.value] = len(
                workflow_template_manager.get_templates_by_complexity(complexity)
            )

        # Agent usage statistics
        agent_usage = {}
        for template in all_templates:
            for agent in template.agents_involved:
                agent_usage[agent] = agent_usage.get(agent, 0) + 1

        # Duration statistics
        durations = [t.estimated_duration_minutes for t in all_templates]
        avg_duration = sum(durations) / len(durations) if durations else 0

        return {
            "success": True,
            "statistics": {
                "total_templates": len(all_templates),
                "category_breakdown": category_stats,
                "complexity_breakdown": complexity_stats,
                "agent_usage": agent_usage,
                "average_duration_minutes": round(avg_duration, 1),
                "duration_range": {
                    "min": min(durations) if durations else 0,
                    "max": max(durations) if durations else 0,
                },
            },
        }

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to get template statistics: {str(e)}"
        )


# --- Parameterized paths below (after all static paths) ---


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_template_details",
    error_code_prefix="TEMPLATES",
)
@router.get("/templates/{template_id}")
@smart_cache(
    data_type="templates", key_func=lambda template_id: f"detail:{template_id}"
)
async def get_template_details(template_id: str):
    """Get detailed information about a specific template (Issue #372 - uses model methods)"""
    try:
        template = workflow_template_manager.get_template(template_id)
        if not template:
            raise HTTPException(status_code=404, detail="Template not found")

        # Issue #372: Use model method to reduce feature envy
        return {
            "success": True,
            "template": template.to_detail_dict(),
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get template: {str(e)}")


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="preview_template_workflow",
    error_code_prefix="TEMPLATES",
)
@router.get("/templates/{template_id}/preview")
async def preview_template_workflow(
    template_id: str,
    variables: Optional[str] = Query(None, description="Variables as JSON string"),
):
    """Preview what a template workflow would look like with given variables"""
    try:
        template = workflow_template_manager.get_template(template_id)
        if not template:
            raise HTTPException(status_code=404, detail="Template not found")

        # Parse variables if provided
        template_variables = {}
        if variables:
            import json

            try:
                template_variables = json.loads(variables)
            except json.JSONDecodeError:
                raise HTTPException(
                    status_code=400, detail="Invalid JSON in variables parameter"
                )

        # Create workflow preview
        workflow_data = workflow_template_manager.create_workflow_from_template(
            template_id, template_variables
        )

        if not workflow_data:
            raise HTTPException(
                status_code=500, detail="Failed to create workflow preview"
            )

        # Create preview steps
        preview_steps = []
        for i, step in enumerate(workflow_data["steps"], 1):
            preview_steps.append(f"{i}. {step['description']}")

        return {
            "success": True,
            "template_id": template_id,
            "template_name": workflow_data["template_name"],
            "description": workflow_data["description"],
            "estimated_duration_minutes": workflow_data["estimated_duration_minutes"],
            "agents_involved": workflow_data["agents_involved"],
            "workflow_preview": preview_steps,
            "variables_used": template_variables,
            "total_steps": len(workflow_data["steps"]),
            "approval_required_steps": sum(
                1 for step in workflow_data["steps"] if step["requires_approval"]
            ),
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to preview template: {str(e)}"
        )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="validate_template_variables",
    error_code_prefix="TEMPLATES",
)
@router.post("/templates/{template_id}/validate")
async def validate_template_variables(
    template_id: str, request: TemplateValidationRequest
):
    """Validate variables for a template before execution"""
    try:
        validation_result = workflow_template_manager.validate_template_variables(
            template_id, request.variables
        )

        return {
            "success": True,
            "template_id": template_id,
            "validation": validation_result,
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to validate template variables: {str(e)}",
        )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="create_workflow_from_template",
    error_code_prefix="TEMPLATES",
)
@router.post("/templates/{template_id}/create-workflow")
async def create_workflow_from_template(
    template_id: str, request: TemplateExecutionRequest
):
    """Create a workflow instance from a template"""
    try:
        # Validate template exists
        template = workflow_template_manager.get_template(template_id)
        if not template:
            raise HTTPException(status_code=404, detail="Template not found")

        # Validate variables if provided
        if request.variables:
            validation = workflow_template_manager.validate_template_variables(
                template_id, request.variables
            )
            if not validation["valid"]:
                return {
                    "success": False,
                    "error": "Invalid template variables",
                    "validation": validation,
                }

        # Create workflow from template
        workflow_data = workflow_template_manager.create_workflow_from_template(
            template_id, request.variables
        )

        if not workflow_data:
            raise HTTPException(
                status_code=500, detail="Failed to create workflow from template"
            )

        return {
            "success": True,
            "workflow": workflow_data,
            "ready_for_execution": True,
            "execution_endpoint": "/api/workflow/execute",
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to create workflow from template: {str(e)}",
        )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="execute_template_workflow",
    error_code_prefix="TEMPLATES",
)
@router.post("/templates/{template_id}/execute")
async def execute_template_workflow(
    template_id: str, request: TemplateExecutionRequest
):
    """Execute a workflow directly from a template (#1272).

    Creates a workflow via WorkflowAutomationManager so it
    appears in the Runner tab with step-by-step approval gates.
    """
    try:
        workflow_data = workflow_template_manager.create_workflow_from_template(
            template_id, request.variables
        )
        if not workflow_data:
            raise HTTPException(
                status_code=404,
                detail="Template not found or invalid",
            )

        from services.workflow_automation.routes import get_workflow_manager

        workflow_manager = get_workflow_manager()
        if workflow_manager is None:
            raise HTTPException(
                status_code=503,
                detail="Workflow automation unavailable",
            )

        wa_steps = _convert_template_steps(workflow_data["steps"])
        workflow_id = await _create_and_start_workflow(
            workflow_manager,
            workflow_data,
            wa_steps,
            request,
        )

        return {
            "success": True,
            "workflow_id": workflow_id,
            "template_info": {
                "template_id": template_id,
                "template_name": workflow_data["template_name"],
                "category": workflow_data["category"],
                "variables_used": workflow_data.get("variables_used", {}),
            },
            "message": (
                f"Workflow '{workflow_data['template_name']}' " f"created and started"
            ),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Failed to execute template %s: %s",
            template_id,
            e,
            exc_info=True,
        )
        raise HTTPException(
            status_code=500,
            detail=("Failed to execute template workflow: " f"{str(e)}"),
        )


def _convert_template_steps(steps):
    """Convert template step dicts to WorkflowStep objects (#1272)."""
    from services.workflow_automation.models import WorkflowStep as WAStep

    wa_steps = []
    for step in steps:
        wa_steps.append(
            WAStep(
                step_id=step["step_id"],
                command=step["action"],
                description=step["description"],
                explanation=(
                    f"Agent: {step['agent_type']} | "
                    f"Inputs: {step.get('inputs', {})}"
                ),
                requires_confirmation=step.get("requires_approval", True),
                risk_level="medium",
                estimated_duration=(step.get("expected_duration_ms", 30000) / 1000),
                dependencies=step.get("dependencies", []),
            )
        )
    return wa_steps


async def _create_and_start_workflow(
    manager,
    workflow_data,
    steps,
    request,
):
    """Create and auto-start a workflow (#1272)."""
    from services.workflow_automation.models import AutomationMode

    mode = (
        AutomationMode.AUTOMATIC
        if request.auto_approve
        else AutomationMode.SEMI_AUTOMATIC
    )
    workflow_id = await manager.create_automated_workflow(
        name=workflow_data["template_name"],
        description=workflow_data.get("description", ""),
        steps=steps,
        session_id="template-execution",
        automation_mode=mode,
    )
    started = await manager.start_workflow_execution(workflow_id)
    logger.info(
        "Template executed as workflow %s (started=%s)",
        workflow_id,
        started,
    )
    return workflow_id
