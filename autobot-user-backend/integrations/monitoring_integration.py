# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss

"""Monitoring integrations for Datadog and New Relic.

This module provides integration classes for popular monitoring platforms,
enabling AutoBot to query metrics, monitors, and application health data.
"""

import logging
from datetime import datetime, timedelta
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


class DatadogIntegration(BaseIntegration):
    """Datadog monitoring integration.

    Supports querying monitors, metrics, hosts, and events from Datadog.
    Requires DD-API-KEY and DD-APPLICATION-KEY credentials.
    """

    def __init__(self, config: IntegrationConfig):
        """Initialize Datadog integration.

        Args:
            config: Integration configuration with api_key and app_key
        """
        super().__init__(config)
        self.base_url = "https://api.datadoghq.com/api/v1"
        self.api_key = config.api_key or ""
        self.app_key = config.extra.get("app_key", "")

    def _get_headers(self) -> Dict[str, str]:
        """Build request headers with authentication.

        Returns:
            Dict with DD-API-KEY and DD-APPLICATION-KEY headers
        """
        return {
            "DD-API-KEY": self.api_key,
            "DD-APPLICATION-KEY": self.app_key,
            "Content-Type": "application/json",
        }

    async def test_connection(self) -> IntegrationHealth:
        """Test Datadog API connection.

        Returns:
            IntegrationHealth with connection status and details
        """
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.base_url}/validate",
                    headers=self._get_headers(),
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        return IntegrationHealth(
                            status=IntegrationStatus.HEALTHY,
                            message="Datadog connection successful",
                            details={"valid": data.get("valid", True)},
                        )
                    else:
                        error_text = await response.text()
                        return IntegrationHealth(
                            status=IntegrationStatus.ERROR,
                            message=f"Datadog API error: {response.status}",
                            details={"error": error_text},
                        )
        except aiohttp.ClientError as e:
            logger.error("Datadog connection failed: %s", e)
            return IntegrationHealth(
                status=IntegrationStatus.ERROR,
                message=f"Connection failed: {str(e)}",
                details={"exception": type(e).__name__},
            )
        except Exception as e:
            logger.exception("Unexpected error testing Datadog connection")
            return IntegrationHealth(
                status=IntegrationStatus.ERROR,
                message=f"Unexpected error: {str(e)}",
                details={"exception": type(e).__name__},
            )

    def get_available_actions(self) -> List[IntegrationAction]:
        """Get list of available Datadog actions.

        Returns:
            List of IntegrationAction objects
        """
        return [
            IntegrationAction(
                name="list_monitors",
                description="List all Datadog monitors",
                parameters={},
            ),
            IntegrationAction(
                name="get_metrics",
                description="Query metrics from Datadog",
                parameters={
                    "query": "string",
                    "from_time": "int (unix timestamp)",
                    "to_time": "int (unix timestamp)",
                },
            ),
            IntegrationAction(
                name="list_hosts",
                description="List all monitored hosts",
                parameters={},
            ),
            IntegrationAction(
                name="get_events",
                description="Get recent events",
                parameters={
                    "start": "int (unix timestamp)",
                    "end": "int (unix timestamp)",
                },
            ),
            IntegrationAction(
                name="create_monitor",
                description="Create a new monitor",
                parameters={
                    "type": "string",
                    "query": "string",
                    "name": "string",
                    "message": "string",
                },
            ),
        ]

    async def execute_action(
        self, action: str, params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Execute a Datadog action.

        Args:
            action: Action name to execute
            params: Action parameters

        Returns:
            Dict with action result

        Raises:
            ValueError: If action is not supported
        """
        action_map = {
            "list_monitors": self._list_monitors,
            "get_metrics": self._get_metrics,
            "list_hosts": self._list_hosts,
            "get_events": self._get_events,
            "create_monitor": self._create_monitor,
        }

        handler = action_map.get(action)
        if not handler:
            raise ValueError(f"Unsupported action: {action}")

        return await handler(params)

    async def _list_monitors(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """List all Datadog monitors."""
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{self.base_url}/monitor",
                headers=self._get_headers(),
                timeout=aiohttp.ClientTimeout(total=30),
            ) as response:
                response.raise_for_status()
                monitors = await response.json()
                return {"monitors": monitors, "count": len(monitors)}

    async def _get_metrics(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Query metrics from Datadog."""
        query = params.get("query", "")
        to_time = params.get("to_time", int(datetime.now().timestamp()))
        from_time = params.get(
            "from_time", int((datetime.now() - timedelta(hours=1)).timestamp())
        )

        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{self.base_url}/query",
                headers=self._get_headers(),
                params={"query": query, "from": from_time, "to": to_time},
                timeout=aiohttp.ClientTimeout(total=30),
            ) as response:
                response.raise_for_status()
                return await response.json()

    async def _list_hosts(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """List all monitored hosts."""
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{self.base_url}/hosts",
                headers=self._get_headers(),
                timeout=aiohttp.ClientTimeout(total=30),
            ) as response:
                response.raise_for_status()
                data = await response.json()
                return {
                    "hosts": data.get("host_list", []),
                    "total": data.get("total_matching", 0),
                }

    async def _get_events(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Get recent events from Datadog."""
        end = params.get("end", int(datetime.now().timestamp()))
        start = params.get(
            "start", int((datetime.now() - timedelta(hours=1)).timestamp())
        )

        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{self.base_url}/events",
                headers=self._get_headers(),
                params={"start": start, "end": end},
                timeout=aiohttp.ClientTimeout(total=30),
            ) as response:
                response.raise_for_status()
                data = await response.json()
                return {"events": data.get("events", [])}

    async def _create_monitor(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new Datadog monitor."""
        monitor_data = {
            "type": params.get("type", "metric alert"),
            "query": params["query"],
            "name": params["name"],
            "message": params.get("message", ""),
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.base_url}/monitor",
                headers=self._get_headers(),
                json=monitor_data,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as response:
                response.raise_for_status()
                return await response.json()


class NewRelicIntegration(BaseIntegration):
    """New Relic monitoring integration.

    Supports querying applications, metrics via NRQL, alerts, and health.
    Requires Api-Key credential.
    """

    def __init__(self, config: IntegrationConfig):
        """Initialize New Relic integration.

        Args:
            config: Integration configuration with api_key
        """
        super().__init__(config)
        self.base_url = "https://api.newrelic.com/v2"
        self.graphql_url = "https://api.newrelic.com/graphql"
        self.api_key = config.api_key or ""
        self.account_id = config.extra.get("account_id", "")

    def _get_headers(self) -> Dict[str, str]:
        """Build request headers with authentication.

        Returns:
            Dict with Api-Key header
        """
        return {
            "Api-Key": self.api_key,
            "Content-Type": "application/json",
        }

    async def test_connection(self) -> IntegrationHealth:
        """Test New Relic API connection.

        Returns:
            IntegrationHealth with connection status and details
        """
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.base_url}/applications.json",
                    headers=self._get_headers(),
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        return IntegrationHealth(
                            status=IntegrationStatus.HEALTHY,
                            message="New Relic connection successful",
                            details={"applications": len(data.get("applications", []))},
                        )
                    else:
                        error_text = await response.text()
                        return IntegrationHealth(
                            status=IntegrationStatus.ERROR,
                            message=f"New Relic API error: {response.status}",
                            details={"error": error_text},
                        )
        except aiohttp.ClientError as e:
            logger.error("New Relic connection failed: %s", e)
            return IntegrationHealth(
                status=IntegrationStatus.ERROR,
                message=f"Connection failed: {str(e)}",
                details={"exception": type(e).__name__},
            )
        except Exception as e:
            logger.exception("Unexpected error testing New Relic connection")
            return IntegrationHealth(
                status=IntegrationStatus.ERROR,
                message=f"Unexpected error: {str(e)}",
                details={"exception": type(e).__name__},
            )

    def get_available_actions(self) -> List[IntegrationAction]:
        """Get list of available New Relic actions.

        Returns:
            List of IntegrationAction objects
        """
        return [
            IntegrationAction(
                name="list_applications",
                description="List all monitored applications",
                parameters={},
            ),
            IntegrationAction(
                name="get_metrics",
                description="Query metrics using NRQL",
                parameters={
                    "nrql": "string",
                    "since": "string (e.g., '1 hour ago')",
                },
            ),
            IntegrationAction(
                name="list_alerts",
                description="List alert policies and conditions",
                parameters={},
            ),
            IntegrationAction(
                name="get_app_health",
                description="Get application health status",
                parameters={"app_id": "int"},
            ),
        ]

    async def execute_action(
        self, action: str, params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Execute a New Relic action.

        Args:
            action: Action name to execute
            params: Action parameters

        Returns:
            Dict with action result

        Raises:
            ValueError: If action is not supported
        """
        action_map = {
            "list_applications": self._list_applications,
            "get_metrics": self._get_metrics,
            "list_alerts": self._list_alerts,
            "get_app_health": self._get_app_health,
        }

        handler = action_map.get(action)
        if not handler:
            raise ValueError(f"Unsupported action: {action}")

        return await handler(params)

    async def _list_applications(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """List all monitored applications."""
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{self.base_url}/applications.json",
                headers=self._get_headers(),
                timeout=aiohttp.ClientTimeout(total=30),
            ) as response:
                response.raise_for_status()
                data = await response.json()
                apps = data.get("applications", [])
                return {"applications": apps, "count": len(apps)}

    async def _get_metrics(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Query metrics using NRQL."""
        nrql = params.get("nrql", "")
        since = params.get("since", "1 hour ago")

        query = f"{nrql} SINCE {since}"
        graphql_query = {
            "query": """
                query($accountId: Int!, $nrql: Nrql!) {
                    actor {
                        account(id: $accountId) {
                            nrql(query: $nrql) {
                                results
                            }
                        }
                    }
                }
            """,
            "variables": {
                "accountId": int(self.account_id),
                "nrql": query,
            },
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(
                self.graphql_url,
                headers=self._get_headers(),
                json=graphql_query,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as response:
                response.raise_for_status()
                data = await response.json()
                results = (
                    data.get("data", {})
                    .get("actor", {})
                    .get("account", {})
                    .get("nrql", {})
                    .get("results", [])
                )
                return {"results": results, "count": len(results)}

    async def _list_alerts(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """List alert policies and conditions."""
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{self.base_url}/alerts_policies.json",
                headers=self._get_headers(),
                timeout=aiohttp.ClientTimeout(total=30),
            ) as response:
                response.raise_for_status()
                data = await response.json()
                policies = data.get("policies", [])
                return {"policies": policies, "count": len(policies)}

    async def _get_app_health(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Get application health status."""
        app_id = params.get("app_id")
        if not app_id:
            raise ValueError("app_id is required")

        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{self.base_url}/applications/{app_id}.json",
                headers=self._get_headers(),
                timeout=aiohttp.ClientTimeout(total=30),
            ) as response:
                response.raise_for_status()
                data = await response.json()
                app = data.get("application", {})
                return {
                    "id": app.get("id"),
                    "name": app.get("name"),
                    "health_status": app.get("health_status"),
                    "reporting": app.get("reporting"),
                    "summary": app.get("application_summary", {}),
                }
