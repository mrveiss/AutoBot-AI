# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss

"""CI/CD integration for Jenkins, GitLab CI, and CircleCI."""

import logging
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


class JenkinsIntegration(BaseIntegration):
    """Jenkins CI/CD integration."""

    def __init__(self, config: IntegrationConfig):
        """Initialize Jenkins integration.

        Args:
            config: Integration configuration with base_url, username, password
        """
        super().__init__(config)
        self.base_url = config.base_url.rstrip("/")
        self.auth = aiohttp.BasicAuth(config.username or "", config.password or "")

    async def test_connection(self) -> IntegrationHealth:
        """Test Jenkins connection.

        Returns:
            IntegrationHealth with status and details
        """
        try:
            async with aiohttp.ClientSession(auth=self.auth) as session:
                async with session.get(
                    f"{self.base_url}/api/json", timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        return IntegrationHealth(
                            status=IntegrationStatus.HEALTHY,
                            message="Connected to Jenkins successfully",
                            details={"version": data.get("version")},
                        )
                    return IntegrationHealth(
                        status=IntegrationStatus.UNHEALTHY,
                        message=f"Jenkins returned status {response.status}",
                        details={},
                    )
        except Exception as e:
            logger.exception("Jenkins connection test failed")
            return IntegrationHealth(
                status=IntegrationStatus.UNHEALTHY,
                message=f"Connection failed: {str(e)}",
                details={},
            )

    def get_available_actions(self) -> List[IntegrationAction]:
        """Get available Jenkins actions.

        Returns:
            List of available integration actions
        """
        return [
            IntegrationAction(
                name="list_jobs", description="List all Jenkins jobs", parameters={}
            ),
            IntegrationAction(
                name="get_build_status",
                description="Get status of a specific build",
                parameters={"job_name": "string", "build_number": "integer"},
            ),
            IntegrationAction(
                name="trigger_build",
                description="Trigger a new build",
                method="POST",
                parameters={"job_name": "string", "parameters": "object"},
            ),
            IntegrationAction(
                name="get_build_log",
                description="Get console output of a build",
                parameters={"job_name": "string", "build_number": "integer"},
            ),
        ]

    async def execute_action(
        self, action: str, params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Execute Jenkins action.

        Args:
            action: Action identifier
            params: Action parameters

        Returns:
            Action execution result
        """
        action_map = {
            "list_jobs": self._list_jobs,
            "get_build_status": self._get_build_status,
            "trigger_build": self._trigger_build,
            "get_build_log": self._get_build_log,
        }
        handler = action_map.get(action)
        if not handler:
            raise ValueError(f"Unknown action: {action}")
        return await handler(params)

    async def _list_jobs(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """List all Jenkins jobs."""
        async with aiohttp.ClientSession(auth=self.auth) as session:
            async with session.get(
                f"{self.base_url}/api/json?tree=jobs[name,url,color]"
            ) as response:
                response.raise_for_status()
                data = await response.json()
                return {"jobs": data.get("jobs", [])}

    async def _get_build_status(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Get Jenkins build status."""
        job_name = params["job_name"]
        build_number = params["build_number"]
        url = f"{self.base_url}/job/{job_name}/{build_number}/api/json"
        async with aiohttp.ClientSession(auth=self.auth) as session:
            async with session.get(url) as response:
                response.raise_for_status()
                return await response.json()

    async def _trigger_build(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Trigger Jenkins build."""
        job_name = params["job_name"]
        build_params = params.get("parameters", {})
        url = f"{self.base_url}/job/{job_name}/buildWithParameters"
        async with aiohttp.ClientSession(auth=self.auth) as session:
            async with session.post(url, json=build_params) as response:
                response.raise_for_status()
                return {"status": "triggered", "job_name": job_name}

    async def _get_build_log(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Get Jenkins build log."""
        job_name = params["job_name"]
        build_number = params["build_number"]
        url = f"{self.base_url}/job/{job_name}/{build_number}/consoleText"
        async with aiohttp.ClientSession(auth=self.auth) as session:
            async with session.get(url) as response:
                response.raise_for_status()
                log = await response.text()
                return {"log": log, "job_name": job_name, "build_number": build_number}


class GitLabCIIntegration(BaseIntegration):
    """GitLab CI/CD integration."""

    def __init__(self, config: IntegrationConfig):
        """Initialize GitLab CI integration.

        Args:
            config: Integration configuration with base_url and private_token
        """
        super().__init__(config)
        self.base_url = config.base_url.rstrip("/")
        self.token = config.token or ""
        self.headers = {"Private-Token": self.token}

    async def test_connection(self) -> IntegrationHealth:
        """Test GitLab connection.

        Returns:
            IntegrationHealth with status and details
        """
        try:
            async with aiohttp.ClientSession(headers=self.headers) as session:
                async with session.get(
                    f"{self.base_url}/api/v4/version",
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        return IntegrationHealth(
                            status=IntegrationStatus.HEALTHY,
                            message="Connected to GitLab successfully",
                            details={"version": data.get("version")},
                        )
                    return IntegrationHealth(
                        status=IntegrationStatus.UNHEALTHY,
                        message=f"GitLab returned status {response.status}",
                        details={},
                    )
        except Exception as e:
            logger.exception("GitLab connection test failed")
            return IntegrationHealth(
                status=IntegrationStatus.UNHEALTHY,
                message=f"Connection failed: {str(e)}",
                details={},
            )

    def get_available_actions(self) -> List[IntegrationAction]:
        """Get available GitLab CI actions.

        Returns:
            List of available integration actions
        """
        return [
            IntegrationAction(
                name="list_pipelines",
                description="List project pipelines",
                parameters={"project_id": "integer"},
            ),
            IntegrationAction(
                name="get_pipeline_status",
                description="Get status of a specific pipeline",
                parameters={"project_id": "integer", "pipeline_id": "integer"},
            ),
            IntegrationAction(
                name="trigger_pipeline",
                description="Trigger a new pipeline",
                method="POST",
                parameters={"project_id": "integer", "ref": "string"},
            ),
            IntegrationAction(
                name="list_jobs",
                description="List jobs in a pipeline",
                parameters={"project_id": "integer", "pipeline_id": "integer"},
            ),
        ]

    async def execute_action(
        self, action: str, params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Execute GitLab CI action.

        Args:
            action: Action identifier
            params: Action parameters

        Returns:
            Action execution result
        """
        action_map = {
            "list_pipelines": self._list_pipelines,
            "get_pipeline_status": self._get_pipeline_status,
            "trigger_pipeline": self._trigger_pipeline,
            "list_jobs": self._list_jobs,
        }
        handler = action_map.get(action)
        if not handler:
            raise ValueError(f"Unknown action: {action}")
        return await handler(params)

    async def _list_pipelines(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """List GitLab pipelines."""
        project_id = params["project_id"]
        url = f"{self.base_url}/api/v4/projects/{project_id}/pipelines"
        async with aiohttp.ClientSession(headers=self.headers) as session:
            async with session.get(url) as response:
                response.raise_for_status()
                pipelines = await response.json()
                return {"pipelines": pipelines}

    async def _get_pipeline_status(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Get GitLab pipeline status."""
        project_id = params["project_id"]
        pipeline_id = params["pipeline_id"]
        url = f"{self.base_url}/api/v4/projects/{project_id}/pipelines/{pipeline_id}"
        async with aiohttp.ClientSession(headers=self.headers) as session:
            async with session.get(url) as response:
                response.raise_for_status()
                return await response.json()

    async def _trigger_pipeline(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Trigger GitLab pipeline."""
        project_id = params["project_id"]
        ref = params["ref"]
        url = f"{self.base_url}/api/v4/projects/{project_id}/pipeline"
        async with aiohttp.ClientSession(headers=self.headers) as session:
            async with session.post(url, json={"ref": ref}) as response:
                response.raise_for_status()
                return await response.json()

    async def _list_jobs(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """List GitLab pipeline jobs."""
        project_id = params["project_id"]
        pipeline_id = params["pipeline_id"]
        url = (
            f"{self.base_url}/api/v4/projects/{project_id}/pipelines/{pipeline_id}/jobs"
        )
        async with aiohttp.ClientSession(headers=self.headers) as session:
            async with session.get(url) as response:
                response.raise_for_status()
                jobs = await response.json()
                return {"jobs": jobs}


class CircleCIIntegration(BaseIntegration):
    """CircleCI integration."""

    def __init__(self, config: IntegrationConfig):
        """Initialize CircleCI integration.

        Args:
            config: Integration configuration with base_url and circle_token
        """
        super().__init__(config)
        self.base_url = config.base_url.rstrip("/") or "https://circleci.com/api/v2"
        self.token = config.token or ""
        self.headers = {"Circle-Token": self.token}

    async def test_connection(self) -> IntegrationHealth:
        """Test CircleCI connection.

        Returns:
            IntegrationHealth with status and details
        """
        try:
            async with aiohttp.ClientSession(headers=self.headers) as session:
                async with session.get(
                    f"{self.base_url}/me", timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        return IntegrationHealth(
                            status=IntegrationStatus.HEALTHY,
                            message="Connected to CircleCI successfully",
                            details={"user": data.get("name")},
                        )
                    return IntegrationHealth(
                        status=IntegrationStatus.UNHEALTHY,
                        message=f"CircleCI returned status {response.status}",
                        details={},
                    )
        except Exception as e:
            logger.exception("CircleCI connection test failed")
            return IntegrationHealth(
                status=IntegrationStatus.UNHEALTHY,
                message=f"Connection failed: {str(e)}",
                details={},
            )

    def get_available_actions(self) -> List[IntegrationAction]:
        """Get available CircleCI actions.

        Returns:
            List of available integration actions
        """
        return [
            IntegrationAction(
                name="list_pipelines",
                description="List project pipelines",
                parameters={"project_slug": "string"},
            ),
            IntegrationAction(
                name="get_workflow_status",
                description="Get status of a specific workflow",
                parameters={"workflow_id": "string"},
            ),
            IntegrationAction(
                name="trigger_pipeline",
                description="Trigger a new pipeline",
                method="POST",
                parameters={"project_slug": "string", "branch": "string"},
            ),
        ]

    async def execute_action(
        self, action: str, params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Execute CircleCI action.

        Args:
            action: Action identifier
            params: Action parameters

        Returns:
            Action execution result
        """
        action_map = {
            "list_pipelines": self._list_pipelines,
            "get_workflow_status": self._get_workflow_status,
            "trigger_pipeline": self._trigger_pipeline,
        }
        handler = action_map.get(action)
        if not handler:
            raise ValueError(f"Unknown action: {action}")
        return await handler(params)

    async def _list_pipelines(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """List CircleCI pipelines."""
        project_slug = params["project_slug"]
        url = f"{self.base_url}/project/{project_slug}/pipeline"
        async with aiohttp.ClientSession(headers=self.headers) as session:
            async with session.get(url) as response:
                response.raise_for_status()
                data = await response.json()
                return {"pipelines": data.get("items", [])}

    async def _get_workflow_status(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Get CircleCI workflow status."""
        workflow_id = params["workflow_id"]
        url = f"{self.base_url}/workflow/{workflow_id}"
        async with aiohttp.ClientSession(headers=self.headers) as session:
            async with session.get(url) as response:
                response.raise_for_status()
                return await response.json()

    async def _trigger_pipeline(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Trigger CircleCI pipeline."""
        project_slug = params["project_slug"]
        branch = params.get("branch", "main")
        url = f"{self.base_url}/project/{project_slug}/pipeline"
        payload = {"branch": branch}
        async with aiohttp.ClientSession(headers=self.headers) as session:
            async with session.post(url, json=payload) as response:
                response.raise_for_status()
                return await response.json()
