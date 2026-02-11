# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Project Management Integration (Issue #61)

Provides integrations with popular project management platforms:
- Jira: Issue tracking, project management, sprint planning
- Trello: Board-based task management
- Asana: Team collaboration and task management

Each integration supports connection testing, resource listing,
and CRUD operations for tasks/issues/cards.
"""

import base64
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

import aiohttp

from backend.integrations.base import (
    BaseIntegration,
    IntegrationAction,
    IntegrationConfig,
    IntegrationHealth,
    IntegrationStatus,
)

logger = logging.getLogger(__name__)


# =============================================================================
# Jira Integration
# =============================================================================


class JiraIntegration(BaseIntegration):
    """Jira Cloud/Server integration.

    Authentication: Basic Auth (email:api_token)
    Base URL: https://your-domain.atlassian.net
    """

    def __init__(self, config: IntegrationConfig):
        super().__init__(config)
        self._session: Optional[aiohttp.ClientSession] = None

    async def test_connection(self) -> IntegrationHealth:
        """Test Jira connection by fetching server info."""
        start_time = datetime.utcnow()
        try:
            result = await self._jira_request("GET", "/rest/api/3/serverInfo")
            latency = (datetime.utcnow() - start_time).total_seconds() * 1000

            if result.get("status_code") == 200:
                self._status = IntegrationStatus.CONNECTED
                body = result.get("body", {})
                return IntegrationHealth(
                    provider="jira",
                    status=IntegrationStatus.CONNECTED,
                    latency_ms=latency,
                    message="Connected successfully",
                    details={
                        "version": body.get("version"),
                        "server_title": body.get("serverTitle"),
                    },
                )
            elif result.get("status_code") == 401:
                self._status = IntegrationStatus.UNAUTHORIZED
                return IntegrationHealth(
                    provider="jira",
                    status=IntegrationStatus.UNAUTHORIZED,
                    message="Invalid credentials",
                )
            else:
                self._status = IntegrationStatus.ERROR
                return IntegrationHealth(
                    provider="jira",
                    status=IntegrationStatus.ERROR,
                    message=f"HTTP {result.get('status_code')}",
                )
        except Exception as exc:
            self.logger.exception("Jira connection test failed")
            self._status = IntegrationStatus.ERROR
            return IntegrationHealth(
                provider="jira",
                status=IntegrationStatus.ERROR,
                message=str(exc),
            )

    def get_available_actions(self) -> List[IntegrationAction]:
        """Return list of supported Jira actions."""
        return [
            IntegrationAction(
                name="list_projects",
                description="List all accessible projects",
                method="GET",
                parameters={},
            ),
            IntegrationAction(
                name="list_issues",
                description="List issues in a project",
                method="GET",
                parameters={"project_key": "Project key (e.g., PROJ)"},
            ),
            IntegrationAction(
                name="create_issue",
                description="Create a new issue",
                method="POST",
                parameters={
                    "project_key": "Project key",
                    "summary": "Issue summary",
                    "description": "Issue description",
                    "issue_type": "Issue type (Task, Bug, Story, etc.)",
                },
            ),
            IntegrationAction(
                name="update_issue_status",
                description="Update issue status/transition",
                method="POST",
                parameters={
                    "issue_key": "Issue key (e.g., PROJ-123)",
                    "transition_id": "Transition ID or name",
                },
            ),
            IntegrationAction(
                name="search_jql",
                description="Search issues using JQL",
                method="GET",
                parameters={
                    "jql": "JQL query string",
                    "max_results": "Maximum results (optional)",
                },
            ),
        ]

    async def execute_action(
        self, action: str, params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Execute a Jira action."""
        action_map = {
            "list_projects": self._list_projects,
            "list_issues": self._list_issues,
            "create_issue": self._create_issue,
            "update_issue_status": self._update_issue_status,
            "search_jql": self._search_jql,
        }

        handler = action_map.get(action)
        if not handler:
            return {"error": f"Unknown action: {action}"}

        try:
            return await handler(params)
        except Exception as exc:
            self.logger.exception("Jira action %s failed", action)
            return {"error": str(exc)}

    async def _list_projects(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """List all accessible projects."""
        result = await self._jira_request("GET", "/rest/api/3/project")
        if result.get("status_code") == 200:
            return {"projects": result.get("body", [])}
        return {"error": f"HTTP {result.get('status_code')}"}

    async def _list_issues(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """List issues in a project."""
        project_key = params.get("project_key")
        if not project_key:
            return {"error": "project_key required"}

        jql = f"project = {project_key} ORDER BY created DESC"
        return await self._search_jql({"jql": jql, "max_results": 50})

    async def _create_issue(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new issue."""
        project_key = params.get("project_key")
        summary = params.get("summary")
        issue_type = params.get("issue_type", "Task")

        if not project_key or not summary:
            return {"error": "project_key and summary required"}

        payload = {
            "fields": {
                "project": {"key": project_key},
                "summary": summary,
                "description": {
                    "type": "doc",
                    "version": 1,
                    "content": [
                        {
                            "type": "paragraph",
                            "content": [
                                {
                                    "type": "text",
                                    "text": params.get("description", ""),
                                }
                            ],
                        }
                    ],
                },
                "issuetype": {"name": issue_type},
            }
        }

        result = await self._jira_request(
            "POST", "/rest/api/3/issue", json_data=payload
        )
        if result.get("status_code") == 201:
            return {"issue": result.get("body", {})}
        return {"error": f"HTTP {result.get('status_code')}"}

    async def _update_issue_status(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Update issue status via transition."""
        issue_key = params.get("issue_key")
        transition_id = params.get("transition_id")

        if not issue_key or not transition_id:
            return {"error": "issue_key and transition_id required"}

        payload = {"transition": {"id": transition_id}}
        endpoint = f"/rest/api/3/issue/{issue_key}/transitions"
        result = await self._jira_request("POST", endpoint, json_data=payload)

        if result.get("status_code") == 204:
            return {"success": True, "message": "Transition completed"}
        return {"error": f"HTTP {result.get('status_code')}"}

    async def _search_jql(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Search issues using JQL."""
        jql = params.get("jql")
        if not jql:
            return {"error": "jql required"}

        max_results = params.get("max_results", 50)
        endpoint = f"/rest/api/3/search?jql={jql}&maxResults={max_results}"
        result = await self._jira_request("GET", endpoint)

        if result.get("status_code") == 200:
            body = result.get("body", {})
            return {
                "total": body.get("total", 0),
                "issues": body.get("issues", []),
            }
        return {"error": f"HTTP {result.get('status_code')}"}

    async def _jira_request(
        self,
        method: str,
        endpoint: str,
        json_data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Make authenticated request to Jira API."""
        url = f"{self.config.base_url}{endpoint}"
        auth_str = f"{self.config.username}:{self.config.api_key}"
        auth_bytes = auth_str.encode("utf-8")
        auth_b64 = base64.b64encode(auth_bytes).decode("ascii")

        headers = {
            "Authorization": f"Basic {auth_b64}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        try:
            timeout = aiohttp.ClientTimeout(total=30.0)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.request(
                    method, url, headers=headers, json=json_data
                ) as resp:
                    if resp.status == 204:
                        return {"status_code": 204, "body": {}}
                    body = await resp.json()
                    return {"status_code": resp.status, "body": body}
        except aiohttp.ClientError as exc:
            self.logger.warning("Jira request to %s failed: %s", url, exc)
            return {"status_code": 0, "error": str(exc)}


# =============================================================================
# Trello Integration
# =============================================================================


class TrelloIntegration(BaseIntegration):
    """Trello integration.

    Authentication: API key + token as query parameters
    Base URL: https://api.trello.com/1
    """

    def __init__(self, config: IntegrationConfig):
        super().__init__(config)

    async def test_connection(self) -> IntegrationHealth:
        """Test Trello connection by fetching member info."""
        start_time = datetime.utcnow()
        try:
            result = await self._trello_request("GET", "/members/me")
            latency = (datetime.utcnow() - start_time).total_seconds() * 1000

            if result.get("status_code") == 200:
                self._status = IntegrationStatus.CONNECTED
                body = result.get("body", {})
                return IntegrationHealth(
                    provider="trello",
                    status=IntegrationStatus.CONNECTED,
                    latency_ms=latency,
                    message="Connected successfully",
                    details={
                        "username": body.get("username"),
                        "full_name": body.get("fullName"),
                    },
                )
            elif result.get("status_code") == 401:
                self._status = IntegrationStatus.UNAUTHORIZED
                return IntegrationHealth(
                    provider="trello",
                    status=IntegrationStatus.UNAUTHORIZED,
                    message="Invalid API key or token",
                )
            else:
                self._status = IntegrationStatus.ERROR
                return IntegrationHealth(
                    provider="trello",
                    status=IntegrationStatus.ERROR,
                    message=f"HTTP {result.get('status_code')}",
                )
        except Exception as exc:
            self.logger.exception("Trello connection test failed")
            self._status = IntegrationStatus.ERROR
            return IntegrationHealth(
                provider="trello",
                status=IntegrationStatus.ERROR,
                message=str(exc),
            )

    def get_available_actions(self) -> List[IntegrationAction]:
        """Return list of supported Trello actions."""
        return [
            IntegrationAction(
                name="list_boards",
                description="List all accessible boards",
                method="GET",
                parameters={},
            ),
            IntegrationAction(
                name="list_lists",
                description="List lists in a board",
                method="GET",
                parameters={"board_id": "Board ID"},
            ),
            IntegrationAction(
                name="list_cards",
                description="List cards in a list",
                method="GET",
                parameters={"list_id": "List ID"},
            ),
            IntegrationAction(
                name="create_card",
                description="Create a new card",
                method="POST",
                parameters={
                    "list_id": "List ID",
                    "name": "Card name",
                    "description": "Card description (optional)",
                },
            ),
            IntegrationAction(
                name="move_card",
                description="Move card to different list",
                method="PUT",
                parameters={"card_id": "Card ID", "list_id": "Target list ID"},
            ),
        ]

    async def execute_action(
        self, action: str, params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Execute a Trello action."""
        action_map = {
            "list_boards": self._list_boards,
            "list_lists": self._list_lists,
            "list_cards": self._list_cards,
            "create_card": self._create_card,
            "move_card": self._move_card,
        }

        handler = action_map.get(action)
        if not handler:
            return {"error": f"Unknown action: {action}"}

        try:
            return await handler(params)
        except Exception as exc:
            self.logger.exception("Trello action %s failed", action)
            return {"error": str(exc)}

    async def _list_boards(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """List all accessible boards."""
        result = await self._trello_request("GET", "/members/me/boards")
        if result.get("status_code") == 200:
            return {"boards": result.get("body", [])}
        return {"error": f"HTTP {result.get('status_code')}"}

    async def _list_lists(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """List lists in a board."""
        board_id = params.get("board_id")
        if not board_id:
            return {"error": "board_id required"}

        endpoint = f"/boards/{board_id}/lists"
        result = await self._trello_request("GET", endpoint)

        if result.get("status_code") == 200:
            return {"lists": result.get("body", [])}
        return {"error": f"HTTP {result.get('status_code')}"}

    async def _list_cards(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """List cards in a list."""
        list_id = params.get("list_id")
        if not list_id:
            return {"error": "list_id required"}

        endpoint = f"/lists/{list_id}/cards"
        result = await self._trello_request("GET", endpoint)

        if result.get("status_code") == 200:
            return {"cards": result.get("body", [])}
        return {"error": f"HTTP {result.get('status_code')}"}

    async def _create_card(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new card."""
        list_id = params.get("list_id")
        name = params.get("name")

        if not list_id or not name:
            return {"error": "list_id and name required"}

        data = {"idList": list_id, "name": name}
        if "description" in params:
            data["desc"] = params["description"]

        result = await self._trello_request("POST", "/cards", data=data)

        if result.get("status_code") == 200:
            return {"card": result.get("body", {})}
        return {"error": f"HTTP {result.get('status_code')}"}

    async def _move_card(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Move card to different list."""
        card_id = params.get("card_id")
        list_id = params.get("list_id")

        if not card_id or not list_id:
            return {"error": "card_id and list_id required"}

        endpoint = f"/cards/{card_id}"
        data = {"idList": list_id}
        result = await self._trello_request("PUT", endpoint, data=data)

        if result.get("status_code") == 200:
            return {"card": result.get("body", {})}
        return {"error": f"HTTP {result.get('status_code')}"}

    async def _trello_request(
        self,
        method: str,
        endpoint: str,
        data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Make authenticated request to Trello API."""
        base_url = self.config.base_url or "https://api.trello.com/1"
        url = f"{base_url}{endpoint}"

        params = {
            "key": self.config.api_key,
            "token": self.config.token,
        }

        if data and method == "GET":
            params.update(data)
            data = None

        try:
            timeout = aiohttp.ClientTimeout(total=30.0)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.request(
                    method,
                    url,
                    params=params,
                    json=data if method != "GET" else None,
                ) as resp:
                    body = await resp.json()
                    return {"status_code": resp.status, "body": body}
        except aiohttp.ClientError as exc:
            self.logger.warning("Trello request to %s failed: %s", url, exc)
            return {"status_code": 0, "error": str(exc)}


# =============================================================================
# Asana Integration
# =============================================================================


class AsanaIntegration(BaseIntegration):
    """Asana integration.

    Authentication: Bearer token
    Base URL: https://app.asana.com/api/1.0
    """

    def __init__(self, config: IntegrationConfig):
        super().__init__(config)

    async def test_connection(self) -> IntegrationHealth:
        """Test Asana connection by fetching user info."""
        start_time = datetime.utcnow()
        try:
            result = await self._asana_request("GET", "/users/me")
            latency = (datetime.utcnow() - start_time).total_seconds() * 1000

            if result.get("status_code") == 200:
                self._status = IntegrationStatus.CONNECTED
                body = result.get("body", {}).get("data", {})
                return IntegrationHealth(
                    provider="asana",
                    status=IntegrationStatus.CONNECTED,
                    latency_ms=latency,
                    message="Connected successfully",
                    details={
                        "name": body.get("name"),
                        "email": body.get("email"),
                    },
                )
            elif result.get("status_code") == 401:
                self._status = IntegrationStatus.UNAUTHORIZED
                return IntegrationHealth(
                    provider="asana",
                    status=IntegrationStatus.UNAUTHORIZED,
                    message="Invalid token",
                )
            else:
                self._status = IntegrationStatus.ERROR
                return IntegrationHealth(
                    provider="asana",
                    status=IntegrationStatus.ERROR,
                    message=f"HTTP {result.get('status_code')}",
                )
        except Exception as exc:
            self.logger.exception("Asana connection test failed")
            self._status = IntegrationStatus.ERROR
            return IntegrationHealth(
                provider="asana",
                status=IntegrationStatus.ERROR,
                message=str(exc),
            )

    def get_available_actions(self) -> List[IntegrationAction]:
        """Return list of supported Asana actions."""
        return [
            IntegrationAction(
                name="list_workspaces",
                description="List all accessible workspaces",
                method="GET",
                parameters={},
            ),
            IntegrationAction(
                name="list_projects",
                description="List projects in a workspace",
                method="GET",
                parameters={"workspace_gid": "Workspace GID"},
            ),
            IntegrationAction(
                name="list_tasks",
                description="List tasks in a project",
                method="GET",
                parameters={"project_gid": "Project GID"},
            ),
            IntegrationAction(
                name="create_task",
                description="Create a new task",
                method="POST",
                parameters={
                    "workspace_gid": "Workspace GID",
                    "name": "Task name",
                    "notes": "Task notes (optional)",
                    "project_gid": "Project GID (optional)",
                },
            ),
            IntegrationAction(
                name="update_task",
                description="Update task details",
                method="PUT",
                parameters={
                    "task_gid": "Task GID",
                    "name": "New name (optional)",
                    "notes": "New notes (optional)",
                    "completed": "Completion status (optional)",
                },
            ),
        ]

    async def execute_action(
        self, action: str, params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Execute an Asana action."""
        action_map = {
            "list_workspaces": self._list_workspaces,
            "list_projects": self._list_projects,
            "list_tasks": self._list_tasks,
            "create_task": self._create_task,
            "update_task": self._update_task,
        }

        handler = action_map.get(action)
        if not handler:
            return {"error": f"Unknown action: {action}"}

        try:
            return await handler(params)
        except Exception as exc:
            self.logger.exception("Asana action %s failed", action)
            return {"error": str(exc)}

    async def _list_workspaces(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """List all accessible workspaces."""
        result = await self._asana_request("GET", "/workspaces")
        if result.get("status_code") == 200:
            data = result.get("body", {}).get("data", [])
            return {"workspaces": data}
        return {"error": f"HTTP {result.get('status_code')}"}

    async def _list_projects(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """List projects in a workspace."""
        workspace_gid = params.get("workspace_gid")
        if not workspace_gid:
            return {"error": "workspace_gid required"}

        endpoint = f"/workspaces/{workspace_gid}/projects"
        result = await self._asana_request("GET", endpoint)

        if result.get("status_code") == 200:
            data = result.get("body", {}).get("data", [])
            return {"projects": data}
        return {"error": f"HTTP {result.get('status_code')}"}

    async def _list_tasks(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """List tasks in a project."""
        project_gid = params.get("project_gid")
        if not project_gid:
            return {"error": "project_gid required"}

        endpoint = f"/projects/{project_gid}/tasks"
        result = await self._asana_request("GET", endpoint)

        if result.get("status_code") == 200:
            data = result.get("body", {}).get("data", [])
            return {"tasks": data}
        return {"error": f"HTTP {result.get('status_code')}"}

    async def _create_task(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new task."""
        workspace_gid = params.get("workspace_gid")
        name = params.get("name")

        if not workspace_gid or not name:
            return {"error": "workspace_gid and name required"}

        data = {"workspace": workspace_gid, "name": name}

        if "notes" in params:
            data["notes"] = params["notes"]
        if "project_gid" in params:
            data["projects"] = [params["project_gid"]]

        result = await self._asana_request("POST", "/tasks", json_data={"data": data})

        if result.get("status_code") == 201:
            task_data = result.get("body", {}).get("data", {})
            return {"task": task_data}
        return {"error": f"HTTP {result.get('status_code')}"}

    async def _update_task(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Update task details."""
        task_gid = params.get("task_gid")
        if not task_gid:
            return {"error": "task_gid required"}

        data = {}
        if "name" in params:
            data["name"] = params["name"]
        if "notes" in params:
            data["notes"] = params["notes"]
        if "completed" in params:
            data["completed"] = params["completed"]

        if not data:
            return {"error": "No update fields provided"}

        endpoint = f"/tasks/{task_gid}"
        result = await self._asana_request("PUT", endpoint, json_data={"data": data})

        if result.get("status_code") == 200:
            task_data = result.get("body", {}).get("data", {})
            return {"task": task_data}
        return {"error": f"HTTP {result.get('status_code')}"}

    async def _asana_request(
        self,
        method: str,
        endpoint: str,
        json_data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Make authenticated request to Asana API."""
        base_url = self.config.base_url or "https://app.asana.com/api/1.0"
        url = f"{base_url}{endpoint}"

        headers = {
            "Authorization": f"Bearer {self.config.token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        try:
            timeout = aiohttp.ClientTimeout(total=30.0)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.request(
                    method, url, headers=headers, json=json_data
                ) as resp:
                    body = await resp.json()
                    return {"status_code": resp.status, "body": body}
        except aiohttp.ClientError as exc:
            self.logger.warning("Asana request to %s failed: %s", url, exc)
            return {"status_code": 0, "error": str(exc)}
