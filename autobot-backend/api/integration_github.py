# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
FastAPI router for GitHub integration (Issue #4097).

Exposes GitHub API capabilities — PRs, issues, code reviews, repository
context — as HTTP endpoints that agents can call via the integration layer.
"""

from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, Query

from api.schemas_system import (
    GitHubCommitResponse,
    GitHubCommitsResponse,
    GitHubFileContentsResponse,
    GitHubIssueResponse,
    GitHubIssuesResponse,
    GitHubPRCommentResponse,
    GitHubPRCommentsResponse,
    GitHubProviderInfo,
    GitHubPRReviewResponse,
    GitHubPullRequestDiffResponse,
    GitHubPullRequestResponse,
    GitHubPullRequestsResponse,
    GitHubRepositoryResponse,
    GitHubRepositoryTreeResponse,
)
from api.schemas_workflows import (
    GitHubCommentRequest,
    GitHubConnectionTestRequest,
    GitHubReviewRequest,
)
from auth_middleware import check_admin_permission
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from autobot_shared.logging_manager import get_logger
from integrations.base import IntegrationConfig, IntegrationHealth
from integrations.github_integration import GitHubIntegration

logger = get_logger(__name__)

router = APIRouter(
    tags=["integrations-github"],
    dependencies=[Depends(check_admin_permission)],
)

# ---------------------------------------------------------------------------
# Request/response models
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Factory helper
# ---------------------------------------------------------------------------


def _make_integration(token: str, base_url: str | None = None) -> GitHubIntegration:
    """Build a GitHubIntegration from a raw token.

    Helper for endpoint handlers (Issue #4097).
    """
    cfg = IntegrationConfig(
        name="github",
        provider="github",
        token=token,
        base_url=base_url,
    )
    return GitHubIntegration(cfg)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/test-connection", response_model=IntegrationHealth)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="test_connection",
    error_code_prefix="INTEGRATION_GITHUB",
)
async def test_connection(
    request: GitHubConnectionTestRequest,
) -> IntegrationHealth:
    """Test a GitHub Personal Access Token.

    Returns:
        IntegrationHealth reflecting token validity and authenticated user.
    """
    try:
        integration = _make_integration(request.token, request.base_url)
        health = await integration.test_connection()
        logger.info("GitHub connection test result: %s", health.status)
        return health
    except Exception as exc:
        logger.error("GitHub connection test failed: %s", exc)
        raise HTTPException(status_code=500, detail="Connection test failed")


@router.get("/{owner}/{repo}/pull-requests", response_model=GitHubPullRequestsResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="list_pull_requests",
    error_code_prefix="INTEGRATION_GITHUB",
)
async def list_pull_requests(
    owner: str,
    repo: str,
    token: str = Query(..., description="GitHub Personal Access Token"),
    state: str | None = Query("open", description="PR state: open, closed, all"),
    base: str | None = Query(None, description="Filter by base branch"),
    head: str | None = Query(None, description="Filter by head branch"),
) -> Dict[str, Any]:
    """List pull requests for a repository.

    Returns:
        Dictionary with pull_requests list and count.
    """
    try:
        integration = _make_integration(token)
        params: Dict[str, Any] = {"owner": owner, "repo": repo, "state": state}
        if base:
            params["base"] = base
        if head:
            params["head"] = head
        result = await integration.execute_action("list_pull_requests", params)
        logger.info("Listed PRs for %s/%s (%s)", owner, repo, state)
        return result
    except Exception as exc:
        logger.error("Failed to list PRs for %s/%s: %s", owner, repo, exc)
        raise HTTPException(status_code=500, detail="Failed to list pull requests")


@router.get("/{owner}/{repo}/pull-requests/{pull_number}", response_model=GitHubPullRequestResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_pull_request",
    error_code_prefix="INTEGRATION_GITHUB",
)
async def get_pull_request(
    owner: str,
    repo: str,
    pull_number: int,
    token: str = Query(..., description="GitHub Personal Access Token"),
) -> Dict[str, Any]:
    """Fetch a single pull request with full metadata.

    Returns:
        Dictionary with pull_request details.
    """
    try:
        integration = _make_integration(token)
        result = await integration.execute_action(
            "get_pull_request",
            {"owner": owner, "repo": repo, "pull_number": pull_number},
        )
        return result
    except Exception as exc:
        logger.error("Failed to get PR %s/%s#%d: %s", owner, repo, pull_number, exc)
        raise HTTPException(status_code=500, detail="Failed to get pull request")


@router.get("/{owner}/{repo}/pull-requests/{pull_number}/diff", response_model=GitHubPullRequestDiffResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_pull_request_diff",
    error_code_prefix="INTEGRATION_GITHUB",
)
async def get_pull_request_diff(
    owner: str,
    repo: str,
    pull_number: int,
    token: str = Query(..., description="GitHub Personal Access Token"),
) -> Dict[str, Any]:
    """Fetch the unified diff of a pull request.

    Returns:
        Dictionary with diff string.
    """
    try:
        integration = _make_integration(token)
        result = await integration.execute_action(
            "get_pull_request_diff",
            {"owner": owner, "repo": repo, "pull_number": pull_number},
        )
        return result
    except Exception as exc:
        logger.error("Failed to get diff for %s/%s#%d: %s", owner, repo, pull_number, exc)
        raise HTTPException(status_code=500, detail="Failed to get pull request diff")


@router.get("/{owner}/{repo}/pull-requests/{pull_number}/comments", response_model=GitHubPRCommentsResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="list_pr_review_comments",
    error_code_prefix="INTEGRATION_GITHUB",
)
async def list_pr_review_comments(
    owner: str,
    repo: str,
    pull_number: int,
    token: str = Query(..., description="GitHub Personal Access Token"),
) -> Dict[str, Any]:
    """List inline review comments on a pull request.

    Returns:
        Dictionary with comments list and count.
    """
    try:
        integration = _make_integration(token)
        result = await integration.execute_action(
            "list_pr_review_comments",
            {"owner": owner, "repo": repo, "pull_number": pull_number},
        )
        return result
    except Exception as exc:
        logger.error("Failed to list comments for %s/%s#%d: %s", owner, repo, pull_number, exc)
        raise HTTPException(status_code=500, detail="Failed to list PR comments")


@router.post("/{owner}/{repo}/pull-requests/{pull_number}/comments", response_model=GitHubPRCommentResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="post_pr_comment",
    error_code_prefix="INTEGRATION_GITHUB",
)
async def post_pr_comment(request: GitHubCommentRequest) -> Dict[str, Any]:
    """Post an issue-level comment to a pull request.

    Returns:
        Dictionary with created comment object.
    """
    try:
        integration = _make_integration(request.token)
        result = await integration.execute_action(
            "post_pr_comment",
            {
                "owner": request.owner,
                "repo": request.repo,
                "pull_number": request.pull_number,
                "body": request.body,
            },
        )
        logger.info("Posted comment to %s/%s#%d", request.owner, request.repo, request.pull_number)
        return result
    except Exception as exc:
        logger.error("Failed to post PR comment: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to post PR comment")


@router.post("/{owner}/{repo}/pull-requests/{pull_number}/reviews", response_model=GitHubPRReviewResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="submit_pr_review",
    error_code_prefix="INTEGRATION_GITHUB",
)
async def submit_pr_review(request: GitHubReviewRequest) -> Dict[str, Any]:
    """Submit a formal pull request review.

    Returns:
        Dictionary with created review object.
    """
    if request.event not in ("APPROVE", "REQUEST_CHANGES", "COMMENT"):
        raise HTTPException(
            status_code=400,
            detail="event must be APPROVE, REQUEST_CHANGES, or COMMENT",
        )
    try:
        integration = _make_integration(request.token)
        result = await integration.execute_action(
            "submit_pr_review",
            {
                "owner": request.owner,
                "repo": request.repo,
                "pull_number": request.pull_number,
                "body": request.body,
                "event": request.event,
            },
        )
        logger.info(
            "Submitted %s review on %s/%s#%d",
            request.event,
            request.owner,
            request.repo,
            request.pull_number,
        )
        return result
    except Exception as exc:
        logger.error("Failed to submit PR review: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to submit PR review")


@router.get("/{owner}/{repo}/issues", response_model=GitHubIssuesResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="list_issues",
    error_code_prefix="INTEGRATION_GITHUB",
)
async def list_issues(
    owner: str,
    repo: str,
    token: str = Query(..., description="GitHub Personal Access Token"),
    state: str | None = Query("open", description="Issue state: open, closed, all"),
    labels: str | None = Query(None, description="Comma-separated label names"),
    assignee: str | None = Query(None, description="Filter by assignee login"),
) -> Dict[str, Any]:
    """List issues in a repository (pull requests excluded).

    Returns:
        Dictionary with issues list and count.
    """
    try:
        integration = _make_integration(token)
        params: Dict[str, Any] = {"owner": owner, "repo": repo, "state": state}
        if labels:
            params["labels"] = labels
        if assignee:
            params["assignee"] = assignee
        result = await integration.execute_action("list_issues", params)
        logger.info("Listed issues for %s/%s (%s)", owner, repo, state)
        return result
    except Exception as exc:
        logger.error("Failed to list issues for %s/%s: %s", owner, repo, exc)
        raise HTTPException(status_code=500, detail="Failed to list issues")


@router.get("/{owner}/{repo}/issues/{issue_number}", response_model=GitHubIssueResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_issue",
    error_code_prefix="INTEGRATION_GITHUB",
)
async def get_issue(
    owner: str,
    repo: str,
    issue_number: int,
    token: str = Query(..., description="GitHub Personal Access Token"),
) -> Dict[str, Any]:
    """Fetch a single GitHub issue.

    Returns:
        Dictionary with issue details.
    """
    try:
        integration = _make_integration(token)
        result = await integration.execute_action(
            "get_issue",
            {"owner": owner, "repo": repo, "issue_number": issue_number},
        )
        return result
    except Exception as exc:
        logger.error("Failed to get issue %s/%s#%d: %s", owner, repo, issue_number, exc)
        raise HTTPException(status_code=500, detail="Failed to get issue")


@router.get("/{owner}/{repo}", response_model=GitHubRepositoryResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_repository",
    error_code_prefix="INTEGRATION_GITHUB",
)
async def get_repository(
    owner: str,
    repo: str,
    token: str = Query(..., description="GitHub Personal Access Token"),
) -> Dict[str, Any]:
    """Fetch repository metadata.

    Returns:
        Dictionary with repository details.
    """
    try:
        integration = _make_integration(token)
        result = await integration.execute_action("get_repository", {"owner": owner, "repo": repo})
        return result
    except Exception as exc:
        logger.error("Failed to get repository %s/%s: %s", owner, repo, exc)
        raise HTTPException(status_code=500, detail="Failed to get repository")


@router.get("/{owner}/{repo}/commits", response_model=GitHubCommitsResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="list_commits",
    error_code_prefix="INTEGRATION_GITHUB",
)
async def list_commits(
    owner: str,
    repo: str,
    token: str = Query(..., description="GitHub Personal Access Token"),
    sha: str | None = Query(None, description="Branch, tag, or commit SHA"),
    per_page: int = Query(30, ge=1, le=100, description="Number of commits to return"),
) -> Dict[str, Any]:
    """List recent commits for a repository branch.

    Returns:
        Dictionary with commits list and count.
    """
    try:
        integration = _make_integration(token)
        params: Dict[str, Any] = {"owner": owner, "repo": repo, "per_page": per_page}
        if sha:
            params["sha"] = sha
        result = await integration.execute_action("list_commits", params)
        logger.info("Listed commits for %s/%s", owner, repo)
        return result
    except Exception as exc:
        logger.error("Failed to list commits for %s/%s: %s", owner, repo, exc)
        raise HTTPException(status_code=500, detail="Failed to list commits")


@router.get("/{owner}/{repo}/commits/{ref}", response_model=GitHubCommitResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_commit",
    error_code_prefix="INTEGRATION_GITHUB",
)
async def get_commit(
    owner: str,
    repo: str,
    ref: str,
    token: str = Query(..., description="GitHub Personal Access Token"),
) -> Dict[str, Any]:
    """Fetch a single commit including files changed.

    Returns:
        Dictionary with commit details and file list.
    """
    try:
        integration = _make_integration(token)
        result = await integration.execute_action("get_commit", {"owner": owner, "repo": repo, "ref": ref})
        return result
    except Exception as exc:
        logger.error("Failed to get commit %s/%s@%s: %s", owner, repo, ref, exc)
        raise HTTPException(status_code=500, detail="Failed to get commit")


@router.get("/{owner}/{repo}/tree/{tree_sha}", response_model=GitHubRepositoryTreeResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_repository_tree",
    error_code_prefix="INTEGRATION_GITHUB",
)
async def get_repository_tree(
    owner: str,
    repo: str,
    tree_sha: str,
    token: str = Query(..., description="GitHub Personal Access Token"),
    recursive: bool = Query(False, description="Fetch tree recursively"),
) -> Dict[str, Any]:
    """Fetch the file tree of a repository at a given ref.

    Returns:
        Dictionary with tree entries.
    """
    try:
        integration = _make_integration(token)
        result = await integration.execute_action(
            "get_repository_tree",
            {"owner": owner, "repo": repo, "tree_sha": tree_sha, "recursive": recursive},
        )
        return result
    except Exception as exc:
        logger.error("Failed to get tree %s/%s@%s: %s", owner, repo, tree_sha, exc)
        raise HTTPException(status_code=500, detail="Failed to get repository tree")


@router.get("/{owner}/{repo}/contents/{path:path}", response_model=GitHubFileContentsResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_file_contents",
    error_code_prefix="INTEGRATION_GITHUB",
)
async def get_file_contents(
    owner: str,
    repo: str,
    path: str,
    token: str = Query(..., description="GitHub Personal Access Token"),
    ref: str | None = Query(None, description="Branch, tag, or commit SHA"),
) -> Dict[str, Any]:
    """Fetch the contents of a single file.

    Returns:
        Dictionary with file contents (base64-encoded per GitHub API).
    """
    try:
        integration = _make_integration(token)
        params: Dict[str, Any] = {"owner": owner, "repo": repo, "path": path}
        if ref:
            params["ref"] = ref
        result = await integration.execute_action("get_file_contents", params)
        return result
    except Exception as exc:
        logger.error("Failed to get file %s/%s/%s: %s", owner, repo, path, exc)
        raise HTTPException(status_code=500, detail="Failed to get file contents")


@router.get("/providers", response_model=list[GitHubProviderInfo])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_providers",
    error_code_prefix="INTEGRATION_GITHUB",
)
async def get_providers() -> List[Dict[str, Any]]:
    """List supported GitHub integration providers.

    Returns:
        List with GitHub provider descriptor.
    """
    return [
        {
            "id": "github",
            "name": "GitHub",
            "description": "GitHub API integration for code context and reviews",
            "required_settings": ["token"],
            "optional_settings": ["base_url"],
        }
    ]
