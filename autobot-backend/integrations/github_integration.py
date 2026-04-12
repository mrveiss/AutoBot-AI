# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
GitHub API Integration (Issue #4097)

Provides GitHub API access for agents: pull requests, issues, code reviews,
repository structure, and commit context.  Authenticates via a Personal Access
Token (PAT) stored in IntegrationConfig.token or IntegrationConfig.api_key.
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

import aiohttp

from integrations.base import (
    BaseIntegration,
    IntegrationAction,
    IntegrationConfig,
    IntegrationHealth,
    IntegrationStatus,
)

logger = logging.getLogger(__name__)

_GITHUB_API = "https://api.github.com"


class GitHubIntegration(BaseIntegration):
    """GitHub REST API integration for code context and reviews.

    Supports fetching PRs, diffs, issues, review comments, repository trees,
    and recent commits.  All operations are read-write: agents may also post
    PR comments and submit reviews.

    Authentication: supply a Personal Access Token (PAT) via
    ``IntegrationConfig.token`` or ``IntegrationConfig.api_key``.
    """

    def __init__(self, config: IntegrationConfig) -> None:
        super().__init__(config)
        self.base_url = (config.base_url or _GITHUB_API).rstrip("/")
        token = config.token or config.api_key or ""
        self.headers: Dict[str, str] = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    # ------------------------------------------------------------------
    # BaseIntegration contract
    # ------------------------------------------------------------------

    async def test_connection(self) -> IntegrationHealth:
        """Verify credentials by calling /user.

        Returns:
            IntegrationHealth reflecting current token validity.
        """
        start = datetime.utcnow()
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.base_url}/user",
                    headers=self.headers,
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    elapsed = (datetime.utcnow() - start).total_seconds() * 1000
                    if resp.status == 200:
                        data = await resp.json()
                        self._status = IntegrationStatus.CONNECTED
                        return IntegrationHealth(
                            provider="github",
                            status=IntegrationStatus.HEALTHY,
                            latency_ms=elapsed,
                            message=f"Connected as {data.get('login')}",
                            last_checked=datetime.utcnow(),
                            details={"login": data.get("login"), "id": data.get("id")},
                        )
                    self._status = IntegrationStatus.UNAUTHORIZED
                    return IntegrationHealth(
                        provider="github",
                        status=IntegrationStatus.UNHEALTHY,
                        latency_ms=elapsed,
                        message=f"GitHub API returned HTTP {resp.status}",
                        last_checked=datetime.utcnow(),
                    )
        except aiohttp.ClientError as exc:
            logger.error("GitHub connection test failed: %s", exc)
            self._status = IntegrationStatus.ERROR
            return IntegrationHealth(
                provider="github",
                status=IntegrationStatus.UNHEALTHY,
                message=f"Connection error: {exc}",
                last_checked=datetime.utcnow(),
            )

    def get_available_actions(self) -> List[IntegrationAction]:
        """Return all supported GitHub actions."""
        return [
            IntegrationAction(
                name="get_pull_request",
                description="Fetch a single PR including metadata and diff URL",
                method="GET",
                parameters={"owner": "string", "repo": "string", "pull_number": "integer"},
            ),
            IntegrationAction(
                name="list_pull_requests",
                description="List pull requests for a repository",
                method="GET",
                parameters={
                    "owner": "string",
                    "repo": "string",
                    "state": "string",
                    "head": "string",
                    "base": "string",
                },
            ),
            IntegrationAction(
                name="get_pull_request_diff",
                description="Fetch the unified diff of a pull request",
                method="GET",
                parameters={"owner": "string", "repo": "string", "pull_number": "integer"},
            ),
            IntegrationAction(
                name="list_pr_review_comments",
                description="List inline review comments on a pull request",
                method="GET",
                parameters={"owner": "string", "repo": "string", "pull_number": "integer"},
            ),
            IntegrationAction(
                name="post_pr_comment",
                description="Post an issue-level comment to a pull request",
                method="POST",
                parameters={
                    "owner": "string",
                    "repo": "string",
                    "pull_number": "integer",
                    "body": "string",
                },
            ),
            IntegrationAction(
                name="submit_pr_review",
                description="Submit a formal PR review (APPROVE/REQUEST_CHANGES/COMMENT)",
                method="POST",
                parameters={
                    "owner": "string",
                    "repo": "string",
                    "pull_number": "integer",
                    "body": "string",
                    "event": "string",
                },
            ),
            IntegrationAction(
                name="get_issue",
                description="Fetch a single GitHub issue",
                method="GET",
                parameters={"owner": "string", "repo": "string", "issue_number": "integer"},
            ),
            IntegrationAction(
                name="list_issues",
                description="List issues in a repository",
                method="GET",
                parameters={
                    "owner": "string",
                    "repo": "string",
                    "state": "string",
                    "labels": "string",
                    "assignee": "string",
                },
            ),
            IntegrationAction(
                name="get_repository",
                description="Fetch repository metadata",
                method="GET",
                parameters={"owner": "string", "repo": "string"},
            ),
            IntegrationAction(
                name="list_commits",
                description="List recent commits on a branch",
                method="GET",
                parameters={
                    "owner": "string",
                    "repo": "string",
                    "sha": "string",
                    "per_page": "integer",
                },
            ),
            IntegrationAction(
                name="get_commit",
                description="Fetch a single commit including files changed",
                method="GET",
                parameters={"owner": "string", "repo": "string", "ref": "string"},
            ),
            IntegrationAction(
                name="get_repository_tree",
                description="Fetch the file tree of a repository at a given ref",
                method="GET",
                parameters={
                    "owner": "string",
                    "repo": "string",
                    "tree_sha": "string",
                    "recursive": "boolean",
                },
            ),
            IntegrationAction(
                name="get_file_contents",
                description="Fetch the contents of a single file",
                method="GET",
                parameters={
                    "owner": "string",
                    "repo": "string",
                    "path": "string",
                    "ref": "string",
                },
            ),
        ]

    async def execute_action(
        self, action: str, params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Dispatch to the appropriate GitHub API method.

        Args:
            action: Action name from get_available_actions().
            params: Parameters for the action.

        Returns:
            Result dictionary.

        Raises:
            ValueError: If action is not recognised.
        """
        dispatch: Dict[str, Any] = {
            "get_pull_request": self._get_pull_request,
            "list_pull_requests": self._list_pull_requests,
            "get_pull_request_diff": self._get_pull_request_diff,
            "list_pr_review_comments": self._list_pr_review_comments,
            "post_pr_comment": self._post_pr_comment,
            "submit_pr_review": self._submit_pr_review,
            "get_issue": self._get_issue,
            "list_issues": self._list_issues,
            "get_repository": self._get_repository,
            "list_commits": self._list_commits,
            "get_commit": self._get_commit,
            "get_repository_tree": self._get_repository_tree,
            "get_file_contents": self._get_file_contents,
        }
        if action not in dispatch:
            raise ValueError(f"Unknown GitHub action: {action}")
        return await dispatch[action](params)

    # ------------------------------------------------------------------
    # Pull-request helpers
    # ------------------------------------------------------------------

    async def _get_pull_request(self, params: Dict[str, Any]) -> Dict[str, Any]:
        owner, repo = params["owner"], params["repo"]
        pull_number = params["pull_number"]
        url = f"{self.base_url}/repos/{owner}/{repo}/pulls/{pull_number}"
        return {"pull_request": await self._get(url)}

    async def _list_pull_requests(self, params: Dict[str, Any]) -> Dict[str, Any]:
        owner, repo = params["owner"], params["repo"]
        query: Dict[str, Any] = {"state": params.get("state", "open"), "per_page": 100}
        for key in ("head", "base"):
            if key in params:
                query[key] = params[key]
        url = f"{self.base_url}/repos/{owner}/{repo}/pulls"
        prs = await self._get(url, query_params=query)
        return {"pull_requests": prs, "count": len(prs)}

    async def _get_pull_request_diff(self, params: Dict[str, Any]) -> Dict[str, Any]:
        owner, repo = params["owner"], params["repo"]
        pull_number = params["pull_number"]
        url = f"{self.base_url}/repos/{owner}/{repo}/pulls/{pull_number}"
        diff_headers = dict(self.headers)
        diff_headers["Accept"] = "application/vnd.github.diff"
        async with aiohttp.ClientSession() as session:
            async with session.get(
                url, headers=diff_headers, timeout=aiohttp.ClientTimeout(total=30)
            ) as resp:
                resp.raise_for_status()
                diff = await resp.text(encoding="utf-8")
        return {"diff": diff}

    async def _list_pr_review_comments(self, params: Dict[str, Any]) -> Dict[str, Any]:
        owner, repo = params["owner"], params["repo"]
        pull_number = params["pull_number"]
        url = f"{self.base_url}/repos/{owner}/{repo}/pulls/{pull_number}/comments"
        comments = await self._get(url)
        return {"comments": comments, "count": len(comments)}

    async def _post_pr_comment(self, params: Dict[str, Any]) -> Dict[str, Any]:
        owner, repo = params["owner"], params["repo"]
        pull_number = params["pull_number"]
        url = f"{self.base_url}/repos/{owner}/{repo}/issues/{pull_number}/comments"
        result = await self._post(url, {"body": params["body"]})
        return {"comment": result}

    async def _submit_pr_review(self, params: Dict[str, Any]) -> Dict[str, Any]:
        owner, repo = params["owner"], params["repo"]
        pull_number = params["pull_number"]
        url = f"{self.base_url}/repos/{owner}/{repo}/pulls/{pull_number}/reviews"
        payload = {
            "body": params.get("body", ""),
            "event": params.get("event", "COMMENT"),
        }
        result = await self._post(url, payload)
        return {"review": result}

    # ------------------------------------------------------------------
    # Issue helpers
    # ------------------------------------------------------------------

    async def _get_issue(self, params: Dict[str, Any]) -> Dict[str, Any]:
        owner, repo = params["owner"], params["repo"]
        issue_number = params["issue_number"]
        url = f"{self.base_url}/repos/{owner}/{repo}/issues/{issue_number}"
        return {"issue": await self._get(url)}

    async def _list_issues(self, params: Dict[str, Any]) -> Dict[str, Any]:
        owner, repo = params["owner"], params["repo"]
        query: Dict[str, Any] = {
            "state": params.get("state", "open"),
            "per_page": 100,
        }
        for key in ("labels", "assignee"):
            if key in params:
                query[key] = params[key]
        url = f"{self.base_url}/repos/{owner}/{repo}/issues"
        issues = await self._get(url, query_params=query)
        # GitHub returns PRs in /issues — filter them out
        real_issues = [i for i in issues if "pull_request" not in i]
        return {"issues": real_issues, "count": len(real_issues)}

    # ------------------------------------------------------------------
    # Repository helpers
    # ------------------------------------------------------------------

    async def _get_repository(self, params: Dict[str, Any]) -> Dict[str, Any]:
        owner, repo = params["owner"], params["repo"]
        url = f"{self.base_url}/repos/{owner}/{repo}"
        return {"repository": await self._get(url)}

    async def _list_commits(self, params: Dict[str, Any]) -> Dict[str, Any]:
        owner, repo = params["owner"], params["repo"]
        query: Dict[str, Any] = {"per_page": params.get("per_page", 30)}
        if "sha" in params:
            query["sha"] = params["sha"]
        url = f"{self.base_url}/repos/{owner}/{repo}/commits"
        commits = await self._get(url, query_params=query)
        return {"commits": commits, "count": len(commits)}

    async def _get_commit(self, params: Dict[str, Any]) -> Dict[str, Any]:
        owner, repo, ref = params["owner"], params["repo"], params["ref"]
        url = f"{self.base_url}/repos/{owner}/{repo}/commits/{ref}"
        return {"commit": await self._get(url)}

    async def _get_repository_tree(self, params: Dict[str, Any]) -> Dict[str, Any]:
        owner, repo = params["owner"], params["repo"]
        tree_sha = params.get("tree_sha", "HEAD")
        query: Dict[str, Any] = {}
        if params.get("recursive"):
            query["recursive"] = "1"
        url = f"{self.base_url}/repos/{owner}/{repo}/git/trees/{tree_sha}"
        tree = await self._get(url, query_params=query)
        return {"tree": tree}

    async def _get_file_contents(self, params: Dict[str, Any]) -> Dict[str, Any]:
        owner, repo, path = params["owner"], params["repo"], params["path"]
        query: Dict[str, Any] = {}
        if "ref" in params:
            query["ref"] = params["ref"]
        url = f"{self.base_url}/repos/{owner}/{repo}/contents/{path}"
        contents = await self._get(url, query_params=query)
        return {"contents": contents}

    # ------------------------------------------------------------------
    # HTTP primitives
    # ------------------------------------------------------------------

    async def _get(
        self,
        url: str,
        query_params: Optional[Dict[str, Any]] = None,
        timeout: float = 30.0,
    ) -> Any:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                url,
                headers=self.headers,
                params=query_params,
                timeout=aiohttp.ClientTimeout(total=timeout),
            ) as resp:
                resp.raise_for_status()
                return await resp.json()

    async def _post(
        self,
        url: str,
        payload: Dict[str, Any],
        timeout: float = 30.0,
    ) -> Any:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url,
                headers=self.headers,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=timeout),
            ) as resp:
                resp.raise_for_status()
                return await resp.json()
