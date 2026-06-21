# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Video-generation provider abstraction — GH#9016.

Defines the async provider contract used by both the generate_video tool and
the /video-generation API:

    submit(prompt, ...) -> job_id          (queue a generation task)
    poll(job_id)        -> JobStatus       (check progress / fetch URL)

Each provider is credential-gated: an unset/empty API key means the provider is
disabled (``available`` is False) and submit/poll raise ProviderError.

Providers shipped:
    * RunwayProvider — Runway ML developer API (Gen-3/Gen-4). Baseline, working.
    * SoraProvider   — OpenAI Sora. Registered; credential-gated (SORA_API_KEY).
    * KlingProvider  — Kling AI. Registered; credential-gated (KLING_API_KEY).

All HTTP is async (aiohttp). No blocking calls on the event loop.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# Runway developer API base + version header (stable public API surface).
RUNWAY_API_BASE = "https://api.dev.runwayml.com/v1"
RUNWAY_API_VERSION = "2024-11-06"


class ProviderError(Exception):
    """Raised when a provider call fails (auth, quota, network, or API error)."""


@dataclass
class JobStatus:
    """Normalized status of a video-generation job, provider-agnostic."""

    job_id: str
    status: str  # one of: pending | running | succeeded | failed
    progress: float = 0.0  # 0.0 .. 1.0
    video_url: Optional[str] = None
    error: Optional[str] = None
    provider: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "job_id": self.job_id,
            "status": self.status,
            "progress": round(self.progress, 3),
            "video_url": self.video_url,
            "error": self.error,
            "provider": self.provider,
            "metadata": self.metadata,
        }


class BaseVideoProvider:
    """Async contract every video-generation provider implements."""

    name: str = "base"
    env_var: str = ""

    def __init__(self, api_key: Optional[str] = None) -> None:
        self._api_key = api_key if api_key is not None else os.environ.get(self.env_var, "")

    @property
    def available(self) -> bool:
        """True when an API key is configured (empty key == disabled)."""
        return bool(self._api_key)

    def _require_key(self) -> str:
        if not self._api_key:
            raise ProviderError(f"{self.env_var} not configured")
        return self._api_key

    async def submit(
        self,
        prompt: str,
        *,
        duration: int = 5,
        resolution: str = "1280x720",
        aspect_ratio: str = "16:9",
    ) -> str:
        """Queue a generation task; return a provider job id."""
        raise NotImplementedError

    async def poll(self, job_id: str) -> JobStatus:
        """Return the current normalized status for *job_id*."""
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Runway ML — baseline working provider
# ---------------------------------------------------------------------------


class RunwayProvider(BaseVideoProvider):
    """Runway ML developer API (text-to-video, Gen-3/Gen-4)."""

    name = "runway"
    env_var = "RUNWAY_API_KEY"

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self._require_key()}",
            "X-Runway-Version": RUNWAY_API_VERSION,
            "Content-Type": "application/json",
        }

    @staticmethod
    def _ratio_to_runway(aspect_ratio: str) -> str:
        """Map a friendly aspect ratio to a Runway ratio string."""
        mapping = {"16:9": "1280:720", "9:16": "720:1280", "1:1": "960:960"}
        return mapping.get(aspect_ratio, "1280:720")

    async def submit(
        self,
        prompt: str,
        *,
        duration: int = 5,
        resolution: str = "1280x720",
        aspect_ratio: str = "16:9",
    ) -> str:
        import aiohttp

        payload: Dict[str, Any] = {
            "promptText": prompt,
            "model": "gen3a_turbo",
            "duration": max(1, min(int(duration), 10)),
            "ratio": self._ratio_to_runway(aspect_ratio),
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{RUNWAY_API_BASE}/text_to_video",
                json=payload,
                headers=self._headers(),
            ) as resp:
                body = await resp.json()
                if resp.status == 429:
                    raise ProviderError("Runway quota/rate limit exceeded (HTTP 429)")
                if resp.status not in (200, 201):
                    raise ProviderError(f"Runway submit failed (HTTP {resp.status}): {body}")
        job_id = body.get("id")
        if not job_id:
            raise ProviderError(f"Runway: no task id in response: {body}")
        return str(job_id)

    async def poll(self, job_id: str) -> JobStatus:
        import aiohttp

        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{RUNWAY_API_BASE}/tasks/{job_id}",
                headers=self._headers(),
            ) as resp:
                body = await resp.json()
                if resp.status != 200:
                    raise ProviderError(f"Runway poll failed (HTTP {resp.status}): {body}")
        return self._normalize(job_id, body)

    def _normalize(self, job_id: str, body: Dict[str, Any]) -> JobStatus:
        """Translate a Runway task payload into a JobStatus."""
        raw = str(body.get("status", "")).upper()
        if raw == "SUCCEEDED":
            outputs = body.get("output") or []
            url = outputs[0] if outputs else None
            return JobStatus(job_id, "succeeded", 1.0, video_url=url, provider=self.name)
        if raw == "FAILED":
            reason = body.get("failure") or body.get("failureCode") or "generation failed"
            return JobStatus(job_id, "failed", 0.0, error=str(reason), provider=self.name)
        if raw in ("RUNNING", "THROTTLED"):
            progress = float(body.get("progress") or 0.0)
            return JobStatus(job_id, "running", progress, provider=self.name)
        # PENDING / queued / unknown
        return JobStatus(job_id, "pending", 0.0, provider=self.name)


# ---------------------------------------------------------------------------
# OpenAI Sora — credential-gated (API surface not yet broadly stable)
# ---------------------------------------------------------------------------


class SoraProvider(BaseVideoProvider):
    """OpenAI Sora video generation (enabled only when SORA_API_KEY is set)."""

    name = "sora"
    env_var = "SORA_API_KEY"
    SORA_API_BASE = "https://api.openai.com/v1/videos"

    def _headers(self) -> Dict[str, str]:
        return {"Authorization": f"Bearer {self._require_key()}", "Content-Type": "application/json"}

    async def submit(
        self,
        prompt: str,
        *,
        duration: int = 5,
        resolution: str = "1280x720",
        aspect_ratio: str = "16:9",
    ) -> str:
        import aiohttp

        payload = {"model": "sora-2", "prompt": prompt, "seconds": str(max(1, int(duration)))}
        async with aiohttp.ClientSession() as session:
            async with session.post(self.SORA_API_BASE, json=payload, headers=self._headers()) as resp:
                body = await resp.json()
                if resp.status == 429:
                    raise ProviderError("Sora quota/rate limit exceeded (HTTP 429)")
                if resp.status not in (200, 201):
                    raise ProviderError(f"Sora submit failed (HTTP {resp.status}): {body}")
        job_id = body.get("id")
        if not job_id:
            raise ProviderError(f"Sora: no job id in response: {body}")
        return str(job_id)

    async def poll(self, job_id: str) -> JobStatus:
        import aiohttp

        async with aiohttp.ClientSession() as session:
            async with session.get(f"{self.SORA_API_BASE}/{job_id}", headers=self._headers()) as resp:
                body = await resp.json()
                if resp.status != 200:
                    raise ProviderError(f"Sora poll failed (HTTP {resp.status}): {body}")
        status = str(body.get("status", "")).lower()
        if status == "completed":
            url = body.get("url") or (body.get("output") or {}).get("url")
            return JobStatus(job_id, "succeeded", 1.0, video_url=url, provider=self.name)
        if status == "failed":
            return JobStatus(job_id, "failed", 0.0, error=str(body.get("error", "failed")), provider=self.name)
        progress = float(body.get("progress") or 0.0)
        progress = progress / 100.0 if progress > 1.0 else progress
        return JobStatus(job_id, "running" if progress > 0 else "pending", progress, provider=self.name)


# ---------------------------------------------------------------------------
# Kling AI — credential-gated
# ---------------------------------------------------------------------------


class KlingProvider(BaseVideoProvider):
    """Kling AI video generation (enabled only when KLING_API_KEY is set)."""

    name = "kling"
    env_var = "KLING_API_KEY"
    KLING_API_BASE = "https://api.klingai.com/v1/videos/text2video"

    def _headers(self) -> Dict[str, str]:
        return {"Authorization": f"Bearer {self._require_key()}", "Content-Type": "application/json"}

    async def submit(
        self,
        prompt: str,
        *,
        duration: int = 5,
        resolution: str = "1280x720",
        aspect_ratio: str = "16:9",
    ) -> str:
        import aiohttp

        payload = {"prompt": prompt, "duration": str(max(1, int(duration))), "aspect_ratio": aspect_ratio}
        async with aiohttp.ClientSession() as session:
            async with session.post(self.KLING_API_BASE, json=payload, headers=self._headers()) as resp:
                body = await resp.json()
                if resp.status == 429:
                    raise ProviderError("Kling quota/rate limit exceeded (HTTP 429)")
                if resp.status not in (200, 201):
                    raise ProviderError(f"Kling submit failed (HTTP {resp.status}): {body}")
        job_id = (body.get("data") or {}).get("task_id") or body.get("task_id")
        if not job_id:
            raise ProviderError(f"Kling: no task id in response: {body}")
        return str(job_id)

    async def poll(self, job_id: str) -> JobStatus:
        import aiohttp

        async with aiohttp.ClientSession() as session:
            async with session.get(f"{self.KLING_API_BASE}/{job_id}", headers=self._headers()) as resp:
                body = await resp.json()
                if resp.status != 200:
                    raise ProviderError(f"Kling poll failed (HTTP {resp.status}): {body}")
        data = body.get("data") or body
        status = str(data.get("task_status", "")).lower()
        if status == "succeed":
            videos = ((data.get("task_result") or {}).get("videos")) or []
            url = videos[0].get("url") if videos else None
            return JobStatus(job_id, "succeeded", 1.0, video_url=url, provider=self.name)
        if status == "failed":
            msg = data.get("task_status_msg") or "failed"
            return JobStatus(job_id, "failed", 0.0, error=str(msg), provider=self.name)
        return JobStatus(job_id, "running" if status == "processing" else "pending", 0.0, provider=self.name)


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


_PROVIDERS: Dict[str, type[BaseVideoProvider]] = {
    "runway": RunwayProvider,
    "sora": SoraProvider,
    "kling": KlingProvider,
}


def get_provider(name: str) -> BaseVideoProvider:
    """Return a provider instance for *name* (raises ProviderError if unknown)."""
    cls = _PROVIDERS.get(name)
    if cls is None:
        raise ProviderError(f"Unknown video provider: {name}")
    return cls()


def provider_names() -> list[str]:
    """Return the registered provider names in a stable order."""
    return list(_PROVIDERS.keys())
