# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""System Docs filesystem service (Issue #12314).

Backs the ``/api/knowledge_base/system-docs/*`` endpoints that power the
Knowledge -> System Docs viewer. Reads the on-disk documentation tree
(``PATH.DOCS_DIR``) directly so the page is always populated without
depending on the ChromaDB/Redis indexing pipeline.

Categories are derived from the ``docs/`` directory structure: each
top-level sub-directory is a category, and loose top-level ``*.md`` files
are grouped under a synthetic ``general`` category. Document ids are an
opaque hash of the repo-relative path, so no client-supplied path ever
reaches the filesystem (guards against traversal).
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

from autobot_shared.logging_manager import get_logger
from constants.path_constants import PATH

logger = get_logger(__name__)

DOC_TYPE = "markdown"
GENERAL_CATEGORY = "general"
_TITLE_SCAN_LINES = 50


def _docs_root() -> Path:
    """Return the on-disk documentation root (``<project>/docs``)."""
    return Path(PATH.DOCS_DIR)


def _humanize(name: str) -> str:
    """Turn a directory/file stem into a human-readable label."""
    label = name.replace("_", " ").replace("-", " ").strip().title()
    return label or name


def _doc_id(rel_path: str) -> str:
    """Deterministic, slash-free id for a repo-relative doc path."""
    # Non-cryptographic identifier only (usedforsecurity=False).
    return hashlib.sha1(rel_path.encode("utf-8"), usedforsecurity=False).hexdigest()


def _within(path: Path, root: Path) -> bool:
    """True when ``path`` resolves inside ``root`` (traversal guard)."""
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _iter_markdown(base: Path) -> Iterator[Path]:
    """Yield markdown files under ``base`` in stable sorted order."""
    for path in sorted(base.rglob("*.md")):
        if path.is_file():
            yield path


def _category_dirs(root: Path) -> List[Path]:
    """Return visible top-level sub-directories of the docs root."""
    return sorted(p for p in root.iterdir() if p.is_dir() and not p.name.startswith("."))


def _loose_docs(root: Path) -> List[Path]:
    """Return markdown files sitting directly in the docs root."""
    return sorted(p for p in root.glob("*.md") if p.is_file())


def _extract_title(path: Path, fallback: str) -> str:
    """Use the first markdown H1 as the title, else a humanized stem."""
    try:
        with path.open(encoding="utf-8") as handle:
            for _ in range(_TITLE_SCAN_LINES):
                line = handle.readline()
                if not line:
                    break
                stripped = line.strip()
                if stripped.startswith("# "):
                    return stripped[2:].strip()
    except OSError as exc:
        logger.debug("Title scan failed for %s: %s", path, exc)
    return _humanize(fallback)


def _build_doc(path: Path, root: Path, category: str, include_content: bool) -> Dict[str, Any]:
    """Assemble a SystemDoc dict matching the frontend contract."""
    rel = path.relative_to(root).as_posix()
    content = ""
    if include_content:
        content = path.read_text(encoding="utf-8")
    metadata: Dict[str, Any] = {}
    try:
        mtime = path.stat().st_mtime
        metadata["lastModified"] = datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat()
    except OSError:
        pass
    return {
        "id": _doc_id(rel),
        "title": _extract_title(path, path.stem),
        "path": rel,
        "content": content,
        "type": DOC_TYPE,
        "category": category,
        "metadata": metadata,
    }


def _category_entry(cat_id: str, name: str, doc_count: int) -> Dict[str, Any]:
    """Build a DocCategory dict (docs loaded lazily by the category route)."""
    return {
        "id": cat_id,
        "name": name,
        "path": cat_id,
        "icon": "folder",
        "children": [],
        "docs": [],
        "docCount": doc_count,
    }


def list_categories() -> List[Dict[str, Any]]:
    """List documentation categories with per-category document counts."""
    root = _docs_root()
    if not root.is_dir():
        logger.warning("System docs root missing: %s", root)
        return []
    categories: List[Dict[str, Any]] = []
    loose = _loose_docs(root)
    if loose:
        categories.append(_category_entry(GENERAL_CATEGORY, _humanize(GENERAL_CATEGORY), len(loose)))
    for cat_dir in _category_dirs(root):
        docs = list(_iter_markdown(cat_dir))
        if docs:
            categories.append(_category_entry(cat_dir.name, _humanize(cat_dir.name), len(docs)))
    return categories


def _category_files(root: Path, category_path: str) -> List[Path]:
    """Resolve the markdown files belonging to a category (traversal-safe)."""
    if category_path == GENERAL_CATEGORY:
        return _loose_docs(root)
    base = root / category_path
    if not _within(base, root) or not base.is_dir():
        return []
    return list(_iter_markdown(base))


def list_category_docs(category_path: str) -> List[Dict[str, Any]]:
    """List documents in a category (metadata only, no content)."""
    root = _docs_root()
    if not root.is_dir():
        return []
    files = _category_files(root, category_path)
    return [_build_doc(path, root, category_path, include_content=False) for path in files]


def get_doc(doc_id: str) -> Optional[Dict[str, Any]]:
    """Return a single document (with full content) by its opaque id."""
    root = _docs_root()
    if not root.is_dir():
        return None
    for path in _iter_markdown(root):
        rel = path.relative_to(root).as_posix()
        if _doc_id(rel) == doc_id:
            category = rel.split("/", 1)[0] if "/" in rel else GENERAL_CATEGORY
            return _build_doc(path, root, category, include_content=True)
    return None
