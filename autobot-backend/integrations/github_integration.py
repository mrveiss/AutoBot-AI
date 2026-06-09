# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
GitHub API Integration (Issues #4097, #4162)

Provides access to pull requests, issues, reviews, repository structure,
and commits via the GitHub REST API v3.  All API calls are guarded by
the IntegrationRateLimiter (5000 req/hr per token, 90 req/min local
window) with automatic Retry-After and X-RateLimit-Reset handling.
"""

import asyncio
import time
from typing import Any, Dict, List

import aiohttp

from autobot_shared.logging_manager import get_logger
from autobot_shared.time_utils import now_utc
from integrations.base import (
    BaseIntegration,
    IntegrationAction,
    IntegrationConfig,
    IntegrationHealth,
    IntegrationStatus,
)
from integrations.rate_limiter import (
    GITHUB_REQUESTS_PER_HOUR,
    GITHUB_REQUESTS_PER_MINUTE,
    IntegrationRateLimiter,
)
from integrations.rate_limiter import integration_rate_limiter as _shared_rate_limiter

logger = get_logger(__name__)

# In-memory limiter retained solely for apply_response_headers() (Retry-After /
# X-RateLimit-* header parsing).  Distributed acquire() uses _shared_rate_limiter
# so quota state is shared across all backend workers (Issue #6311).
_GITHUB_RATE_LIMITER = IntegrationRateLimiter(
    requests_per_minute=GITHUB_REQUESTS_PER_MINUTE,
    requests_per_hour=GITHUB_REQUESTS_PER_HOUR,
)


class GitHubIntegration(BaseIntegration):
    """GitHub REST API v3 integration.

    Authentication: Personal Access Token (PAT) or GitHub App installation
    token passed as ``api_key`` in the config.  Unauthenticated requests
    receive a 60 req/hr limit; authenticated ones get 5 000 req/hr.

    Rate limiting:
    - Local sliding-window: 90 req/min, 5 000 req/hr per token
    - Response-header tracking: X-RateLimit-Remaining / X-RateLimit-Reset
    - Retry-After enforcement on HTTP 403 (secondary limit) / HTTP 429
    - Exponential back-off for transient 5xx errors (max 3 retries)
    """

    _RETRY_STATUS_CODES = {500, 502, 503, 504}
    _MAX_RETRIES = 3

    def __init__(self, config: IntegrationConfig) -> None:
        super().__init__(config)
        self.base_url = (config.base_url or "https://api.github.com").rstrip("/")
        self._rate_limiter = _GITHUB_RATE_LIMITER
        self._token_key = config.api_key or "unauthenticated"

    @property
    def _auth_headers(self) -> Dict[str, str]:
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"
        return headers

    async def test_connection(self) -> IntegrationHealth:
        """Test GitHub API connectivity by fetching the authenticated user."""
        start = time.monotonic()
        try:
            result = await self._github_request("GET", "/user")
        except asyncio.TimeoutError:
            return IntegrationHealth(
                provider="github",
                status=IntegrationStatus.ERROR,
                message="Request timed out",
                last_checked=now_utc(),
            )

        latency_ms = (time.monotonic() - start) * 1000
        status_code = result.get("status_code", 0)
        body = result.get("body", {})

        if status_code == 200:
            self._status = IntegrationStatus.CONNECTED
            return IntegrationHealth(
                provider="github",
                status=IntegrationStatus.CONNECTED,
                latency_ms=latency_ms,
                message=f"Connected as {body.get('login')}",
                last_checked=now_utc(),
                details={
                    "login": body.get("login"),
                    "type": body.get("type"),
                },
            )
        if status_code == 401:
            self._status = IntegrationStatus.UNAUTHORIZED
            return IntegrationHealth(
                provider="github",
                status=IntegrationStatus.UNAUTHORIZED,
                latency_ms=latency_ms,
                message="Invalid or expired token",
                last_checked=now_utc(),
            )
        self._status = IntegrationStatus.ERROR
        return IntegrationHealth(
            provider="github",
            status=IntegrationStatus.ERROR,
            latency_ms=latency_ms,
            message=f"HTTP {status_code}: {body.get('message', 'Unknown error')}",
            last_checked=now_utc(),
        )

    def get_available_actions(self) -> List[IntegrationAction]:
        """Return the list of supported GitHub actions."""
        return [
            IntegrationAction(
                name="get_pull_request",
                description="Fetch a pull request and its diff",
                method="GET",
                parameters={"owner": "str", "repo": "str", "pull_number": "int"},
            ),
            IntegrationAction(
                name="list_pull_requests",
                description="List open pull requests for a repository",
                method="GET",
                parameters={"owner": "str", "repo": "str", "state": "str"},
            ),
            IntegrationAction(
                name="list_issues",
                description="List issues for a repository",
                method="GET",
                parameters={"owner": "str", "repo": "str", "state": "str"},
            ),
            IntegrationAction(
                name="get_issue",
                description="Fetch a single issue by number",
                method="GET",
                parameters={"owner": "str", "repo": "str", "issue_number": "int"},
            ),
            IntegrationAction(
                name="post_comment",
                description="Post a comment on a PR or issue",
                method="POST",
                parameters={
                    "owner": "str",
                    "repo": "str",
                    "issue_number": "int",
                    "body": "str",
                },
            ),
            IntegrationAction(
                name="list_commits",
                description="List recent commits for a branch",
                method="GET",
                parameters={
                    "owner": "str",
                    "repo": "str",
                    "sha": "str",
                    "per_page": "int",
                },
            ),
            IntegrationAction(
                name="get_repository",
                description="Fetch repository metadata",
                method="GET",
                parameters={"owner": "str", "repo": "str"},
            ),
        ]

    async def execute_action(self, action: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a named GitHub action."""
        action_map = {
            "get_pull_request": self._get_pull_request,
            "list_pull_requests": self._list_pull_requests,
            "list_issues": self._list_issues,
            "get_issue": self._get_issue,
            "post_comment": self._post_comment,
            "list_commits": self._list_commits,
            "get_repository": self._get_repository,
        }
        handler = action_map.get(action)
        if not handler:
            return {"error": f"Unknown action: {action}"}
        return await handler(params)

    # ------------------------------------------------------------------
    # Action implementations
    # ------------------------------------------------------------------

    async def _get_pull_request(self, params: Dict[str, Any]) -> Dict[str, Any]:
        owner, repo = params["owner"], params["repo"]
        number = params["pull_number"]
        result = await self._github_request("GET", f"/repos/{owner}/{repo}/pulls/{number}")
        return result.get("body", {})

    async def _list_pull_requests(self, params: Dict[str, Any]) -> Dict[str, Any]:
        owner, repo = params["owner"], params["repo"]
        state = params.get("state", "open")
        result = await self._github_request(
            "GET",
            f"/repos/{owner}/{repo}/pulls",
            query_params={"state": state, "per_page": 50},
        )
        prs = result.get("body", [])
        return {"pull_requests": prs, "count": len(prs)}

    async def _list_issues(self, params: Dict[str, Any]) -> Dict[str, Any]:
        owner, repo = params["owner"], params["repo"]
        state = params.get("state", "open")
        result = await self._github_request(
            "GET",
            f"/repos/{owner}/{repo}/issues",
            query_params={"state": state, "per_page": 50},
        )
        issues = result.get("body", [])
        return {"issues": issues, "count": len(issues)}

    async def _get_issue(self, params: Dict[str, Any]) -> Dict[str, Any]:
        owner, repo = params["owner"], params["repo"]
        number = params["issue_number"]
        result = await self._github_request("GET", f"/repos/{owner}/{repo}/issues/{number}")
        return result.get("body", {})

    async def _post_comment(self, params: Dict[str, Any]) -> Dict[str, Any]:
        owner, repo = params["owner"], params["repo"]
        number = params["issue_number"]
        result = await self._github_request(
            "POST",
            f"/repos/{owner}/{repo}/issues/{number}/comments",
            json_data={"body": params["body"]},
        )
        return result.get("body", {})

    async def _list_commits(self, params: Dict[str, Any]) -> Dict[str, Any]:
        owner, repo = params["owner"], params["repo"]
        query: Dict[str, Any] = {"per_page": params.get("per_page", 20)}
        if "sha" in params:
            query["sha"] = params["sha"]
        result = await self._github_request("GET", f"/repos/{owner}/{repo}/commits", query_params=query)
        commits = result.get("body", [])
        return {"commits": commits, "count": len(commits)}

    async def _get_repository(self, params: Dict[str, Any]) -> Dict[str, Any]:
        owner, repo = params["owner"], params["repo"]
        result = await self._github_request("GET", f"/repos/{owner}/{repo}")
        return result.get("body", {})

    # ------------------------------------------------------------------
    # Core HTTP helper with rate limiting and retry logic
    # ------------------------------------------------------------------

    async def _github_request(
        self,
        method: str,
        path: str,
        query_params: Dict[str, Any] | None = None,
        json_data: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        """Rate-limited HTTP request to the GitHub REST API.

        - Checks local sliding-window quota before sending.
        - Reads X-RateLimit-* headers after each response.
        - Handles HTTP 403 (secondary rate limit) and 429 with Retry-After.
        - Retries on transient 5xx errors (exponential back-off, max 3×).
        - Never raises on HTTP errors; returns structured dict instead.
        """
        url = f"{self.base_url}{path}"

        # Acquire rate-limit slot via the shared Redis-backed limiter (Issue #6311).
        # Falls back to allow-all when Redis is unavailable.
        allowed = await _shared_rate_limiter.acquire(
            self._token_key,
            requests_per_minute=GITHUB_REQUESTS_PER_MINUTE,
            requests_per_hour=GITHUB_REQUESTS_PER_HOUR,
        )
        if not allowed:
            logger.error("GitHub rate limit exceeded for %s %s", method, path)
            return {
                "status_code": 429,
                "body": {"message": "Rate limit exceeded"},
                "error": "rate_limit_exceeded",
            }

        last_result: Dict[str, Any] = {}
        for attempt in range(self._MAX_RETRIES + 1):
            try:
                timeout = aiohttp.ClientTimeout(total=30.0)
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.request(
                        method,
                        url,
                        headers=self._auth_headers,
                        params=query_params,
                        json=json_data,
                    ) as resp:
                        resp_headers = dict(resp.headers)
                        body = await resp.json(content_type=None)
                        last_result = {
                            "status_code": resp.status,
                            "body": body,
                            "headers": resp_headers,
                        }

                        # Always update rate limit state from headers
                        self._rate_limiter.apply_response_headers(self._token_key, resp_headers, service="github")

                        if resp.status == 403:
                            retry_after = resp_headers.get("Retry-After") or resp_headers.get("retry-after")
                            if retry_after:
                                self._rate_limiter.apply_response_headers(
                                    self._token_key,
                                    {"Retry-After": retry_after},
                                    service="github",
                                )
                            msg = body.get("message", "")
                            logger.warning("GitHub 403 for %s %s: %s", method, path, msg)
                            return last_result

                        if resp.status == 429:
                            retry_after = resp_headers.get("Retry-After") or resp_headers.get("retry-after", "60")
                            wait = float(retry_after)
                            logger.warning("GitHub 429 for %s %s — waiting %.1fs", method, path, wait)
                            self._rate_limiter.apply_response_headers(
                                self._token_key,
                                {"Retry-After": str(wait)},
                                service="github",
                            )
                            if attempt < self._MAX_RETRIES:
                                await asyncio.sleep(min(wait, 120.0))
                                continue
                            return last_result

                        if resp.status in self._RETRY_STATUS_CODES:
                            if attempt < self._MAX_RETRIES:
                                backoff = 2.0**attempt
                                logger.warning(
                                    "GitHub %d for %s %s — retrying in %.1fs (attempt %d/%d)",
                                    resp.status,
                                    method,
                                    path,
                                    backoff,
                                    attempt + 1,
                                    self._MAX_RETRIES,
                                )
                                await asyncio.sleep(backoff)
                                continue

                        return last_result

            except asyncio.TimeoutError:
                logger.warning("GitHub request timed out: %s %s", method, path)
                return {
                    "status_code": 0,
                    "body": {"message": "Request timed out"},
                    "error": "timeout",
                }
            except aiohttp.ClientConnectionError as exc:
                logger.warning("GitHub connection error for %s %s: %s", method, path, exc)
                return {
                    "status_code": 0,
                    "body": {"message": "integration_error"},
                    "error": "connection_error",
                }
            except aiohttp.ClientError as exc:
                logger.warning("GitHub request error for %s %s: %s", method, path, exc)
                return {
                    "status_code": 0,
                    "body": {"message": "integration_error"},
                    "error": "client_error",
                }

        return last_result
