# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss

"""FastAPI router for Version Control System integrations."""

import logging
from typing import Any, Dict, List, Optional

from backend.integrations.base import IntegrationConfig, IntegrationHealth
from backend.integrations.version_control_integration import (
    BitbucketIntegration,
    GitLabIntegration,
)
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)
router = APIRouter(tags=["integrations-version-control"])


class ConnectionTestRequest(BaseModel):
    """Request model for testing VCS connection."""

    provider: str = Field(..., description="VCS provider (gitlab, bitbucket)")
    api_key: str = Field(..., description="API key or access token")
    settings: Dict[str, Any] = Field(
        default_factory=dict, description="Provider-specific settings"
    )


class ProviderInfo(BaseModel):
    """Information about a VCS provider."""

    id: str = Field(..., description="Provider identifier")
    name: str = Field(..., description="Provider display name")
    description: str = Field(..., description="Provider description")
    required_settings: List[str] = Field(
        default_factory=list, description="Required configuration settings"
    )
    optional_settings: List[str] = Field(
        default_factory=list, description="Optional configuration settings"
    )


SUPPORTED_PROVIDERS = {
    "gitlab": {
        "name": "GitLab",
        "description": "GitLab version control platform",
        "required_settings": ["api_key"],
        "optional_settings": ["base_url"],
    },
    "bitbucket": {
        "name": "Bitbucket",
        "description": "Bitbucket version control platform",
        "required_settings": ["api_key", "workspace"],
        "optional_settings": ["base_url", "auth_type", "username"],
    },
}


def _build_vcs_config(
    provider: str,
    api_key: str,
    base_url: str = None,
    workspace: str = None,
    username: str = None,
) -> IntegrationConfig:
    """Build IntegrationConfig for VCS provider.

    Helper for endpoint handlers (Issue #61).
    """
    extra: Dict[str, Any] = {}
    if workspace:
        extra["workspace"] = workspace

    return IntegrationConfig(
        name=provider,
        provider=provider,
        api_key=api_key,
        base_url=base_url,
        username=username,
        extra=extra,
    )


def _create_integration(provider: str, config: IntegrationConfig) -> Any:
    """Create integration instance for provider.

    Args:
        provider: Provider identifier
        config: Integration configuration

    Returns:
        Integration instance

    Helper for endpoint handlers (Issue #61).
    """
    if provider == "gitlab":
        return GitLabIntegration(config)
    elif provider == "bitbucket":
        return BitbucketIntegration(config)
    else:
        raise HTTPException(status_code=400, detail=f"Unsupported provider: {provider}")


@router.post("/test-connection", response_model=IntegrationHealth)
async def test_connection(request: ConnectionTestRequest) -> IntegrationHealth:
    """Test VCS provider connection.

    Args:
        request: Connection test request with credentials

    Returns:
        IntegrationHealth with connection status
    """
    try:
        config = IntegrationConfig(
            name=request.provider,
            provider=request.provider,
            api_key=request.api_key,
            base_url=request.settings.get("base_url"),
            username=request.settings.get("username"),
            extra={
                k: v
                for k, v in request.settings.items()
                if k not in ("base_url", "username")
            },
        )

        integration = _create_integration(request.provider, config)
        health = await integration.test_connection()

        logger.info("Connection test for %s: %s", request.provider, health.status)
        return health

    except Exception as e:
        logger.error("Connection test failed: %s", str(e))
        raise HTTPException(status_code=500, detail=f"Connection test failed: {str(e)}")


@router.get("/providers", response_model=List[ProviderInfo])
async def get_providers() -> List[ProviderInfo]:
    """Get list of supported VCS providers.

    Returns:
        List of provider information
    """
    providers = []
    for provider_id, info in SUPPORTED_PROVIDERS.items():
        providers.append(
            ProviderInfo(
                id=provider_id,
                name=info["name"],
                description=info["description"],
                required_settings=info["required_settings"],
                optional_settings=info["optional_settings"],
            )
        )
    return providers


@router.get("/{provider}/repositories")
async def list_repositories(
    provider: str,
    api_key: str = Query(..., description="API key or access token"),
    workspace: Optional[str] = Query(None, description="Workspace (Bitbucket)"),
    base_url: Optional[str] = Query(None, description="Custom API base URL"),
    search: Optional[str] = Query(None, description="Search filter"),
    visibility: Optional[str] = Query(None, description="Visibility filter"),
) -> Dict[str, Any]:
    """List repositories or projects.

    Args:
        provider: VCS provider identifier
        api_key: API key or access token
        workspace: Workspace name (required for Bitbucket)
        base_url: Custom API base URL
        search: Search filter
        visibility: Visibility filter (GitLab)

    Returns:
        Dictionary with repositories/projects list
    """
    try:
        config = _build_vcs_config(provider, api_key, base_url, workspace)
        integration = _create_integration(provider, config)

        params: Dict[str, Any] = {}
        if search:
            params["search"] = search
        if visibility:
            params["visibility"] = visibility

        action = "list_projects" if provider == "gitlab" else "list_repositories"
        result = await integration.execute_action(action, params)
        logger.info("Listed repositories for %s", provider)
        return result
    except Exception as e:
        logger.error("Failed to list repositories: %s", str(e))
        raise HTTPException(
            status_code=500, detail=f"Failed to list repositories: {str(e)}"
        )


@router.get("/{provider}/repositories/{repo_id}/branches")
async def list_branches(
    provider: str,
    repo_id: str,
    api_key: str = Query(..., description="API key or access token"),
    workspace: Optional[str] = Query(None, description="Workspace (Bitbucket)"),
    base_url: Optional[str] = Query(None, description="Custom API base URL"),
    search: Optional[str] = Query(None, description="Search filter"),
) -> Dict[str, Any]:
    """List branches for a repository.

    Args:
        provider: VCS provider identifier
        repo_id: Repository ID (GitLab) or slug (Bitbucket)
        api_key: API key or access token
        workspace: Workspace name (required for Bitbucket)
        base_url: Custom API base URL
        search: Search filter

    Returns:
        Dictionary with branches list
    """
    try:
        config = _build_vcs_config(provider, api_key, base_url, workspace)
        integration = _create_integration(provider, config)

        params: Dict[str, Any] = {}
        if provider == "gitlab":
            params["project_id"] = repo_id
        else:
            params["repo_slug"] = repo_id
        if search:
            params["search"] = search

        result = await integration.execute_action("list_branches", params)
        logger.info("Listed branches for %s/%s", provider, repo_id)
        return result
    except Exception as e:
        logger.error("Failed to list branches: %s", str(e))
        raise HTTPException(
            status_code=500, detail=f"Failed to list branches: {str(e)}"
        )


def _build_pr_params(
    provider: str,
    repo_id: str,
    state: str = None,
    scope: str = None,
) -> tuple:
    """Build PR/MR query action and params.

    Helper for list_pull_requests (Issue #61).
    """
    params: Dict[str, Any] = {}
    if provider == "gitlab":
        params["project_id"] = repo_id
        if state:
            params["state"] = state
        if scope:
            params["scope"] = scope
        return "list_merge_requests", params
    else:
        params["repo_slug"] = repo_id
        if state:
            params["state"] = state.upper()
        return "list_pull_requests", params


@router.get("/{provider}/repositories/{repo_id}/pull-requests")
async def list_pull_requests(
    provider: str,
    repo_id: str,
    api_key: str = Query(..., description="API key or access token"),
    workspace: Optional[str] = Query(None, description="Workspace (Bitbucket)"),
    base_url: Optional[str] = Query(None, description="Custom API base URL"),
    state: Optional[str] = Query(None, description="State filter"),
    scope: Optional[str] = Query(None, description="Scope filter (GitLab)"),
) -> Dict[str, Any]:
    """List pull requests or merge requests."""
    try:
        config = _build_vcs_config(provider, api_key, base_url, workspace)
        integration = _create_integration(provider, config)
        action, params = _build_pr_params(provider, repo_id, state, scope)
        result = await integration.execute_action(action, params)
        logger.info("Listed PRs/MRs for %s/%s", provider, repo_id)
        return result
    except Exception as e:
        logger.error("Failed to list pull requests: %s", str(e))
        raise HTTPException(
            status_code=500, detail=f"Failed to list pull requests: {str(e)}"
        )


@router.get("/{provider}/repositories/{repo_id}/commits")
async def get_commit_info(
    provider: str,
    repo_id: str,
    commit_hash: str = Query(..., description="Commit hash or SHA"),
    api_key: str = Query(..., description="API key or access token"),
    workspace: Optional[str] = Query(None, description="Workspace (Bitbucket)"),
    base_url: Optional[str] = Query(None, description="Custom API base URL"),
) -> Dict[str, Any]:
    """Get commit information."""
    try:
        config = _build_vcs_config(provider, api_key, base_url, workspace)
        integration = _create_integration(provider, config)

        params: Dict[str, Any] = {}
        if provider == "gitlab":
            params["project_id"] = repo_id
            params["commit_sha"] = commit_hash
        else:
            params["repo_slug"] = repo_id
            params["commit_hash"] = commit_hash

        result = await integration.execute_action("get_commit_info", params)
        logger.info("Retrieved commit for %s/%s@%s", provider, repo_id, commit_hash)
        return result

    except Exception as e:
        logger.error("Failed to get commit info: %s", str(e))
        raise HTTPException(
            status_code=500, detail=f"Failed to get commit info: {str(e)}"
        )
