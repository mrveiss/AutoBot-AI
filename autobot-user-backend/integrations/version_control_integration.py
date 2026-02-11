# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss

"""Version Control System integrations for GitLab and Bitbucket."""

import logging
from datetime import datetime
from typing import Any, Dict, List

import aiohttp

from backend.integrations.base import (
    BaseIntegration,
    IntegrationAction,
    IntegrationConfig,
    IntegrationHealth,
    IntegrationStatus,
)

logger = logging.getLogger(__name__)


class GitLabIntegration(BaseIntegration):
    """GitLab API integration for version control operations."""

    def __init__(self, config: IntegrationConfig):
        """Initialize GitLab integration.

        Args:
            config: Integration configuration with api_key as Private-Token
        """
        super().__init__(config)
        self.base_url = config.base_url or "https://gitlab.com/api/v4"
        self.headers = {"Private-Token": config.api_key}

    async def test_connection(self) -> IntegrationHealth:
        """Test GitLab API connection.

        Returns:
            IntegrationHealth with connection status
        """
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.base_url}/user",
                    headers=self.headers,
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as response:
                    if response.status == 200:
                        user_data = await response.json()
                        return IntegrationHealth(
                            status=IntegrationStatus.HEALTHY,
                            message=f"Connected as {user_data.get('username')}",
                            last_checked=datetime.utcnow(),
                        )
                    return IntegrationHealth(
                        status=IntegrationStatus.UNHEALTHY,
                        message=f"API returned status {response.status}",
                        last_checked=datetime.utcnow(),
                    )
        except Exception as e:
            logger.error("GitLab connection test failed: %s", str(e))
            return IntegrationHealth(
                status=IntegrationStatus.UNHEALTHY,
                message=f"Connection failed: {str(e)}",
                last_checked=datetime.utcnow(),
            )

    def get_available_actions(self) -> List[IntegrationAction]:
        """Get list of available GitLab actions.

        Returns:
            List of IntegrationAction objects
        """
        return [
            IntegrationAction(
                name="list_projects",
                description="List accessible GitLab projects",
                parameters={"search": "string", "visibility": "string"},
            ),
            IntegrationAction(
                name="list_merge_requests",
                description="List merge requests for a project",
                parameters={"project_id": "integer", "state": "string"},
            ),
            IntegrationAction(
                name="list_branches",
                description="List branches for a project",
                parameters={"project_id": "integer", "search": "string"},
            ),
            IntegrationAction(
                name="get_commit_info",
                description="Get detailed commit information",
                parameters={"project_id": "integer", "commit_sha": "string"},
            ),
            IntegrationAction(
                name="compare_branches",
                description="Compare two branches",
                parameters={
                    "project_id": "integer",
                    "from_branch": "string",
                    "to_branch": "string",
                },
            ),
        ]

    async def execute_action(
        self, action: str, params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Execute a GitLab action.

        Args:
            action: Action ID to execute
            params: Action parameters

        Returns:
            Action result data
        """
        action_map = {
            "list_projects": self._list_projects,
            "list_merge_requests": self._list_merge_requests,
            "list_branches": self._list_branches,
            "get_commit_info": self._get_commit_info,
            "compare_branches": self._compare_branches,
        }

        if action not in action_map:
            raise ValueError(f"Unknown action: {action}")

        return await action_map[action](params)

    async def _list_projects(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """List accessible GitLab projects.

        Args:
            params: Optional search and visibility filters

        Returns:
            Dictionary with projects list
        """
        query_params = {}
        if "search" in params:
            query_params["search"] = params["search"]
        if "visibility" in params:
            query_params["visibility"] = params["visibility"]

        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{self.base_url}/projects",
                headers=self.headers,
                params=query_params,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as response:
                response.raise_for_status()
                projects = await response.json()
                return {"projects": projects, "count": len(projects)}

    async def _list_merge_requests(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """List merge requests for a project.

        Args:
            params: Project ID and optional filters

        Returns:
            Dictionary with merge requests list
        """
        project_id = params["project_id"]
        query_params = {
            "state": params.get("state", "opened"),
            "scope": params.get("scope", "all"),
        }

        async with aiohttp.ClientSession() as session:
            url = f"{self.base_url}/projects/{project_id}/merge_requests"
            async with session.get(
                url,
                headers=self.headers,
                params=query_params,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as response:
                response.raise_for_status()
                merge_requests = await response.json()
                return {"merge_requests": merge_requests, "count": len(merge_requests)}

    async def _list_branches(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """List branches for a project.

        Args:
            params: Project ID and optional search filter

        Returns:
            Dictionary with branches list
        """
        project_id = params["project_id"]
        query_params = {}
        if "search" in params:
            query_params["search"] = params["search"]

        async with aiohttp.ClientSession() as session:
            url = f"{self.base_url}/projects/{project_id}/repository/branches"
            async with session.get(
                url,
                headers=self.headers,
                params=query_params,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as response:
                response.raise_for_status()
                branches = await response.json()
                return {"branches": branches, "count": len(branches)}

    async def _get_commit_info(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Get detailed commit information.

        Args:
            params: Project ID and commit SHA

        Returns:
            Dictionary with commit details
        """
        project_id = params["project_id"]
        commit_sha = params["commit_sha"]

        async with aiohttp.ClientSession() as session:
            url = (
                f"{self.base_url}/projects/{project_id}"
                f"/repository/commits/{commit_sha}"
            )
            async with session.get(
                url, headers=self.headers, timeout=aiohttp.ClientTimeout(total=30)
            ) as response:
                response.raise_for_status()
                commit = await response.json()
                return {"commit": commit}

    async def _compare_branches(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Compare two branches.

        Args:
            params: Project ID, from_branch, and to_branch

        Returns:
            Dictionary with comparison data
        """
        project_id = params["project_id"]
        query_params = {"from": params["from_branch"], "to": params["to_branch"]}

        async with aiohttp.ClientSession() as session:
            url = f"{self.base_url}/projects/{project_id}/repository/compare"
            async with session.get(
                url,
                headers=self.headers,
                params=query_params,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as response:
                response.raise_for_status()
                comparison = await response.json()
                return {"comparison": comparison}


class BitbucketIntegration(BaseIntegration):
    """Bitbucket API integration for version control operations."""

    def __init__(self, config: IntegrationConfig):
        """Initialize Bitbucket integration.

        Args:
            config: Integration configuration with credentials
        """
        super().__init__(config)
        self.base_url = config.base_url or "https://api.bitbucket.org/2.0"
        self.workspace = config.extra.get("workspace")
        self._setup_auth(config)

    def _setup_auth(self, config: IntegrationConfig) -> None:
        """Setup authentication headers.

        Args:
            config: Integration configuration

        Helper for __init__ (Issue #61).
        """
        auth_type = config.extra.get("auth_type", "app_password")
        if auth_type == "bearer":
            self.headers = {"Authorization": f"Bearer {config.api_key}"}
        else:
            username = config.username or ""
            self.auth = aiohttp.BasicAuth(username, config.api_key)
            self.headers = {}

    async def test_connection(self) -> IntegrationHealth:
        """Test Bitbucket API connection.

        Returns:
            IntegrationHealth with connection status
        """
        try:
            async with aiohttp.ClientSession() as session:
                kwargs = {"headers": self.headers, "timeout": 10}
                if hasattr(self, "auth"):
                    kwargs["auth"] = self.auth

                async with session.get(f"{self.base_url}/user", **kwargs) as response:
                    if response.status == 200:
                        user_data = await response.json()
                        return IntegrationHealth(
                            status=IntegrationStatus.HEALTHY,
                            message=(f"Connected as {user_data.get('username')}"),
                            last_checked=datetime.utcnow(),
                        )
                    return IntegrationHealth(
                        status=IntegrationStatus.UNHEALTHY,
                        message=f"API returned status {response.status}",
                        last_checked=datetime.utcnow(),
                    )
        except Exception as e:
            logger.error("Bitbucket connection test failed: %s", str(e))
            return IntegrationHealth(
                status=IntegrationStatus.UNHEALTHY,
                message=f"Connection failed: {str(e)}",
                last_checked=datetime.utcnow(),
            )

    def get_available_actions(self) -> List[IntegrationAction]:
        """Get list of available Bitbucket actions.

        Returns:
            List of IntegrationAction objects
        """
        return [
            IntegrationAction(
                name="list_repositories",
                description="List repositories in workspace",
                parameters={"workspace": "string"},
            ),
            IntegrationAction(
                name="list_pull_requests",
                description="List pull requests for a repository",
                parameters={"repo_slug": "string", "state": "string"},
            ),
            IntegrationAction(
                name="list_branches",
                description="List branches for a repository",
                parameters={"repo_slug": "string", "workspace": "string"},
            ),
            IntegrationAction(
                name="get_commit_info",
                description="Get detailed commit information",
                parameters={"repo_slug": "string", "commit_hash": "string"},
            ),
        ]

    async def execute_action(
        self, action: str, params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Execute a Bitbucket action.

        Args:
            action: Action ID to execute
            params: Action parameters

        Returns:
            Action result data
        """
        action_map = {
            "list_repositories": self._list_repositories,
            "list_pull_requests": self._list_pull_requests,
            "list_branches": self._list_branches,
            "get_commit_info": self._get_commit_info,
        }

        if action not in action_map:
            raise ValueError(f"Unknown action: {action}")

        return await action_map[action](params)

    async def _list_repositories(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """List repositories in workspace.

        Args:
            params: Optional workspace override

        Returns:
            Dictionary with repositories list
        """
        workspace = params.get("workspace", self.workspace)
        if not workspace:
            raise ValueError("Workspace is required")

        async with aiohttp.ClientSession() as session:
            kwargs = {"headers": self.headers, "timeout": 30}
            if hasattr(self, "auth"):
                kwargs["auth"] = self.auth

            url = f"{self.base_url}/repositories/{workspace}"
            async with session.get(url, **kwargs) as response:
                response.raise_for_status()
                data = await response.json()
                return {
                    "repositories": data.get("values", []),
                    "count": len(data.get("values", [])),
                }

    async def _list_pull_requests(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """List pull requests for a repository.

        Args:
            params: Repository slug and optional filters

        Returns:
            Dictionary with pull requests list
        """
        workspace = params.get("workspace", self.workspace)
        if not workspace:
            raise ValueError("Workspace is required")

        repo_slug = params["repo_slug"]
        state = params.get("state", "OPEN")

        async with aiohttp.ClientSession() as session:
            kwargs = {"headers": self.headers, "timeout": 30}
            if hasattr(self, "auth"):
                kwargs["auth"] = self.auth

            url = (
                f"{self.base_url}/repositories/{workspace}/" f"{repo_slug}/pullrequests"
            )
            kwargs["params"] = {"state": state}

            async with session.get(url, **kwargs) as response:
                response.raise_for_status()
                data = await response.json()
                return {
                    "pull_requests": data.get("values", []),
                    "count": len(data.get("values", [])),
                }

    async def _list_branches(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """List branches for a repository.

        Args:
            params: Repository slug and optional workspace

        Returns:
            Dictionary with branches list
        """
        workspace = params.get("workspace", self.workspace)
        if not workspace:
            raise ValueError("Workspace is required")

        repo_slug = params["repo_slug"]

        async with aiohttp.ClientSession() as session:
            kwargs = {"headers": self.headers, "timeout": 30}
            if hasattr(self, "auth"):
                kwargs["auth"] = self.auth

            url = (
                f"{self.base_url}/repositories/{workspace}/"
                f"{repo_slug}/refs/branches"
            )
            async with session.get(url, **kwargs) as response:
                response.raise_for_status()
                data = await response.json()
                return {
                    "branches": data.get("values", []),
                    "count": len(data.get("values", [])),
                }

    async def _get_commit_info(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Get detailed commit information.

        Args:
            params: Repository slug and commit hash

        Returns:
            Dictionary with commit details
        """
        workspace = params.get("workspace", self.workspace)
        if not workspace:
            raise ValueError("Workspace is required")

        repo_slug = params["repo_slug"]
        commit_hash = params["commit_hash"]

        async with aiohttp.ClientSession() as session:
            kwargs = {"headers": self.headers, "timeout": 30}
            if hasattr(self, "auth"):
                kwargs["auth"] = self.auth

            url = (
                f"{self.base_url}/repositories/{workspace}/"
                f"{repo_slug}/commit/{commit_hash}"
            )
            async with session.get(url, **kwargs) as response:
                response.raise_for_status()
                commit = await response.json()
                return {"commit": commit}
