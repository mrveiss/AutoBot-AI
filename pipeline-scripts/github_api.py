# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The one GitHub REST client for the CI pipeline scripts (#15411).

``GitHubApi`` used to live inside ``ci_dispatch_watchdog.py``, a module frozen at its
#14236 size ceiling, so the shared client could not gain a method. It lives here so it
can, and ``build_api()`` is the one place the environment becomes a client. Stdlib only,
reached by path like its siblings. ``ci_dispatch_watchdog`` re-exports the names below
for the callers that still import them from there.
"""

from __future__ import annotations

import json
import os
import socket
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
from header_safe_secret import require_header_safe  # noqa: E402  # #15204

# Transport failure -- no HTTP status was ever received.
NO_RESPONSE_STATUS = 0

DEFAULT_API_ROOT = "https://api.github.com"
DEFAULT_REQUEST_TIMEOUT_SECONDS = 30

# Rate-limit backoff (#19522): a 429, or a 403 that is a primary or secondary rate limit, is
# retried after the wait GitHub names (Retry-After, else x-ratelimit-reset, else the documented
# one minute for a secondary limit), at most RATE_LIMIT_RETRIES times, each wait capped.
RATE_LIMIT_RETRIES = 2
RATE_LIMIT_MAX_WAIT_SECONDS = 90.0
SECONDARY_LIMIT_WAIT_SECONDS = 60.0

# The author_association values that mean a maintainer of the repository (#19520, #19522).
TRUSTED_ASSOCIATIONS = frozenset({"OWNER", "MEMBER", "COLLABORATOR"})


class WatchdogError(RuntimeError):
    """Base for every error this module raises deliberately."""


class WatchdogConfigError(WatchdogError):
    """Raised when required environment configuration is absent or unusable."""


class WatchdogApiError(WatchdogError):
    """
    Raised when the API answered with something unusable.

    This is deliberately distinct from "the API answered and said there are no
    runs". Conflating the two is how a single rate-limit window turns into
    "CI never dispatched" printed against every open pull request.
    """


def _decode_error_body(exc: urllib.error.HTTPError) -> Any:
    body = exc.read().decode("utf-8", errors="replace")
    try:
        return json.loads(body) if body else None
    except json.JSONDecodeError:
        return {"message": body}


def _header(headers: Any, name: str) -> Optional[str]:
    value = headers.get(name) if headers is not None else None
    return str(value).strip() if value is not None else None


def rate_limit_wait(status: int, body: Any, headers: Any, now: float) -> Optional[float]:
    """Seconds to wait before retrying a rate-limited answer, or None when it is not one.

    429 always is. A 403 is only when GitHub says so: Retry-After, an exhausted
    x-ratelimit-remaining, or a "rate limit" message (the secondary limit). Any other
    403 is a permission answer and is returned at once.
    """
    message = str(body.get("message", "")) if isinstance(body, dict) else ""
    retry_after = _header(headers, "Retry-After")
    exhausted = _header(headers, "x-ratelimit-remaining") == "0"
    if status != 429 and not (status == 403 and (retry_after or exhausted or "rate limit" in message.lower())):
        return None
    if retry_after and retry_after.isdigit():
        return float(retry_after)
    reset = _header(headers, "x-ratelimit-reset")
    if exhausted and reset and reset.isdigit():
        return max(float(reset) - now, 1.0)
    return SECONDARY_LIMIT_WAIT_SECONDS


class GitHubApi:
    """Minimal GitHub REST client — stdlib only, no extra CI dependency."""

    def __init__(
        self,
        token: str,
        repository: str,
        api_root: str = DEFAULT_API_ROOT,
        timeout: int = DEFAULT_REQUEST_TIMEOUT_SECONDS,
    ) -> None:
        # #15204: validated here as well as in load_config, because this is the
        # object that hands the value to the HTTP layer. Direct construction --
        # a test, a future caller -- must not be the path that leaks.
        self.token = require_header_safe(token, "GITHUB_TOKEN", WatchdogConfigError)
        self.repository = repository
        self.api_root = api_root.rstrip("/")
        self.timeout = timeout
        # #19548: the last response's headers, so a caller can honour a
        # secondary-rate-limit ``Retry-After`` without a second transport.
        self.last_headers: Dict[str, str] = {}

    def request(self, method: str, path: str, payload: Optional[Dict[str, Any]] = None) -> Tuple[int, Any]:
        """
        Issue a request and return ``(status_code, decoded_body)``.

        A transport failure (DNS, TLS, connection reset, timeout) returns status
        ``NO_RESPONSE_STATUS`` rather than escaping as a traceback. An uncaught
        ``URLError`` would exit the process with code 1, which this module
        documents as "parked runs could not be approved" — a completely
        different condition, reported with no remediation text.

        A rate-limited answer is retried after the wait GitHub asks for (see
        ``rate_limit_wait``); the last answer is returned when retries run out.
        """
        for attempt in range(RATE_LIMIT_RETRIES + 1):
            status, body, headers = self._send(method, path, payload)
            wait = rate_limit_wait(status, body, headers, time.time())
            if wait is None or attempt == RATE_LIMIT_RETRIES:
                return status, body
            self.sleep(min(wait, RATE_LIMIT_MAX_WAIT_SECONDS))
        return status, body

    @staticmethod
    def sleep(seconds: float) -> None:
        time.sleep(seconds)

    def _send(self, method: str, path: str, payload: Optional[Dict[str, Any]]) -> Tuple[int, Any, Any]:
        """One attempt: ``(status, decoded body, response headers or None)``."""
        url = path if path.startswith("http") else f"{self.api_root}/{path.lstrip('/')}"
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        request = urllib.request.Request(url=url, method=method, data=data)
        request.add_header("Authorization", f"Bearer {self.token}")
        request.add_header("Accept", "application/vnd.github+json")
        request.add_header("X-GitHub-Api-Version", "2022-11-28")
        if data is not None:
            request.add_header("Content-Type", "application/json")
        self.last_headers = {}
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:  # noqa: S310 - fixed api host
                self.last_headers = {k.lower(): v for k, v in response.headers.items()}
                body = response.read().decode("utf-8")
                return response.status, (json.loads(body) if body else None), None
        except urllib.error.HTTPError as exc:
            self.last_headers = {k.lower(): v for k, v in (exc.headers or {}).items()}
            return exc.code, _decode_error_body(exc), exc.headers
        except (urllib.error.URLError, socket.timeout, OSError) as exc:
            return NO_RESPONSE_STATUS, {"message": f"transport failure: {exc}"}, None

    def _list_runs(self, params: Dict[str, str], context: str) -> List[Dict[str, Any]]:
        query = urllib.parse.urlencode(params)
        status, body = self.request("GET", f"/repos/{self.repository}/actions/runs?{query}")
        if status != 200 or not isinstance(body, dict):
            raise WatchdogApiError(f"cannot list {context} (HTTP {status}): {body}")
        return list(body.get("workflow_runs") or [])

    def open_pull_requests(self, base: str) -> List[Dict[str, Any]]:
        query = urllib.parse.urlencode({"state": "open", "base": base, "per_page": "100"})
        status, body = self.request("GET", f"/repos/{self.repository}/pulls?{query}")
        if status != 200 or not isinstance(body, list):
            raise WatchdogApiError(f"cannot list open PRs (HTTP {status}): {body}")
        return body

    def runs_for_sha(self, sha: str) -> List[Dict[str, Any]]:
        """
        Runs attached to one head commit.

        Raises rather than returning ``[]`` on an API error: an empty list is
        interpreted downstream as "CI never dispatched", which is a specific and
        alarming claim that must never be made on the strength of a rate-limit
        response.
        """
        return self._list_runs({"head_sha": sha, "per_page": "100"}, f"runs for {sha[:12]}")

    def recent_runs(self, per_page: int = 100, run_status: str = "") -> List[Dict[str, Any]]:
        params = {"per_page": str(per_page)}
        if run_status:
            params["status"] = run_status
        return self._list_runs(params, f"recent runs (status={run_status or 'any'})")

    def run_jobs(self, run_id: int) -> List[Dict[str, Any]]:
        query = urllib.parse.urlencode({"per_page": "100"})
        status, body = self.request("GET", f"/repos/{self.repository}/actions/runs/{run_id}/jobs?{query}")
        if status != 200 or not isinstance(body, dict):
            raise WatchdogApiError(f"cannot list jobs for run {run_id} (HTTP {status}): {body}")
        return list(body.get("jobs") or [])

    def approve_run(self, run_id: int) -> Tuple[int, str]:
        status, body = self.request("POST", f"/repos/{self.repository}/actions/runs/{run_id}/approve")
        message = ""
        if isinstance(body, dict):
            message = str(body.get("message", ""))
        return status, message

    def rerun_run(self, run_id: int) -> Tuple[int, str]:
        """Re-dispatch a run.

        ``rerun-failed-jobs`` rather than ``rerun``: a run that never dispatched has
        exactly one failed job and nothing worth repeating, and on a partly
        successful run this avoids paying again for the jobs that passed. GitHub
        rejects the request on state grounds if the run is not re-runnable, which is
        returned rather than raised.
        """
        status, body = self.request("POST", f"/repos/{self.repository}/actions/runs/{run_id}/rerun-failed-jobs")
        message = str(body.get("message", "")) if isinstance(body, dict) else ""
        return status, message

    def rate_limit_remaining(self) -> int:
        """Remaining core REST budget, or -1 when it cannot be read.

        Inside Actions the GITHUB_TOKEN budget is 1,000/hour per repository, not the
        5,000 a PAT gets. -1 means "unknown", which callers must treat as "do not
        spend" rather than as headroom.
        """
        status, body = self.request("GET", "/rate_limit")
        if status != 200 or not isinstance(body, dict):
            return -1
        core = (body.get("resources") or {}).get("core") or {}
        remaining = core.get("remaining")
        return int(remaining) if isinstance(remaining, int) else -1

    def set_status(self, sha: str, state: str, context: str, description: str, target_url: str) -> int:
        payload: Dict[str, Any] = {
            "state": state,
            "context": context,
            "description": description,
        }
        if target_url:
            payload["target_url"] = target_url
        status, _ = self.request("POST", f"/repos/{self.repository}/statuses/{sha}", payload)
        return status


def build_api(timeout: int = DEFAULT_REQUEST_TIMEOUT_SECONDS) -> GitHubApi:
    """The client for ``GITHUB_TOKEN`` / ``GITHUB_REPOSITORY`` / ``GITHUB_API_URL``."""
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    repository = os.environ.get("GITHUB_REPOSITORY", "").strip()
    if not token:
        raise WatchdogConfigError("GITHUB_TOKEN is required")
    if "/" not in repository:
        raise WatchdogConfigError("GITHUB_REPOSITORY must be 'owner/repo'")
    api_root = os.environ.get("GITHUB_API_URL", DEFAULT_API_ROOT).strip() or DEFAULT_API_ROOT
    return GitHubApi(token, repository, api_root, timeout)
