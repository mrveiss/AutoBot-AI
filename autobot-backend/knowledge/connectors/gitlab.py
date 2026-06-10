# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
GitLab / Gitea / Forgejo Knowledge Connector (Issue #9011)

Indexes issues, merge/pull requests, and optionally repository files from
self-hosted or cloud GitLab, Gitea, and Forgejo instances into the AutoBot
knowledge base.

Two connector types are registered:

  ``gitlab``  — GitLab REST API v4 (gitlab.com or self-hosted).
  ``gitea``   — Gitea REST API v1, also compatible with Forgejo (identical API).

Config keys shared by both:
    token (str): Personal access token. Required.
    sync_issues (bool): Index issues. Default True.
    sync_merge_requests (bool): Index MRs/PRs. Default True.
    sync_files (bool): Index README + text files. Default False.
    per_page (int): Page size for paginated requests. Default 100.
    max_concurrency (int): Parallel source fetches. Default 4.

GitLab-specific config:
    gitlab_url (str): Base URL of the GitLab instance.
                      Default "https://gitlab.com".
    project_ids (list[str|int]): Numeric or namespace/path IDs to sync.
                                 Empty list = enumerate all accessible projects.

Gitea/Forgejo-specific config:
    gitea_url (str): Base URL of the Gitea/Forgejo instance. Required.
    repos (list[str]): Repositories in "owner/repo" format. Required.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
from urllib.parse import quote

import aiohttp

from autobot_shared.auth import ApiKeyAuth
from autobot_shared.logging_manager import get_logger
from autobot_shared.time_utils import now_utc, parse_utc_iso
from knowledge.connectors.base import AbstractConnector, RetryableError
from knowledge.connectors.content_extraction import content_hash as _content_hash
from knowledge.connectors.models import (
    ChangeInfo,
    ConnectorConfig,
    ContentResult,
    SourceInfo,
)
from knowledge.connectors.registry import ConnectorRegistry

logger = get_logger(__name__)

_REDIS_TS_PREFIX = "connector:gitlab:ts:"
_REDIS_TS_TTL = 86400 * 30  # 30 days


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _issue_to_text(issue: Dict[str, Any], *, is_pr: bool = False) -> str:
    kind = "Merge Request" if is_pr else "Issue"
    parts = [
        "%s #%s: %s" % (kind, issue.get("iid") or issue.get("number", ""), issue.get("title", "")),
        "State: %s" % issue.get("state", ""),
        "Author: %s" % _author_name(issue),
        "Created: %s" % issue.get("created_at", ""),
        "Updated: %s" % issue.get("updated_at", ""),
    ]
    labels = issue.get("labels") or []
    if labels:
        if isinstance(labels[0], dict):
            label_names = [lb.get("name", "") for lb in labels]
        else:
            label_names = [str(lb) for lb in labels]
        parts.append("Labels: %s" % ", ".join(label_names))
    body = issue.get("description") or issue.get("body") or ""
    if body.strip():
        parts.append("")
        parts.append(body.strip())
    return "\n".join(parts)


def _author_name(obj: Dict[str, Any]) -> str:
    author = obj.get("author") or obj.get("user") or {}
    if isinstance(author, dict):
        return author.get("username") or author.get("login") or author.get("name", "unknown")
    return str(author)


def _file_to_text(path: str, raw_content: str) -> str:
    return "File: %s\n\n%s" % (path, raw_content)


async def _load_ts(connector_id: str, source_id: str) -> Optional[str]:
    try:
        from autobot_shared.redis_client import get_redis_client

        redis = get_redis_client(database="knowledge")
        key = "%s%s:%s" % (_REDIS_TS_PREFIX, connector_id, source_id)
        value = redis.get(key)
        if hasattr(value, "__await__"):
            value = await value
        if isinstance(value, bytes):
            return value.decode("utf-8")
        return value
    except Exception as exc:
        logger.warning("Redis load_ts failed for %s: %s", source_id, exc)
        return None


async def _store_ts(connector_id: str, source_id: str, ts: str) -> None:
    try:
        from autobot_shared.redis_client import get_redis_client

        redis = get_redis_client(database="knowledge")
        key = "%s%s:%s" % (_REDIS_TS_PREFIX, connector_id, source_id)
        result = redis.set(key, ts, ex=_REDIS_TS_TTL)
        if hasattr(result, "__await__"):
            await result
    except Exception as exc:
        logger.warning("Redis store_ts failed for %s: %s", source_id, exc)


# ---------------------------------------------------------------------------
# GitLab connector
# ---------------------------------------------------------------------------


@ConnectorRegistry.register("gitlab")
class GitLabConnector(AbstractConnector):
    """Knowledge connector for GitLab instances.

    Indexes issues and merge requests (and optionally repository files) from
    one or more GitLab projects into the AutoBot knowledge base.

    Each issue/MR becomes one KB fact keyed by
    ``gitlab:{connector_id}:project:{project_id}:{kind}:{iid}``.

    Supports incremental sync via ``updated_at`` comparison cached in Redis.
    """

    connector_type = "gitlab"
    tier = 1
    max_concurrency = 4

    @classmethod
    def auth_schema(cls) -> type:
        return ApiKeyAuth

    def __init__(self, config: ConnectorConfig) -> None:
        super().__init__(config)
        cfg = config.config
        self._token: str = cfg.get("token", "")
        self._base_url: str = cfg.get("gitlab_url", "https://gitlab.com").rstrip("/")
        self._api_base: str = "%s/api/v4" % self._base_url
        self._project_ids: List[str] = [str(p) for p in cfg.get("project_ids", [])]
        self._sync_issues: bool = cfg.get("sync_issues", True)
        self._sync_mrs: bool = cfg.get("sync_merge_requests", True)
        self._sync_files: bool = cfg.get("sync_files", False)
        self._per_page: int = int(cfg.get("per_page", 100))

    # ------------------------------------------------------------------
    # AbstractConnector interface
    # ------------------------------------------------------------------

    async def test_connection(self) -> bool:
        result = await self._gl_get("/user")
        if result.get("status_code") == 200:
            return True
        self.logger.warning("GitLab test_connection failed: HTTP %s", result.get("status_code"))
        return False

    async def discover_sources(self) -> List[SourceInfo]:
        sources: List[SourceInfo] = []
        for project_id in await self._resolve_project_ids():
            if self._sync_issues:
                sources.extend(await self._discover_issues(project_id))
            if self._sync_mrs:
                sources.extend(await self._discover_mrs(project_id))
            if self._sync_files:
                sources.extend(await self._discover_files(project_id))
        return sources

    async def fetch_content(self, source_id: str) -> Optional[ContentResult]:
        parts = source_id.split(":")
        # Format: gitlab:{connector_id}:project:{project_id}:{kind}:{iid_or_path}
        if len(parts) < 6:
            self.logger.error("Malformed source_id: %s", source_id)
            return None
        project_id = parts[3]
        kind = parts[4]
        ref = ":".join(parts[5:])

        if kind == "issue":
            return await self._fetch_issue(project_id, ref, source_id)
        if kind == "mr":
            return await self._fetch_mr(project_id, ref, source_id)
        if kind == "file":
            return await self._fetch_file(project_id, ref, source_id)

        self.logger.error("Unknown kind '%s' in source_id: %s", kind, source_id)
        return None

    async def detect_changes(self, since: Optional[datetime] = None) -> List[ChangeInfo]:
        changes: List[ChangeInfo] = []
        for project_id in await self._resolve_project_ids():
            if self._sync_issues:
                changes.extend(await self._changed_issues(project_id, since))
            if self._sync_mrs:
                changes.extend(await self._changed_mrs(project_id, since))
            if self._sync_files:
                changes.extend(await self._changed_files(project_id, since))
        return changes

    # ------------------------------------------------------------------
    # Discovery helpers
    # ------------------------------------------------------------------

    async def _resolve_project_ids(self) -> List[str]:
        if self._project_ids:
            return self._project_ids
        result = await self._gl_get("/projects?membership=true&per_page=%d" % self._per_page)
        if result.get("status_code") != 200:
            self.logger.error("Failed to list GitLab projects: HTTP %s", result.get("status_code"))
            return []
        return [str(p["id"]) for p in result.get("body", [])]

    async def _discover_issues(self, project_id: str) -> List[SourceInfo]:
        items = await self._paginate("/projects/%s/issues?scope=all" % project_id)
        return [self._issue_source_info(project_id, item, "issue") for item in items]

    async def _discover_mrs(self, project_id: str) -> List[SourceInfo]:
        items = await self._paginate("/projects/%s/merge_requests?scope=all" % project_id)
        return [self._issue_source_info(project_id, item, "mr") for item in items]

    async def _discover_files(self, project_id: str) -> List[SourceInfo]:
        items = await self._paginate("/projects/%s/repository/tree?recursive=true" % project_id)
        sources = []
        for item in items:
            if item.get("type") != "blob":
                continue
            path = item.get("path", "")
            if not _is_text_file(path):
                continue
            sid = self._source_id(project_id, "file", path)
            sources.append(
                SourceInfo(
                    source_id=sid,
                    name=path,
                    path="%s/-/blob/HEAD/%s" % (self._base_url, path),
                    content_type="text/plain",
                    size_bytes=0,
                    last_modified=now_utc(),
                    metadata={"project_id": project_id, "file_path": path},
                )
            )
        return sources

    def _issue_source_info(self, project_id: str, item: Dict[str, Any], kind: str) -> SourceInfo:
        iid = str(item.get("iid", item.get("id", "")))
        sid = self._source_id(project_id, kind, iid)
        updated_raw = item.get("updated_at", "")
        try:
            last_modified = parse_utc_iso(updated_raw)
        except (ValueError, AttributeError):
            last_modified = now_utc()
        return SourceInfo(
            source_id=sid,
            name=item.get("title", ""),
            path=item.get("web_url", ""),
            content_type="text/plain",
            size_bytes=0,
            last_modified=last_modified,
            metadata={"project_id": project_id, "iid": iid, "kind": kind},
        )

    # ------------------------------------------------------------------
    # Change detection
    # ------------------------------------------------------------------

    async def _changed_issues(self, project_id: str, since: Optional[datetime]) -> List[ChangeInfo]:
        params = "scope=all&per_page=%d" % self._per_page
        if since:
            params += "&updated_after=%s" % since.isoformat()
        items = await self._paginate("/projects/%s/issues?%s" % (project_id, params))
        changes = []
        for item in items:
            iid = str(item.get("iid", ""))
            sid = self._source_id(project_id, "issue", iid)
            changes.append(await self._classify(sid, item.get("updated_at", ""), since))
        return [c for c in changes if c is not None]

    async def _changed_mrs(self, project_id: str, since: Optional[datetime]) -> List[ChangeInfo]:
        params = "scope=all&per_page=%d" % self._per_page
        if since:
            params += "&updated_after=%s" % since.isoformat()
        items = await self._paginate("/projects/%s/merge_requests?%s" % (project_id, params))
        changes = []
        for item in items:
            iid = str(item.get("iid", ""))
            sid = self._source_id(project_id, "mr", iid)
            changes.append(await self._classify(sid, item.get("updated_at", ""), since))
        return [c for c in changes if c is not None]

    async def _changed_files(self, project_id: str, since: Optional[datetime]) -> List[ChangeInfo]:
        items = await self._paginate("/projects/%s/repository/tree?recursive=true" % project_id)
        changes = []
        for item in items:
            if item.get("type") != "blob":
                continue
            path = item.get("path", "")
            if not _is_text_file(path):
                continue
            sid = self._source_id(project_id, "file", path)
            stored_ts = await _load_ts(self.config.connector_id, sid)
            change_type = "added" if stored_ts is None else "modified"
            changes.append(
                ChangeInfo(
                    source_id=sid,
                    change_type=change_type,
                    timestamp=now_utc(),
                    details={"path": path},
                )
            )
        return changes

    async def _classify(self, source_id: str, updated_at: str, since: Optional[datetime]) -> Optional[ChangeInfo]:
        if since is None:
            return ChangeInfo(
                source_id=source_id,
                change_type="added",
                timestamp=now_utc(),
                details={"updated_at": updated_at},
            )
        stored = await _load_ts(self.config.connector_id, source_id)
        if stored is None or updated_at > stored:
            change_type = "added" if stored is None else "modified"
            await _store_ts(self.config.connector_id, source_id, updated_at)
            return ChangeInfo(
                source_id=source_id,
                change_type=change_type,
                timestamp=now_utc(),
                details={"updated_at": updated_at},
            )
        return None

    # ------------------------------------------------------------------
    # Content fetch
    # ------------------------------------------------------------------

    async def _fetch_issue(self, project_id: str, iid: str, source_id: str) -> Optional[ContentResult]:
        result = await self._gl_get("/projects/%s/issues/%s" % (project_id, iid))
        if result.get("status_code") != 200:
            self.logger.error("GitLab fetch issue %s/%s: HTTP %s", project_id, iid, result.get("status_code"))
            return None
        item = result["body"]
        text = _issue_to_text(item)
        updated_at = item.get("updated_at", "")
        if updated_at:
            await _store_ts(self.config.connector_id, source_id, updated_at)
        return ContentResult(
            source_id=source_id,
            content=text,
            content_type="text/plain",
            metadata={
                "gitlab_project_id": project_id,
                "gitlab_issue_iid": iid,
                "gitlab_issue_url": item.get("web_url", ""),
                "title": item.get("title", ""),
                "state": item.get("state", ""),
                "updated_at": updated_at,
                "connector_type": self.connector_type,
            },
        )

    async def _fetch_mr(self, project_id: str, iid: str, source_id: str) -> Optional[ContentResult]:
        result = await self._gl_get("/projects/%s/merge_requests/%s" % (project_id, iid))
        if result.get("status_code") != 200:
            self.logger.error("GitLab fetch MR %s/%s: HTTP %s", project_id, iid, result.get("status_code"))
            return None
        item = result["body"]
        text = _issue_to_text(item, is_pr=True)
        updated_at = item.get("updated_at", "")
        if updated_at:
            await _store_ts(self.config.connector_id, source_id, updated_at)
        return ContentResult(
            source_id=source_id,
            content=text,
            content_type="text/plain",
            metadata={
                "gitlab_project_id": project_id,
                "gitlab_mr_iid": iid,
                "gitlab_mr_url": item.get("web_url", ""),
                "title": item.get("title", ""),
                "state": item.get("state", ""),
                "updated_at": updated_at,
                "connector_type": self.connector_type,
            },
        )

    async def _fetch_file(self, project_id: str, file_path: str, source_id: str) -> Optional[ContentResult]:
        encoded = quote(file_path, safe="")
        result = await self._gl_get("/projects/%s/repository/files/%s/raw?ref=HEAD" % (project_id, encoded))
        if result.get("status_code") != 200:
            self.logger.error("GitLab fetch file %s: HTTP %s", file_path, result.get("status_code"))
            return None
        raw = result.get("body_text", "")
        text = _file_to_text(file_path, raw)
        await _store_ts(self.config.connector_id, source_id, now_utc().isoformat())
        return ContentResult(
            source_id=source_id,
            content=text,
            content_type="text/plain",
            metadata={
                "gitlab_project_id": project_id,
                "file_path": file_path,
                "connector_type": self.connector_type,
            },
        )

    # ------------------------------------------------------------------
    # HTTP helpers
    # ------------------------------------------------------------------

    async def _gl_get(self, path: str) -> Dict[str, Any]:
        url = "%s%s" % (self._api_base, path)
        headers = {"PRIVATE-TOKEN": self._token}
        try:
            timeout = aiohttp.ClientTimeout(total=30.0)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url, headers=headers) as resp:
                    if resp.status == 429:
                        raise RetryableError("GitLab rate-limited", status_code=429)
                    if resp.status >= 500:
                        raise RetryableError("GitLab server error %d" % resp.status, status_code=resp.status)
                    content_type = resp.content_type or ""
                    if "json" in content_type:
                        body = await resp.json(content_type=None)
                        return {"status_code": resp.status, "body": body}
                    text = await resp.text(encoding="utf-8")
                    return {"status_code": resp.status, "body_text": text}
        except RetryableError:
            raise
        except aiohttp.ClientError as exc:
            self.logger.warning("GitLab request to %s failed: %s", url, exc)
            return {"status_code": 0, "error": str(exc)}

    async def _paginate(self, path: str) -> List[Dict[str, Any]]:
        items: List[Dict[str, Any]] = []
        sep = "&" if "?" in path else "?"
        page = 1
        while True:
            result = await self.fetch_with_retry(
                lambda p=path, pg=page, s=sep: self._gl_get("%s%sper_page=%d&page=%d" % (p, s, self._per_page, pg))
            )
            if result.get("status_code") != 200:
                break
            batch = result.get("body", [])
            if not batch:
                break
            items.extend(batch)
            if len(batch) < self._per_page:
                break
            page += 1
        return items

    def _source_id(self, project_id: str, kind: str, ref: str) -> str:
        return "gitlab:%s:project:%s:%s:%s" % (self.config.connector_id, project_id, kind, ref)


# ---------------------------------------------------------------------------
# Gitea / Forgejo connector
# ---------------------------------------------------------------------------


@ConnectorRegistry.register("gitea")
@ConnectorRegistry.register("forgejo")
class GiteaConnector(AbstractConnector):
    """Knowledge connector for Gitea and Forgejo instances.

    Gitea and Forgejo share identical REST APIs (``/api/v1``), so one connector
    class handles both.  To connect to a Forgejo instance, point ``gitea_url``
    at the Forgejo host — no other config change is needed.

    Each issue/PR becomes one KB fact keyed by
    ``gitea:{connector_id}:repo:{owner}:{repo}:{kind}:{number}``.
    """

    connector_type = "gitea"
    tier = 1
    max_concurrency = 4

    @classmethod
    def auth_schema(cls) -> type:
        return ApiKeyAuth

    def __init__(self, config: ConnectorConfig) -> None:
        super().__init__(config)
        cfg = config.config
        self._token: str = cfg.get("token", "")
        self._base_url: str = cfg.get("gitea_url", "").rstrip("/")
        self._api_base: str = "%s/api/v1" % self._base_url
        raw_repos: List[str] = cfg.get("repos", [])
        # Each entry must be "owner/repo"
        self._repos: List[tuple] = []
        for r in raw_repos:
            if "/" in r:
                owner, repo = r.split("/", 1)
                self._repos.append((owner, repo))
            else:
                self.logger.warning("Gitea repo entry '%s' missing owner — skipping", r)
        self._sync_issues: bool = cfg.get("sync_issues", True)
        self._sync_prs: bool = cfg.get("sync_merge_requests", True)
        self._sync_files: bool = cfg.get("sync_files", False)
        self._per_page: int = int(cfg.get("per_page", 50))

    # ------------------------------------------------------------------
    # AbstractConnector interface
    # ------------------------------------------------------------------

    async def test_connection(self) -> bool:
        result = await self._gitea_get("/user")
        if result.get("status_code") == 200:
            return True
        self.logger.warning("Gitea test_connection failed: HTTP %s", result.get("status_code"))
        return False

    async def discover_sources(self) -> List[SourceInfo]:
        sources: List[SourceInfo] = []
        for owner, repo in self._repos:
            if self._sync_issues:
                sources.extend(await self._discover_issues(owner, repo))
            if self._sync_prs:
                sources.extend(await self._discover_prs(owner, repo))
            if self._sync_files:
                sources.extend(await self._discover_files(owner, repo))
        return sources

    async def fetch_content(self, source_id: str) -> Optional[ContentResult]:
        parts = source_id.split(":")
        # Format: gitea:{connector_id}:repo:{owner}:{repo}:{kind}:{number_or_path}
        if len(parts) < 7:
            self.logger.error("Malformed Gitea source_id: %s", source_id)
            return None
        owner = parts[3]
        repo = parts[4]
        kind = parts[5]
        ref = ":".join(parts[6:])

        if kind == "issue":
            return await self._fetch_issue(owner, repo, ref, source_id)
        if kind == "pr":
            return await self._fetch_pr(owner, repo, ref, source_id)
        if kind == "file":
            return await self._fetch_file(owner, repo, ref, source_id)

        self.logger.error("Unknown Gitea kind '%s' in source_id: %s", kind, source_id)
        return None

    async def detect_changes(self, since: Optional[datetime] = None) -> List[ChangeInfo]:
        changes: List[ChangeInfo] = []
        for owner, repo in self._repos:
            if self._sync_issues:
                changes.extend(await self._changed_issues(owner, repo, since))
            if self._sync_prs:
                changes.extend(await self._changed_prs(owner, repo, since))
            if self._sync_files:
                changes.extend(await self._changed_files(owner, repo, since))
        return changes

    # ------------------------------------------------------------------
    # Discovery helpers
    # ------------------------------------------------------------------

    async def _discover_issues(self, owner: str, repo: str) -> List[SourceInfo]:
        items = await self._paginate("/repos/%s/%s/issues?type=issues" % (owner, repo))
        return [self._item_source_info(owner, repo, item, "issue") for item in items]

    async def _discover_prs(self, owner: str, repo: str) -> List[SourceInfo]:
        items = await self._paginate("/repos/%s/%s/pulls" % (owner, repo))
        return [self._item_source_info(owner, repo, item, "pr") for item in items]

    async def _discover_files(self, owner: str, repo: str) -> List[SourceInfo]:
        items = await self._paginate("/repos/%s/%s/git/trees/HEAD?recursive=true" % (owner, repo))
        tree = items[0].get("tree", []) if items else []
        sources = []
        for item in tree:
            if item.get("type") != "blob":
                continue
            path = item.get("path", "")
            if not _is_text_file(path):
                continue
            sid = self._source_id(owner, repo, "file", path)
            sources.append(
                SourceInfo(
                    source_id=sid,
                    name=path,
                    path="%s/%s/%s/raw/branch/HEAD/%s" % (self._base_url, owner, repo, path),
                    content_type="text/plain",
                    size_bytes=item.get("size", 0),
                    last_modified=now_utc(),
                    metadata={"owner": owner, "repo": repo, "file_path": path},
                )
            )
        return sources

    def _item_source_info(self, owner: str, repo: str, item: Dict[str, Any], kind: str) -> SourceInfo:
        number = str(item.get("number", ""))
        sid = self._source_id(owner, repo, kind, number)
        updated_raw = item.get("updated_at", "")
        try:
            last_modified = parse_utc_iso(updated_raw)
        except (ValueError, AttributeError):
            last_modified = now_utc()
        return SourceInfo(
            source_id=sid,
            name=item.get("title", ""),
            path=item.get("html_url", ""),
            content_type="text/plain",
            size_bytes=0,
            last_modified=last_modified,
            metadata={"owner": owner, "repo": repo, "number": number, "kind": kind},
        )

    # ------------------------------------------------------------------
    # Change detection
    # ------------------------------------------------------------------

    async def _changed_issues(self, owner: str, repo: str, since: Optional[datetime]) -> List[ChangeInfo]:
        params = "type=issues&limit=%d" % self._per_page
        if since:
            params += "&since=%s" % since.isoformat()
        items = await self._paginate("/repos/%s/%s/issues?%s" % (owner, repo, params))
        return [
            c
            for c in [
                await self._classify(
                    self._source_id(owner, repo, "issue", str(i.get("number", ""))), i.get("updated_at", ""), since
                )
                for i in items
            ]
            if c is not None
        ]

    async def _changed_prs(self, owner: str, repo: str, since: Optional[datetime]) -> List[ChangeInfo]:
        items = await self._paginate("/repos/%s/%s/pulls" % (owner, repo))
        changes = []
        for item in items:
            updated_at = item.get("updated_at", "")
            if since and updated_at and updated_at <= since.isoformat():
                continue
            sid = self._source_id(owner, repo, "pr", str(item.get("number", "")))
            change = await self._classify(sid, updated_at, since)
            if change:
                changes.append(change)
        return changes

    async def _changed_files(self, owner: str, repo: str, since: Optional[datetime]) -> List[ChangeInfo]:
        items = await self._paginate("/repos/%s/%s/git/trees/HEAD?recursive=true" % (owner, repo))
        tree = items[0].get("tree", []) if items else []
        changes = []
        for item in tree:
            if item.get("type") != "blob":
                continue
            path = item.get("path", "")
            if not _is_text_file(path):
                continue
            sid = self._source_id(owner, repo, "file", path)
            stored = await _load_ts(self.config.connector_id, sid)
            change_type = "added" if stored is None else "modified"
            changes.append(
                ChangeInfo(
                    source_id=sid,
                    change_type=change_type,
                    timestamp=now_utc(),
                    details={"path": path},
                )
            )
        return changes

    async def _classify(self, source_id: str, updated_at: str, since: Optional[datetime]) -> Optional[ChangeInfo]:
        if since is None:
            return ChangeInfo(
                source_id=source_id,
                change_type="added",
                timestamp=now_utc(),
                details={"updated_at": updated_at},
            )
        stored = await _load_ts(self.config.connector_id, source_id)
        if stored is None or updated_at > stored:
            change_type = "added" if stored is None else "modified"
            await _store_ts(self.config.connector_id, source_id, updated_at)
            return ChangeInfo(
                source_id=source_id,
                change_type=change_type,
                timestamp=now_utc(),
                details={"updated_at": updated_at},
            )
        return None

    # ------------------------------------------------------------------
    # Content fetch
    # ------------------------------------------------------------------

    async def _fetch_issue(self, owner: str, repo: str, number: str, source_id: str) -> Optional[ContentResult]:
        result = await self._gitea_get("/repos/%s/%s/issues/%s" % (owner, repo, number))
        if result.get("status_code") != 200:
            self.logger.error("Gitea fetch issue %s/%s#%s: HTTP %s", owner, repo, number, result.get("status_code"))
            return None
        item = result["body"]
        text = _issue_to_text(item)
        updated_at = item.get("updated_at", "")
        if updated_at:
            await _store_ts(self.config.connector_id, source_id, updated_at)
        return ContentResult(
            source_id=source_id,
            content=text,
            content_type="text/plain",
            metadata={
                "gitea_owner": owner,
                "gitea_repo": repo,
                "issue_number": number,
                "issue_url": item.get("html_url", ""),
                "title": item.get("title", ""),
                "state": item.get("state", ""),
                "updated_at": updated_at,
                "connector_type": self.connector_type,
            },
        )

    async def _fetch_pr(self, owner: str, repo: str, number: str, source_id: str) -> Optional[ContentResult]:
        result = await self._gitea_get("/repos/%s/%s/pulls/%s" % (owner, repo, number))
        if result.get("status_code") != 200:
            self.logger.error("Gitea fetch PR %s/%s#%s: HTTP %s", owner, repo, number, result.get("status_code"))
            return None
        item = result["body"]
        text = _issue_to_text(item, is_pr=True)
        updated_at = item.get("updated_at", "")
        if updated_at:
            await _store_ts(self.config.connector_id, source_id, updated_at)
        return ContentResult(
            source_id=source_id,
            content=text,
            content_type="text/plain",
            metadata={
                "gitea_owner": owner,
                "gitea_repo": repo,
                "pr_number": number,
                "pr_url": item.get("html_url", ""),
                "title": item.get("title", ""),
                "state": item.get("state", ""),
                "updated_at": updated_at,
                "connector_type": self.connector_type,
            },
        )

    async def _fetch_file(self, owner: str, repo: str, file_path: str, source_id: str) -> Optional[ContentResult]:
        result = await self._gitea_get("/repos/%s/%s/raw/%s" % (owner, repo, quote(file_path, safe="/")))
        if result.get("status_code") != 200:
            self.logger.error("Gitea fetch file %s: HTTP %s", file_path, result.get("status_code"))
            return None
        raw = result.get("body_text", "")
        text = _file_to_text(file_path, raw)
        await _store_ts(self.config.connector_id, source_id, now_utc().isoformat())
        return ContentResult(
            source_id=source_id,
            content=text,
            content_type="text/plain",
            metadata={
                "gitea_owner": owner,
                "gitea_repo": repo,
                "file_path": file_path,
                "connector_type": self.connector_type,
            },
        )

    # ------------------------------------------------------------------
    # HTTP helpers
    # ------------------------------------------------------------------

    async def _gitea_get(self, path: str) -> Dict[str, Any]:
        url = "%s%s" % (self._api_base, path)
        headers = {"Authorization": "token %s" % self._token}
        try:
            timeout = aiohttp.ClientTimeout(total=30.0)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url, headers=headers) as resp:
                    if resp.status == 429:
                        raise RetryableError("Gitea rate-limited", status_code=429)
                    if resp.status >= 500:
                        raise RetryableError("Gitea server error %d" % resp.status, status_code=resp.status)
                    content_type = resp.content_type or ""
                    if "json" in content_type:
                        body = await resp.json(content_type=None)
                        return {"status_code": resp.status, "body": body}
                    text = await resp.text(encoding="utf-8")
                    return {"status_code": resp.status, "body_text": text}
        except RetryableError:
            raise
        except aiohttp.ClientError as exc:
            self.logger.warning("Gitea request to %s failed: %s", url, exc)
            return {"status_code": 0, "error": str(exc)}

    async def _paginate(self, path: str) -> List[Dict[str, Any]]:
        items: List[Dict[str, Any]] = []
        sep = "&" if "?" in path else "?"
        page = 1
        while True:
            result = await self.fetch_with_retry(
                lambda p=path, pg=page, s=sep: self._gitea_get("%s%slimit=%d&page=%d" % (p, s, self._per_page, pg))
            )
            if result.get("status_code") != 200:
                break
            batch = result.get("body", [])
            if not isinstance(batch, list):
                items.append(batch)
                break
            if not batch:
                break
            items.extend(batch)
            if len(batch) < self._per_page:
                break
            page += 1
        return items

    def _source_id(self, owner: str, repo: str, kind: str, ref: str) -> str:
        return "gitea:%s:repo:%s:%s:%s:%s" % (self.config.connector_id, owner, repo, kind, ref)


# ---------------------------------------------------------------------------
# Shared utility
# ---------------------------------------------------------------------------


_TEXT_EXTENSIONS = {
    ".md",
    ".rst",
    ".txt",
    ".py",
    ".js",
    ".ts",
    ".go",
    ".rb",
    ".java",
    ".c",
    ".cpp",
    ".h",
    ".hpp",
    ".cs",
    ".php",
    ".sh",
    ".yaml",
    ".yml",
    ".json",
    ".toml",
    ".ini",
    ".cfg",
    ".conf",
    ".html",
    ".htm",
    ".xml",
    ".csv",
    ".sql",
    ".kt",
    ".swift",
    ".rs",
    ".scala",
    ".ex",
    ".exs",
}


def _is_text_file(path: str) -> bool:
    import os

    _, ext = os.path.splitext(path.lower())
    return ext in _TEXT_EXTENSIONS
