# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss

"""CI/CD integration API endpoints."""

import logging
from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, HTTPException, Query
from integrations.base import IntegrationConfig
from integrations.cicd_integration import (
    CircleCIIntegration,
    GitLabCIIntegration,
    JenkinsIntegration,
)
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(tags=["integrations-cicd"])

CICDProvider = Literal["jenkins", "gitlab", "circleci"]


class ConnectionTestRequest(BaseModel):
    """Request model for testing CI/CD connection."""

    provider: CICDProvider = Field(..., description="CI/CD provider type")
    base_url: str = Field(..., description="Base URL of the CI/CD service")
    credentials: Dict[str, str] = Field(..., description="Authentication credentials")


class PipelineTriggerRequest(BaseModel):
    """Request model for triggering a pipeline."""

    confirm: bool = Field(
        False, description="Confirmation flag - must be true to trigger"
    )
    parameters: Dict[str, Any] = Field(
        default_factory=dict, description="Pipeline parameters"
    )


class ProviderInfo(BaseModel):
    """CI/CD provider information."""

    id: str = Field(..., description="Provider identifier")
    name: str = Field(..., description="Provider display name")
    description: str = Field(..., description="Provider description")
    auth_type: str = Field(..., description="Authentication type")


@router.post("/test-connection")
async def test_connection(request: ConnectionTestRequest) -> Dict[str, Any]:
    """Test connection to a CI/CD provider.

    Args:
        request: Connection test request with provider and credentials

    Returns:
        Connection health status

    Raises:
        HTTPException: If provider is unknown or test fails
    """
    try:
        integration = _create_integration(
            request.provider, request.base_url, request.credentials
        )
        health = await integration.test_connection()
        return {
            "status": health.status.value,
            "message": health.message,
            "details": health.details,
        }
    except Exception as e:
        logger.exception("Connection test failed for %s", request.provider)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/providers")
async def list_providers() -> List[ProviderInfo]:
    """List supported CI/CD providers.

    Returns:
        List of supported provider information
    """
    return [
        ProviderInfo(
            id="jenkins",
            name="Jenkins",
            description="Jenkins automation server",
            auth_type="basic",
        ),
        ProviderInfo(
            id="gitlab",
            name="GitLab CI",
            description="GitLab integrated CI/CD",
            auth_type="token",
        ),
        ProviderInfo(
            id="circleci",
            name="CircleCI",
            description="CircleCI continuous integration",
            auth_type="token",
        ),
    ]


@router.get("/{provider}/pipelines")
async def list_pipelines(
    provider: CICDProvider,
    base_url: str = Query(..., description="CI/CD service base URL"),
    credentials: str = Query(..., description="JSON-encoded credentials"),
    project_id: Optional[str] = Query(None, description="Project/job identifier"),
) -> Dict[str, Any]:
    """List pipelines or jobs for a provider.

    Args:
        provider: CI/CD provider type
        base_url: Base URL of the CI/CD service
        credentials: JSON-encoded authentication credentials
        project_id: Project or job identifier (provider-specific)

    Returns:
        List of pipelines/jobs

    Raises:
        HTTPException: If operation fails
    """
    try:
        import json

        creds = json.loads(credentials)
        integration = _create_integration(provider, base_url, creds)
        params = {}
        if project_id:
            params["project_id"] = (
                int(project_id) if project_id.isdigit() else project_id
            )
            params["project_slug"] = project_id

        if provider == "jenkins":
            return await integration.execute_action("list_jobs", params)
        return await integration.execute_action("list_pipelines", params)
    except Exception as e:
        logger.exception("Failed to list pipelines for %s", provider)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{provider}/pipelines/{pipeline_id}/status")
async def get_pipeline_status(
    provider: CICDProvider,
    pipeline_id: str,
    base_url: str = Query(..., description="CI/CD service base URL"),
    credentials: str = Query(..., description="JSON-encoded credentials"),
    job_name: Optional[str] = Query(None, description="Job name (Jenkins only)"),
    project_id: Optional[str] = Query(None, description="Project ID (GitLab only)"),
) -> Dict[str, Any]:
    """Get status of a specific pipeline.

    Args:
        provider: CI/CD provider type
        pipeline_id: Pipeline or build identifier
        base_url: Base URL of the CI/CD service
        credentials: JSON-encoded authentication credentials
        job_name: Job name for Jenkins
        project_id: Project ID for GitLab

    Returns:
        Pipeline status information

    Raises:
        HTTPException: If operation fails
    """
    try:
        import json

        creds = json.loads(credentials)
        integration = _create_integration(provider, base_url, creds)
        params = _build_status_params(provider, pipeline_id, job_name, project_id)
        action = _get_status_action(provider)
        return await integration.execute_action(action, params)
    except Exception as e:
        logger.exception(
            "Failed to get status for %s pipeline %s", provider, pipeline_id
        )
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{provider}/pipelines/{pipeline_id}/trigger")
async def trigger_pipeline(
    provider: CICDProvider,
    pipeline_id: str,
    request: PipelineTriggerRequest,
    base_url: str = Query(..., description="CI/CD service base URL"),
    credentials: str = Query(..., description="JSON-encoded credentials"),
    project_id: Optional[str] = Query(None, description="Project ID (GitLab only)"),
) -> Dict[str, Any]:
    """Trigger a pipeline or build.

    Args:
        provider: CI/CD provider type
        pipeline_id: Pipeline/job identifier or branch name
        request: Trigger request with confirmation
        base_url: Base URL of the CI/CD service
        credentials: JSON-encoded authentication credentials
        project_id: Project ID for GitLab

    Returns:
        Trigger confirmation

    Raises:
        HTTPException: If confirmation missing or operation fails
    """
    if not request.confirm:
        raise HTTPException(
            status_code=400, detail="Confirmation required to trigger pipeline"
        )
    try:
        import json

        creds = json.loads(credentials)
        integration = _create_integration(provider, base_url, creds)
        params = _build_trigger_params(
            provider, pipeline_id, project_id, request.parameters
        )
        return await integration.execute_action("trigger_pipeline", params)
    except Exception as e:
        logger.exception("Failed to trigger %s pipeline %s", provider, pipeline_id)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{provider}/pipelines/{pipeline_id}/logs")
async def get_pipeline_logs(
    provider: CICDProvider,
    pipeline_id: str,
    base_url: str = Query(..., description="CI/CD service base URL"),
    credentials: str = Query(..., description="JSON-encoded credentials"),
    job_name: Optional[str] = Query(None, description="Job name (Jenkins only)"),
) -> Dict[str, Any]:
    """Get logs for a pipeline or build.

    Args:
        provider: CI/CD provider type
        pipeline_id: Build or pipeline identifier
        base_url: Base URL of the CI/CD service
        credentials: JSON-encoded authentication credentials
        job_name: Job name for Jenkins

    Returns:
        Pipeline logs

    Raises:
        HTTPException: If provider doesn't support logs or operation fails
    """
    if provider != "jenkins":
        raise HTTPException(
            status_code=400,
            detail=f"Log retrieval not supported for {provider}",
        )
    try:
        import json

        creds = json.loads(credentials)
        integration = _create_integration(provider, base_url, creds)
        if not job_name:
            raise HTTPException(status_code=400, detail="job_name required for Jenkins")
        params = {"job_name": job_name, "build_number": int(pipeline_id)}
        return await integration.execute_action("get_build_log", params)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid build number")
    except Exception as e:
        logger.exception("Failed to get logs for %s build %s", provider, pipeline_id)
        raise HTTPException(status_code=500, detail=str(e))


def _create_integration(
    provider: CICDProvider, base_url: str, credentials: Dict[str, str]
):
    """Create integration instance.

    Helper for _create_integration (Issue #61).

    Args:
        provider: CI/CD provider type
        base_url: Service base URL
        credentials: Authentication credentials

    Returns:
        Integration instance

    Raises:
        ValueError: If provider unknown
    """
    config = IntegrationConfig(
        name=provider,
        provider=provider,
        base_url=base_url,
        username=credentials.get("username"),
        password=credentials.get("password"),
        token=(credentials.get("private_token") or credentials.get("circle_token")),
        api_key=credentials.get("api_key"),
    )
    if provider == "jenkins":
        return JenkinsIntegration(config)
    elif provider == "gitlab":
        return GitLabCIIntegration(config)
    elif provider == "circleci":
        return CircleCIIntegration(config)
    raise ValueError(f"Unknown provider: {provider}")


def _build_status_params(
    provider: CICDProvider,
    pipeline_id: str,
    job_name: Optional[str],
    project_id: Optional[str],
) -> Dict[str, Any]:
    """Build status query parameters.

    Helper for get_pipeline_status (Issue #61).

    Args:
        provider: CI/CD provider type
        pipeline_id: Pipeline/build identifier
        job_name: Job name for Jenkins
        project_id: Project ID for GitLab

    Returns:
        Parameters dictionary

    Raises:
        HTTPException: If required parameters missing
    """
    if provider == "jenkins":
        if not job_name:
            raise HTTPException(status_code=400, detail="job_name required for Jenkins")
        return {"job_name": job_name, "build_number": int(pipeline_id)}
    elif provider == "gitlab":
        if not project_id:
            raise HTTPException(
                status_code=400, detail="project_id required for GitLab"
            )
        return {"project_id": int(project_id), "pipeline_id": int(pipeline_id)}
    elif provider == "circleci":
        return {"workflow_id": pipeline_id}
    return {}


def _get_status_action(provider: CICDProvider) -> str:
    """Get status action name.

    Helper for get_pipeline_status (Issue #61).

    Args:
        provider: CI/CD provider type

    Returns:
        Action name for status query
    """
    if provider == "jenkins":
        return "get_build_status"
    elif provider == "gitlab":
        return "get_pipeline_status"
    return "get_workflow_status"


def _build_trigger_params(
    provider: CICDProvider,
    pipeline_id: str,
    project_id: Optional[str],
    parameters: Dict[str, Any],
) -> Dict[str, Any]:
    """Build trigger parameters.

    Helper for trigger_pipeline (Issue #61).

    Args:
        provider: CI/CD provider type
        pipeline_id: Pipeline/job/branch identifier
        project_id: Project ID for GitLab
        parameters: Additional parameters

    Returns:
        Trigger parameters dictionary

    Raises:
        HTTPException: If required parameters missing
    """
    if provider == "jenkins":
        return {"job_name": pipeline_id, "parameters": parameters}
    elif provider == "gitlab":
        if not project_id:
            raise HTTPException(
                status_code=400, detail="project_id required for GitLab"
            )
        return {"project_id": int(project_id), "ref": pipeline_id}
    elif provider == "circleci":
        return {"project_slug": project_id or pipeline_id, "branch": pipeline_id}
    return {}
