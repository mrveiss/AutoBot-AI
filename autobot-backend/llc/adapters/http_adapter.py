# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""HttpAdapter — delegates agent runs to a remote HTTP endpoint (GH#8226).

adapter_config schema::

    {
        "url": "https://agent-runtime.example.com",
        "method": "POST",          # optional, default POST
        "headers": {},              # optional extra request headers
        "payload_template": "..."   # optional JSON template string
    }

Lifecycle endpoints (relative to ``url``):

* **invoke**: ``{method} {url}``  with ``context`` as JSON body
* **status**: ``GET {url}/status/{run_id}``
* **cancel**: ``POST {url}/cancel/{run_id}``

The ``run_id`` is the ``run_id`` field from the invoke response body.
"""

import json

import aiohttp

from autobot_shared.logging_manager import get_logger

from ..models.enums import LLCRunStatus
from .base import AdapterRunStatus

logger = get_logger(__name__)

_DEFAULT_TIMEOUT = aiohttp.ClientTimeout(total=None, connect=30)


class HttpAdapter:
    """Adapter that delegates agent runs to a remote HTTP service."""

    async def invoke(self, agent_config: dict, context: dict) -> str:
        url: str = agent_config["url"]
        method: str = agent_config.get("method", "POST").upper()
        headers: dict = agent_config.get("headers", {})
        payload_template: str | None = agent_config.get("payload_template")

        if payload_template:
            body = json.loads(payload_template.format(**context))
        else:
            body = context

        async with aiohttp.ClientSession(timeout=_DEFAULT_TIMEOUT) as session:
            async with session.request(method, url, json=body, headers=headers) as resp:
                resp.raise_for_status()
                data = await resp.json()

        run_id: str = data["run_id"]
        logger.info("HttpAdapter: invoked %s %s → run_id=%s", method, url, run_id)
        return run_id

    async def status(self, agent_config: dict, run_id: str) -> AdapterRunStatus:
        base_url: str = agent_config["url"].rstrip("/")
        headers: dict = agent_config.get("headers", {})

        status_url = f"{base_url}/status/{run_id}"
        async with aiohttp.ClientSession(timeout=_DEFAULT_TIMEOUT) as session:
            async with session.get(status_url, headers=headers) as resp:
                if resp.status == 404:
                    return AdapterRunStatus(status=LLCRunStatus.FAILED, error="run not found")
                resp.raise_for_status()
                data = await resp.json()

        raw_status: str = data.get("status", "failed")
        # Map remote vocabulary to LLCRunStatus; "succeeded" accepted for compat.
        _STATUS_MAP = {
            "running": LLCRunStatus.RUNNING,
            "succeeded": LLCRunStatus.COMPLETED,
            "completed": LLCRunStatus.COMPLETED,
            "failed": LLCRunStatus.FAILED,
            "timeout": LLCRunStatus.TIMEOUT,
            "cancelled": LLCRunStatus.CANCELLED,
        }
        run_status = _STATUS_MAP.get(raw_status, LLCRunStatus.FAILED)

        return AdapterRunStatus(
            status=run_status,
            exit_code=data.get("exit_code"),
            error=data.get("error"),
        )

    async def cancel(self, agent_config: dict, run_id: str) -> None:
        base_url: str = agent_config["url"].rstrip("/")
        headers: dict = agent_config.get("headers", {})

        cancel_url = f"{base_url}/cancel/{run_id}"
        async with aiohttp.ClientSession(timeout=_DEFAULT_TIMEOUT) as session:
            async with session.post(cancel_url, headers=headers) as resp:
                resp.raise_for_status()
        logger.info("HttpAdapter: cancelled run_id=%s at %s", run_id, cancel_url)
