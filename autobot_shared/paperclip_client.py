# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Idempotent Paperclip API client for autobot_shared (GH#8944).

Prevents three routine-agent failure modes:
  1. Duplicate task creation — creates only when no matching issue exists.
  2. Comment flooding     — skips posts whose fingerprint was sent recently.
  3. Status churn         — no-ops when the issue already has the target status.

All idempotency state is backed by Redis so the guard holds across multiple
processes and restarts.  Every method fails open: if Redis is unavailable the
underlying API call proceeds normally rather than silently dropping data.

Configuration
-------------
Environment variables (same ones injected by the Paperclip harness):

  PAPERCLIP_API_URL   Base URL of the Paperclip server (required).
  PAPERCLIP_API_KEY   Bearer token for all requests (required).
  PAPERCLIP_RUN_ID    Injected run-ID forwarded in X-Paperclip-Run-Id header
                      (optional; omit for calls outside a harness run).

Redis database
--------------
All keys use the ``"main"`` logical database and live under the namespace
``paperclip:idem:``.  TTLs default to the values below but callers may
override them per-call.

Usage
-----
    from autobot_shared.paperclip_client import PaperclipClient

    async with PaperclipClient() as client:
        issue = await client.create_issue_idempotent(
            company_id="...",
            title="[GH#1234] Fix the thing",
            description="...",
        )
        await client.post_comment_idempotent(issue["id"], "Work complete.")
        await client.update_status_idempotent(issue["id"], "done")
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
from typing import Any
from urllib.parse import quote as _url_quote

import aiohttp

from autobot_shared.redis_client import get_async_redis_client

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

_COMMENT_DEDUP_TTL_SECONDS = int(os.environ.get("AUTOBOT_PAPERCLIP_COMMENT_DEDUP_TTL", 3600))
_ISSUE_SEARCH_LIMIT = 50  # max results to scan when checking for duplicates
_REDIS_KEY_PREFIX = "paperclip:idem:"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _content_fingerprint(text: str) -> str:
    """SHA-256 hex digest of normalised text.

    Strips leading/trailing whitespace and collapses internal runs of
    whitespace so that two messages differing only in spacing compare equal.
    """
    normalised = re.sub(r"\s+", " ", text.strip())
    return hashlib.sha256(normalised.encode("utf-8")).hexdigest()


def _comment_dedup_key(issue_id: str, fingerprint: str) -> str:
    return f"{_REDIS_KEY_PREFIX}comment:{issue_id}:{fingerprint}"


def _issue_search_key(company_id: str, title_fingerprint: str) -> str:
    return f"{_REDIS_KEY_PREFIX}issue:{company_id}:{title_fingerprint}"


# ---------------------------------------------------------------------------
# PaperclipClient
# ---------------------------------------------------------------------------


class PaperclipClient:
    """Async Paperclip HTTP client with idempotency guards.

    Can be used as an async context manager (preferred) or with explicit
    ``open()`` / ``close()`` calls.

    Args:
        api_url:  Base URL; defaults to ``PAPERCLIP_API_URL`` env var.
        api_key:  Bearer token; defaults to ``PAPERCLIP_API_KEY`` env var.
        run_id:   Heartbeat run ID forwarded as ``X-Paperclip-Run-Id``;
                  defaults to ``PAPERCLIP_RUN_ID`` env var.
        comment_dedup_ttl: Seconds a comment fingerprint is suppressed after
                  the first successful post.  0 disables dedup.
    """

    def __init__(
        self,
        *,
        api_url: str | None = None,
        api_key: str | None = None,
        run_id: str | None = None,
        comment_dedup_ttl: int = _COMMENT_DEDUP_TTL_SECONDS,
    ) -> None:
        self._api_url = (api_url or os.environ.get("PAPERCLIP_API_URL") or "").rstrip("/")
        self._api_key = api_key or os.environ.get("PAPERCLIP_API_KEY", "")
        self._run_id = run_id or os.environ.get("PAPERCLIP_RUN_ID", "")
        self._comment_dedup_ttl = comment_dedup_ttl
        self._session: aiohttp.ClientSession | None = None
        self._redis: Any | None = None  # async Redis client; None when unavailable

    # ------------------------------------------------------------------
    # Context manager / lifecycle
    # ------------------------------------------------------------------

    async def __aenter__(self) -> "PaperclipClient":
        await self.open()
        return self

    async def __aexit__(self, *_: Any) -> None:
        await self.close()

    async def open(self) -> None:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                headers=self._base_headers(),
                timeout=aiohttp.ClientTimeout(total=30, connect=5),
            )
        if self._redis is None:
            try:
                self._redis = await get_async_redis_client(database="main")
            except Exception as exc:
                logger.warning("paperclip_client: Redis unavailable (%s) — failing open", exc)
                self._redis = None

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()
        self._session = None
        self._redis = None

    # ------------------------------------------------------------------
    # Idempotent public API
    # ------------------------------------------------------------------

    async def create_issue_idempotent(
        self,
        company_id: str,
        title: str,
        *,
        description: str = "",
        status: str = "todo",
        priority: str = "medium",
        **extra_fields: Any,
    ) -> dict:
        """Create an issue unless one with the same title already exists.

        Searches for an open issue whose title exactly matches *title*. If a
        match is found, returns that issue rather than creating a duplicate.
        On a cache-miss it creates the issue and caches the new ID in Redis
        so subsequent calls within the dedup window are instant.

        Args:
            company_id:    Paperclip company UUID.
            title:         Issue title (used as the idempotency key).
            description:   Issue body markdown.
            status:        Initial status for newly created issues.
            priority:      Issue priority.
            **extra_fields: Any additional fields forwarded to the create API.

        Returns:
            The existing or newly created issue object (dict).
        """
        session = await self._ensure_session()
        fp = _content_fingerprint(title)
        cache_key = _issue_search_key(company_id, fp)

        # Fast path: Redis has the issue ID from a previous call.
        cached_id = await self._redis_get(cache_key)
        if cached_id:
            existing = await self._get_issue(session, cached_id)
            if existing:
                logger.debug(
                    "paperclip_client.create_issue_idempotent: cache hit title=%r id=%s",
                    title,
                    cached_id,
                )
                return existing
            # Cached ID no longer resolves — fall through to search.
            await self._redis_delete(cache_key)

        # Slow path: search the API for an existing issue.
        existing = await self._search_issue_by_title(session, company_id, title)
        if existing:
            logger.info(
                "paperclip_client.create_issue_idempotent: duplicate suppressed title=%r id=%s",
                title,
                existing.get("id"),
            )
            await self._redis_set(cache_key, existing["id"], ttl=86400)
            return existing

        # Not found — create it.
        payload: dict[str, Any] = {
            "title": title,
            "description": description,
            "status": status,
            "priority": priority,
            **extra_fields,
        }
        created = await self._post_json(session, f"/api/companies/{company_id}/issues", payload)
        logger.info(
            "paperclip_client.create_issue_idempotent: created id=%s title=%r",
            created.get("id"),
            title,
        )
        if created.get("id"):
            await self._redis_set(cache_key, created["id"], ttl=86400)
        return created

    async def post_comment_idempotent(
        self,
        issue_id: str,
        body: str,
        *,
        dedup_ttl: int | None = None,
    ) -> dict | None:
        """Post a comment only if the same content wasn't posted recently.

        A SHA-256 fingerprint of the normalised *body* is stored in Redis
        with a TTL.  Duplicate calls within the TTL window are silently
        dropped (returns ``None``).

        Args:
            issue_id:  Paperclip issue UUID.
            body:      Markdown comment body.
            dedup_ttl: Override the instance-level comment dedup TTL (seconds).
                       Pass 0 to disable dedup for this call.

        Returns:
            The created comment dict, or ``None`` when the post was suppressed.
        """
        ttl = self._comment_dedup_ttl if dedup_ttl is None else dedup_ttl
        fp = _content_fingerprint(body)

        if ttl > 0:
            dedup_key = _comment_dedup_key(issue_id, fp)
            if await self._redis_exists(dedup_key):
                logger.debug(
                    "paperclip_client.post_comment_idempotent: suppressed duplicate " "issue_id=%s fingerprint=%s",
                    issue_id,
                    fp,
                )
                return None

        session = await self._ensure_session()
        comment = await self._post_json(session, f"/api/issues/{issue_id}/comments", {"body": body})

        if ttl > 0 and comment.get("id"):
            await self._redis_set(_comment_dedup_key(issue_id, fp), "1", ttl=ttl)

        logger.debug(
            "paperclip_client.post_comment_idempotent: posted id=%s issue=%s",
            comment.get("id"),
            issue_id,
        )
        return comment

    async def update_status_idempotent(
        self,
        issue_id: str,
        status: str,
        *,
        comment: str | None = None,
        extra_fields: dict[str, Any] | None = None,
    ) -> dict | None:
        """Update issue status only when it differs from the current value.

        Fetches the current issue state first. If the issue is already in
        *status*, the update is skipped and ``None`` is returned.

        Args:
            issue_id:     Paperclip issue UUID.
            status:       Target status string (e.g. ``"done"``, ``"blocked"``).
            comment:      Optional comment to include in the PATCH body.
            extra_fields: Additional fields to include in the PATCH body.

        Returns:
            The updated issue dict, or ``None`` when the update was skipped.
        """
        session = await self._ensure_session()
        current = await self._get_issue(session, issue_id)
        if current and current.get("status") == status:
            logger.debug(
                "paperclip_client.update_status_idempotent: no-op issue=%s status=%s",
                issue_id,
                status,
            )
            return None

        payload: dict[str, Any] = {"status": status}
        if comment:
            payload["comment"] = comment
        if extra_fields:
            payload.update(extra_fields)

        updated = await self._patch_json(session, f"/api/issues/{issue_id}", payload)
        logger.info(
            "paperclip_client.update_status_idempotent: updated issue=%s %s→%s",
            issue_id,
            current.get("status") if current else "?",
            status,
        )
        return updated

    # ------------------------------------------------------------------
    # Low-level HTTP helpers
    # ------------------------------------------------------------------

    def _base_headers(self) -> dict[str, str]:
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        if self._run_id:
            headers["X-Paperclip-Run-Id"] = self._run_id
        return headers

    async def _ensure_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            await self.open()
        assert self._session is not None
        return self._session

    async def _get_json(self, session: aiohttp.ClientSession, path: str) -> dict | None:
        url = f"{self._api_url}{path}"
        try:
            async with session.get(url) as resp:
                if resp.status == 404:
                    return None
                resp.raise_for_status()
                return await resp.json()
        except aiohttp.ClientError as exc:
            logger.error("paperclip_client GET %s failed: %s", path, exc)
            raise

    async def _post_json(self, session: aiohttp.ClientSession, path: str, payload: dict) -> dict:
        url = f"{self._api_url}{path}"
        try:
            async with session.post(url, json=payload) as resp:
                resp.raise_for_status()
                return await resp.json()
        except aiohttp.ClientError as exc:
            logger.error("paperclip_client POST %s failed: %s", path, exc)
            raise

    async def _patch_json(self, session: aiohttp.ClientSession, path: str, payload: dict) -> dict:
        url = f"{self._api_url}{path}"
        try:
            async with session.patch(url, json=payload) as resp:
                resp.raise_for_status()
                return await resp.json()
        except aiohttp.ClientError as exc:
            logger.error("paperclip_client PATCH %s failed: %s", path, exc)
            raise

    async def _get_issue(self, session: aiohttp.ClientSession, issue_id: str) -> dict | None:
        return await self._get_json(session, f"/api/issues/{issue_id}")

    async def _search_issue_by_title(self, session: aiohttp.ClientSession, company_id: str, title: str) -> dict | None:
        """Return the first open issue whose title exactly matches *title*."""
        encoded = _url_quote(title, safe="")
        path = f"/api/companies/{company_id}/issues?q={encoded}&limit={_ISSUE_SEARCH_LIMIT}"
        result = await self._get_json(session, path)
        if not result:
            return None
        items: list[dict] = result if isinstance(result, list) else result.get("items", [])
        if len(items) >= _ISSUE_SEARCH_LIMIT:
            logger.warning(
                "paperclip_client._search_issue_by_title: hit scan limit (%d) for title=%r"
                " — exact match may have been missed",
                _ISSUE_SEARCH_LIMIT,
                title,
            )
        for item in items:
            if item.get("title") == title and item.get("status") not in ("done", "cancelled"):
                return item
        return None

    # ------------------------------------------------------------------
    # Redis helpers — async, fail-open
    # ------------------------------------------------------------------

    async def _redis_get(self, key: str) -> str | None:
        if self._redis is None:
            return None
        try:
            value = await self._redis.get(key)
            return value.decode() if isinstance(value, bytes) else value
        except Exception as exc:
            logger.warning("paperclip_client: Redis GET %s failed: %s", key, exc)
            return None

    async def _redis_set(self, key: str, value: str, *, ttl: int) -> None:
        if self._redis is None:
            return
        try:
            await self._redis.set(key, value, ex=ttl)
        except Exception as exc:
            logger.warning("paperclip_client: Redis SET %s failed: %s", key, exc)

    async def _redis_exists(self, key: str) -> bool:
        if self._redis is None:
            return False
        try:
            return bool(await self._redis.exists(key))
        except Exception as exc:
            logger.warning("paperclip_client: Redis EXISTS %s failed: %s", key, exc)
            return False

    async def _redis_delete(self, key: str) -> None:
        if self._redis is None:
            return
        try:
            await self._redis.delete(key)
        except Exception as exc:
            logger.warning("paperclip_client: Redis DELETE %s failed: %s", key, exc)
