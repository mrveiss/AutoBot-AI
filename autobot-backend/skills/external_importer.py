# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
External Skill Importer (Issue #5063)

Imports skill packages from external git repositories and HTTP catalogs.
All imported skills are always assigned SkillActivationLevel.SANDBOXED -- they are never
automatically promoted to BUILTIN or TRUSTED.
"""

import asyncio
import os
import re
import uuid
from typing import Any
from urllib.parse import urlparse

import aiohttp

from autobot_shared.logging_manager import get_logger
from skills.manifest_parser import parse_manifest
from skills.models import SkillActivationLevel, SkillPackage, SkillState

logger = get_logger(__name__)

_SKILL_CACHE_DIR = "/var/lib/autobot/skill_cache"
_GIT_TIMEOUT = 120
_SOURCE_META_KEY = "external_import"

# Allowlist of git URL schemes.  file://, http://, git:// and any other scheme
# are rejected outright to prevent SSRF via the git binary.
_ALLOWED_GIT_SCHEMES = frozenset({"https", "ssh", "git+ssh"})

# Valid git ref characters — rejects flag-injection strings like --upload-pack=x
# and path-traversal sequences.
_GIT_REF_RE = re.compile(r"^[A-Za-z0-9._/\-]+$")


def _parse_git_remote(url: str) -> tuple[str, str]:
    """Return (scheme, host) for a git remote URL.

    Supports https://, ssh://, git+ssh://, and SCP-style git@host:path remotes.
    Raises ValueError for disallowed or unrecognisable formats.
    """
    if "://" not in url:
        # SCP-style: [user@]host:path  — treated as SSH
        host_part = url.split(":", 1)[0]
        host = host_part.split("@", 1)[-1]
        if not host:
            raise ValueError(f"Cannot parse host from SCP-style git URL: {url!r}")
        return "ssh", host

    parsed = urlparse(url)
    scheme = (parsed.scheme or "").lower()
    if scheme not in _ALLOWED_GIT_SCHEMES:
        raise ValueError(
            f"Disallowed git URL scheme {scheme!r} in {url!r}: "
            f"only https and ssh are permitted (got scheme from allowlist {_ALLOWED_GIT_SCHEMES})"
        )
    host = parsed.hostname or ""
    if not host:
        raise ValueError(f"Git URL has no hostname: {url!r}")
    return scheme, host


async def _validate_git_url(url: str) -> None:
    """SSRF guard for git remote URLs.

    Rejects file://, http://, git://, and any private/internal host.
    For https:// delegates to is_public_url_async; for ssh/git+ssh resolves
    the host via resolve_safe_ip_async to block private RFC-range IPs.

    Raises RuntimeError with a descriptive message on any rejection.
    """
    from autobot_shared.url_safety import is_public_url_async, resolve_safe_ip_async

    try:
        scheme, host = _parse_git_remote(url)
    except ValueError as exc:
        raise RuntimeError(f"Git URL rejected: {exc}") from exc

    if scheme == "https":
        if not await is_public_url_async(url):
            raise RuntimeError(f"Git HTTPS URL blocked by SSRF guard: {url}")
    else:
        # SSH variants: validate the resolved IP is publicly routable.
        try:
            await resolve_safe_ip_async(host)
        except ValueError as exc:
            raise RuntimeError(f"Git SSH URL blocked by SSRF guard ({host}): {exc}") from exc


def _validate_git_ref(ref: str) -> None:
    """Reject ref strings that look like flag injection or path traversal."""
    if not ref or ref.startswith("-") or ".." in ref or not _GIT_REF_RE.match(ref):
        raise RuntimeError(
            f"Invalid git ref {ref!r}: refs must match [A-Za-z0-9._/-]+ " "and cannot start with '-' or contain '..'"
        )


def _ensure_cache_dir() -> str:
    """Create skill cache directory if it does not exist.

    Returns the cache directory path, or a temp fallback on permission error.
    """
    try:
        os.makedirs(_SKILL_CACHE_DIR, exist_ok=True)
        return _SKILL_CACHE_DIR
    except PermissionError:
        import tempfile

        fallback = os.path.join(tempfile.gettempdir(), "autobot_skill_cache")
        os.makedirs(fallback, exist_ok=True)
        logger.warning(
            "Cannot write to %s (permission denied); using fallback cache %s",
            _SKILL_CACHE_DIR,
            fallback,
        )
        return fallback


async def _git_available() -> bool:
    """Return True if the git binary is on PATH."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "git",
            "--version",
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await proc.wait()
        return proc.returncode == 0
    except FileNotFoundError:
        return False


async def _run_git(*args: str, cwd: str | None = None) -> None:
    """Run a git command; raise RuntimeError on non-zero exit."""
    proc = await asyncio.create_subprocess_exec(
        "git",
        *args,
        cwd=cwd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await asyncio.wait_for(proc.communicate(), timeout=_GIT_TIMEOUT)
    if proc.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {stderr.decode('utf-8', errors='replace')}")


def _walk_skill_mds(root: str) -> list[str]:
    """Return paths of all SKILL.md files found under root."""
    paths: list[str] = []
    for dirpath, _dirs, files in os.walk(root):
        if "SKILL.md" in files:
            paths.append(os.path.join(dirpath, "SKILL.md"))
    return paths


def _read_adjacent_py(skill_md_path: str) -> str | None:
    """Read skill.py adjacent to SKILL.md, returning None if absent."""
    py_path = os.path.join(os.path.dirname(skill_md_path), "skill.py")
    if not os.path.exists(py_path):
        return None
    with open(py_path, encoding="utf-8") as fh:
        return fh.read()


def _build_package_from_manifest(
    manifest: dict[str, Any],
    skill_md_text: str,
    skill_py: str | None,
    repo_id: str | None,
    source_url: str,
) -> SkillPackage:
    """Construct a SANDBOXED SkillPackage from a parsed manifest."""
    meta: dict[str, Any] = {
        _SOURCE_META_KEY: True,
        "source_url": source_url,
    }
    return SkillPackage(
        id=str(uuid.uuid4()),
        name=manifest["name"],
        version=manifest.get("version", "0.0.0"),
        state=SkillState.INSTALLED,
        repo_id=repo_id,
        skill_md=skill_md_text,
        skill_py=skill_py,
        manifest={**manifest, **meta},
        trust_level=SkillActivationLevel.SANDBOXED,
        requested_by="external-import",
    )


class ExternalSkillImporter:
    """Import skills from git repositories and HTTP catalogs.

    All imported skills are assigned SkillActivationLevel.SANDBOXED and stored in the
    DB for subsequent review before any promotion attempt.
    """

    async def import_git_repo(self, url: str, ref: str = "main", repo_id: str | None = None) -> list[SkillPackage]:
        """Clone/fetch a git repository and return SkillPackage objects for each SKILL.md found.

        The packages are NOT persisted here -- callers are responsible for
        saving them to the database.

        Args:
            url: Git remote URL (https or ssh).
            ref: Branch, tag, or commit to check out.
            repo_id: Optional SkillRepo.id to link packages to.

        Returns:
            List of SANDBOXED SkillPackage instances (not yet DB-committed).

        Raises:
            RuntimeError: If git is not available, the URL is blocked by the
                SSRF guard, or cloning fails.
        """
        # SSRF protection enforced before any git operation:
        # 1. Scheme validation: only https/ssh/git+ssh allowed (no file://, git://, etc.)
        # 2. HTTPS URLs: validated via is_public_url_async() to reject private IPs
        # 3. SSH URLs: host resolved via resolve_safe_ip_async() to block RFC1918/loopback
        # See _validate_git_url() implementation and #MVA-2605 for full security analysis.
        await _validate_git_url(url)
        _validate_git_ref(ref)

        if not await _git_available():
            raise RuntimeError("git binary not found on PATH -- cannot import git repo")

        cache_dir = _ensure_cache_dir()
        safe_name = url.replace("://", "_").replace("/", "_").replace(":", "_")
        clone_dir = os.path.join(cache_dir, safe_name[:80])

        if os.path.exists(os.path.join(clone_dir, ".git")):
            logger.info("Fetching existing clone: %s", clone_dir)
            await _run_git("fetch", "--depth=1", "origin", cwd=clone_dir)
            await _run_git("checkout", ref, cwd=clone_dir)
        else:
            logger.info("Cloning %s (ref=%s) -> %s", url, ref, clone_dir)
            # codeql[py/full-ssrf] SSRF mitigated: url validated by _validate_git_url() enforcing
            # https/ssh scheme and blocking private IP ranges
            await _run_git("clone", "--depth=1", "--branch", ref, url, clone_dir)

        skill_md_paths = _walk_skill_mds(clone_dir)
        logger.info("Found %d SKILL.md file(s) in %s", len(skill_md_paths), clone_dir)

        packages: list[SkillPackage] = []
        for path in skill_md_paths:
            with open(path, encoding="utf-8") as fh:
                text = fh.read()
            try:
                manifest = parse_manifest(text)
            except ValueError as exc:
                logger.warning("Skipping %s: %s", path, exc)
                continue
            skill_py = _read_adjacent_py(path)
            pkg = _build_package_from_manifest(
                manifest=manifest,
                skill_md_text=text,
                skill_py=skill_py,
                repo_id=repo_id,
                source_url=url,
            )
            packages.append(pkg)
            logger.info("Imported skill '%s' from %s", pkg.name, path)

        return packages

    async def import_http_catalog(self, url: str, page: int = 1, page_size: int = 20) -> list[dict[str, Any]]:
        """Fetch a paginated JSON skill catalog from an HTTP endpoint.

        The endpoint is expected to return JSON in the shape::

            {
                "skills": [ { "name": ..., "version": ..., ... }, ... ],
                "total": <int>,
                "page": <int>
            }

        or simply a list of skill dicts.

        Args:
            url: HTTP/HTTPS URL of the catalog endpoint.
            page: Page number (1-based).
            page_size: Items per page.

        Returns:
            List of catalog entry dicts.

        Raises:
            RuntimeError: On HTTP error, SSRF guard rejection, or unexpected response shape.
        """
        from autobot_shared.url_safety import is_public_url_async

        if not await is_public_url_async(url):
            raise RuntimeError(f"Catalog URL blocked by SSRF guard: {url}")

        params = {"page": page, "page_size": page_size}
        timeout = aiohttp.ClientTimeout(total=30)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url, params=params) as response:
                if response.status != 200:
                    raise RuntimeError(f"Catalog fetch failed: HTTP {response.status} from {url}")
                data = await response.json()

        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            return data.get("skills", [])
        raise RuntimeError(f"Unexpected catalog response shape from {url}: {type(data).__name__}")

    async def install_from_catalog(
        self, name: str, catalog_entry: dict[str, Any], repo_id: str | None = None
    ) -> SkillPackage:
        """Materialize a catalog entry as a SANDBOXED SkillPackage.

        The catalog entry must contain at minimum a ``skill_md`` key with the
        full SKILL.md content.  An optional ``skill_py`` key may contain the
        implementation source.

        Args:
            name: Canonical skill name (used as a fallback if manifest omits it).
            catalog_entry: Dict from :meth:`import_http_catalog`.
            repo_id: Optional SkillRepo.id to link the package to.

        Returns:
            SANDBOXED SkillPackage (not yet DB-committed).

        Raises:
            ValueError: If ``skill_md`` is absent or the manifest is invalid.
        """
        skill_md = catalog_entry.get("skill_md")
        if not skill_md:
            raise ValueError(f"Catalog entry for '{name}' is missing 'skill_md'")

        try:
            manifest = parse_manifest(skill_md)
        except ValueError as exc:
            raise ValueError(f"Invalid manifest in catalog entry '{name}': {exc}") from exc

        skill_py = catalog_entry.get("skill_py")
        source_url = catalog_entry.get("source_url", "http-catalog")

        pkg = _build_package_from_manifest(
            manifest=manifest,
            skill_md_text=skill_md,
            skill_py=skill_py,
            repo_id=repo_id,
            source_url=source_url,
        )
        logger.info("Installed catalog skill '%s' from %s", pkg.name, source_url)
        return pkg


def is_externally_imported(skill: SkillPackage) -> bool:
    """Return True if the skill was imported from an external source.

    Checks the ``external_import`` flag stored in the manifest JSON column
    by :class:`ExternalSkillImporter`.
    """
    manifest = skill.manifest or {}
    return bool(manifest.get(_SOURCE_META_KEY))
