# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Project Management Integration API (Issue #61)

REST API endpoints for interacting with project management platforms:
- Jira (Atlassian)
- Trello
- Asana

Provides connection testing, resource listing, and CRUD operations
for issues, cards, and tasks.
"""

from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, Query

from api.schemas_code import (
    PMIssueCreateResponse,
    PMIssueSearchResponse,
    PMIssuesResponse,
    PMIssueUpdateResponse,
    PMProjectsResponse,
)
from api.schemas_workflows import (
    ConnectionTestRequest,
    IssueCreateRequest,
    IssueUpdateRequest,
    ProviderInfo,
)
from auth_middleware import check_admin_permission
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from autobot_shared.logging_manager import get_logger
from integrations.base import IntegrationConfig, IntegrationHealth
from integrations.project_management_integration import (
    AsanaIntegration,
    JiraIntegration,
    TrelloIntegration,
)

logger = get_logger(__name__)

router = APIRouter(
    tags=["integrations-project-management"],
    dependencies=[Depends(check_admin_permission)],
)


# =============================================================================
# Request/Response Models
# =============================================================================


# =============================================================================
# Provider Configuration
# =============================================================================

SUPPORTED_PROVIDERS: Dict[str, ProviderInfo] = {
    "jira": ProviderInfo(
        provider="jira",
        name="Jira",
        description="Atlassian Jira issue tracking and project management",
        auth_type="basic",
        base_url_required=True,
        documentation_url="https://developer.atlassian.com/cloud/jira/",
    ),
    "trello": ProviderInfo(
        provider="trello",
        name="Trello",
        description="Visual board-based task management",
        auth_type="api_key_token",
        base_url_required=False,
        documentation_url="https://developer.atlassian.com/cloud/trello/",
    ),
    "asana": ProviderInfo(
        provider="asana",
        name="Asana",
        description="Team collaboration and task management",
        auth_type="bearer",
        base_url_required=False,
        documentation_url="https://developers.asana.com/docs",
    ),
}


# =============================================================================
# Helper Functions
# =============================================================================


def _get_integration(provider: str, config: IntegrationConfig):
    """Create integration instance for provider.

    Helper for _get_integration (Issue #61).
    """
    if provider == "jira":
        return JiraIntegration(config)
    elif provider == "trello":
        return TrelloIntegration(config)
    elif provider == "asana":
        return AsanaIntegration(config)
    else:
        raise HTTPException(status_code=400, detail=f"Unsupported provider: {provider}")


def _validate_provider(provider: str) -> None:
    """Validate that provider is supported.

    Helper for API endpoints (Issue #61).
    """
    if provider not in SUPPORTED_PROVIDERS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported provider: {provider}. " f"Supported: {list(SUPPORTED_PROVIDERS.keys())}",
        )


# =============================================================================
# API Endpoints
# =============================================================================


@router.post("/test-connection", response_model=IntegrationHealth)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="test_connection",
    error_code_prefix="INTEGRATION_PROJECT_MANAGEMENT",
)
async def test_connection(
    request: ConnectionTestRequest,
) -> IntegrationHealth:
    """Test connection to a project management provider.

    Validates credentials and returns connection health status.
    """
    _validate_provider(request.provider)

    config = IntegrationConfig(
        name=f"{request.provider}_integration",
        provider=request.provider,
        base_url=request.base_url,
        api_key=request.api_key,
        api_secret=request.api_secret,
        token=request.token,
        username=request.username,
        password=request.password,
    )

    integration = _get_integration(request.provider, config)
    health = await integration.test_connection()

    return health


@router.get("/providers", response_model=List[ProviderInfo])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="list_providers",
    error_code_prefix="INTEGRATION_PROJECT_MANAGEMENT",
)
async def list_providers() -> List[ProviderInfo]:
    """List all supported project management providers.

    Returns configuration requirements for each provider.
    """
    return list(SUPPORTED_PROVIDERS.values())


@router.get("/{provider}/projects", response_model=PMProjectsResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="list_projects",
    error_code_prefix="INTEGRATION_PROJECT_MANAGEMENT",
)
async def list_projects(
    provider: str,
    base_url: str | None = Query(None),
    api_key: str | None = Query(None),
    token: str | None = Query(None),
    username: str | None = Query(None),
    workspace_gid: str | None = Query(None),
) -> Dict[str, Any]:
    """List projects, boards, or workspaces.

    - Jira: Returns projects
    - Trello: Returns boards
    - Asana: Returns workspaces (or projects if workspace_gid provided)
    """
    _validate_provider(provider)

    config = IntegrationConfig(
        name=f"{provider}_integration",
        provider=provider,
        base_url=base_url,
        api_key=api_key,
        token=token,
        username=username,
    )

    integration = _get_integration(provider, config)

    if provider == "jira":
        return await integration.execute_action("list_projects", {})
    elif provider == "trello":
        return await integration.execute_action("list_boards", {})
    elif provider == "asana":
        if workspace_gid:
            return await integration.execute_action("list_projects", {"workspace_gid": workspace_gid})
        return await integration.execute_action("list_workspaces", {})


@router.get("/{provider}/issues", response_model=PMIssuesResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="list_issues",
    error_code_prefix="INTEGRATION_PROJECT_MANAGEMENT",
)
async def list_issues(
    provider: str,
    base_url: str | None = Query(None),
    api_key: str | None = Query(None),
    token: str | None = Query(None),
    username: str | None = Query(None),
    project_key: str | None = Query(None),
    list_id: str | None = Query(None),
    project_gid: str | None = Query(None),
    board_id: str | None = Query(None),
) -> Dict[str, Any]:
    """List issues, cards, or tasks.

    - Jira: Requires project_key
    - Trello: Requires list_id (or board_id to list lists first)
    - Asana: Requires project_gid
    """
    _validate_provider(provider)

    config = IntegrationConfig(
        name=f"{provider}_integration",
        provider=provider,
        base_url=base_url,
        api_key=api_key,
        token=token,
        username=username,
    )

    integration = _get_integration(provider, config)

    if provider == "jira":
        if not project_key:
            raise HTTPException(status_code=400, detail="project_key required for Jira")
        return await integration.execute_action("list_issues", {"project_key": project_key})
    elif provider == "trello":
        if board_id:
            return await integration.execute_action("list_lists", {"board_id": board_id})
        if not list_id:
            raise HTTPException(
                status_code=400,
                detail="list_id or board_id required for Trello",
            )
        return await integration.execute_action("list_cards", {"list_id": list_id})
    elif provider == "asana":
        if not project_gid:
            raise HTTPException(status_code=400, detail="project_gid required for Asana")
        return await integration.execute_action("list_tasks", {"project_gid": project_gid})


def _build_create_params(provider: str, request: IssueCreateRequest) -> tuple:
    """Build create action and params for provider.

    Helper for create_issue (Issue #61).

    Returns:
        Tuple of (action_name, params_dict)
    """
    if provider == "jira":
        if not request.project_key:
            raise HTTPException(status_code=400, detail="project_key required for Jira")
        params = {
            "project_key": request.project_key,
            "summary": request.title,
            "description": request.description or "",
            "issue_type": request.issue_type or "Task",
        }
        return "create_issue", params
    elif provider == "trello":
        if not request.list_id:
            raise HTTPException(status_code=400, detail="list_id required for Trello")
        params = {"list_id": request.list_id, "name": request.title}
        if request.description:
            params["description"] = request.description
        return "create_card", params
    else:  # asana
        if not request.workspace_gid:
            raise HTTPException(status_code=400, detail="workspace_gid required for Asana")
        params = {
            "workspace_gid": request.workspace_gid,
            "name": request.title,
        }
        if request.description:
            params["notes"] = request.description
        if request.project_key:
            params["project_gid"] = request.project_key
        return "create_task", params


@router.post("/{provider}/issues", response_model=PMIssueCreateResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="create_issue",
    error_code_prefix="INTEGRATION_PROJECT_MANAGEMENT",
)
async def create_issue(
    provider: str,
    request: IssueCreateRequest,
    base_url: str | None = Query(None),
    api_key: str | None = Query(None),
    token: str | None = Query(None),
    username: str | None = Query(None),
) -> Dict[str, Any]:
    """Create a new issue, card, or task."""
    _validate_provider(provider)

    config = IntegrationConfig(
        name=f"{provider}_integration",
        provider=provider,
        base_url=base_url,
        api_key=api_key,
        token=token,
        username=username,
    )

    integration = _get_integration(provider, config)
    action, params = _build_create_params(provider, request)
    return await integration.execute_action(action, params)


def _build_update_params(provider: str, issue_id: str, request: IssueUpdateRequest) -> tuple:
    """Build update action and params for provider.

    Helper for update_issue (Issue #61).

    Returns:
        Tuple of (action_name, params_dict)
    """
    if provider == "jira":
        if not request.transition_id:
            raise HTTPException(status_code=400, detail="transition_id required for Jira")
        return "update_issue_status", {
            "issue_key": issue_id,
            "transition_id": request.transition_id,
        }
    elif provider == "trello":
        if not request.list_id:
            raise HTTPException(status_code=400, detail="list_id required for Trello")
        return "move_card", {"card_id": issue_id, "list_id": request.list_id}
    else:  # asana
        params = {"task_gid": issue_id}
        if request.title:
            params["name"] = request.title
        if request.description:
            params["notes"] = request.description
        if request.completed is not None:
            params["completed"] = request.completed
        if len(params) == 1:
            raise HTTPException(status_code=400, detail="No update fields provided")
        return "update_task", params


@router.patch("/{provider}/issues/{issue_id}", response_model=PMIssueUpdateResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="update_issue",
    error_code_prefix="INTEGRATION_PROJECT_MANAGEMENT",
)
async def update_issue(
    provider: str,
    issue_id: str,
    request: IssueUpdateRequest,
    base_url: str | None = Query(None),
    api_key: str | None = Query(None),
    token: str | None = Query(None),
    username: str | None = Query(None),
) -> Dict[str, Any]:
    """Update an issue, card, or task."""
    _validate_provider(provider)

    config = IntegrationConfig(
        name=f"{provider}_integration",
        provider=provider,
        base_url=base_url,
        api_key=api_key,
        token=token,
        username=username,
    )

    integration = _get_integration(provider, config)
    action, params = _build_update_params(provider, issue_id, request)
    return await integration.execute_action(action, params)


@router.get("/{provider}/search", response_model=PMIssueSearchResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="search_issues",
    error_code_prefix="INTEGRATION_PROJECT_MANAGEMENT",
)
async def search_issues(
    provider: str,
    query: str = Query(..., description="Search query or JQL"),
    max_results: int = Query(50, description="Maximum results"),
    base_url: str | None = Query(None),
    api_key: str | None = Query(None),
    token: str | None = Query(None),
    username: str | None = Query(None),
) -> Dict[str, Any]:
    """Search for issues, cards, or tasks.

    - Jira: Supports full JQL syntax
    - Trello: Text search across boards and cards
    - Asana: Text search across tasks
    """
    _validate_provider(provider)

    config = IntegrationConfig(
        name=f"{provider}_integration",
        provider=provider,
        base_url=base_url,
        api_key=api_key,
        token=token,
        username=username,
    )

    integration = _get_integration(provider, config)

    if provider == "jira":
        params = {"jql": query, "max_results": max_results}
        return await integration.execute_action("search_jql", params)
    else:
        raise HTTPException(
            status_code=501,
            detail=f"Search not yet implemented for {provider}",
        )
