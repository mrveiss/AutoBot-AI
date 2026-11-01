# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Where ``ConversationFileManager.transfer_files`` sends a file: the knowledge base or the shared root (#20225).

``shared`` is the file browser's sandbox root (the ``file_manager_root`` data path that ``api/files.py``
serves), reached only through the shared sandbox resolver so a target path cannot leave it.
"""

from __future__ import annotations

import asyncio
import os
import shutil
import uuid
from pathlib import Path, PurePosixPath
from typing import Dict, List

import aiofiles

from autobot_shared.scoping import ScopeLevel
from autobot_shared.security.path_validator import resolve_within_sandbox
from knowledge_factory import get_knowledge_base_async
from utils.paths_manager import get_data_path

SHARED_ROOT = get_data_path("file_manager_root").resolve()


def _shared_target(info: Dict, target_path: str | None) -> Path:
    """The destination file inside the shared root. An absolute ``target_path`` is refused, not re-rooted."""
    if target_path and PurePosixPath(target_path).is_absolute():
        raise ValueError("target_path must be relative to the shared root")
    name = PurePosixPath(info["original_filename"]).name
    relative = str(PurePosixPath(target_path or "") / name)
    return resolve_within_sandbox(relative, SHARED_ROOT)


def _copy_into_place(source: str, target: Path) -> None:
    """Copy ``source`` to ``target`` without ever overwriting it or leaving a partial file there.

    The bytes go to a temp file this call creates (exclusive create) beside the target, then ``os.link``
    publishes it: link fails with ``FileExistsError`` if anything, even a symlink, is already at the
    target, so a concurrent transfer can never be overwritten. Only the temp is ever unlinked.
    """
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.parent / f".{target.name}.{uuid.uuid4().hex}.transfer"
    try:
        with open(source, "rb") as src, open(temp, "xb") as dst:
            shutil.copyfileobj(src, dst)
        try:
            os.link(temp, target)
        except FileExistsError:
            raise FileExistsError(f"'{target.relative_to(SHARED_ROOT)}' already exists in shared storage") from None
    finally:
        temp.unlink(missing_ok=True)


async def _to_shared(info: Dict, target_path: str | None) -> Dict[str, str]:
    target = _shared_target(info, target_path)
    await asyncio.to_thread(_copy_into_place, info["file_path"], target)
    return {"file_id": info["file_id"], "destination": "shared", "path": str(target.relative_to(SHARED_ROOT))}


async def _to_knowledge_base(info: Dict, tags: List[str] | None, user_id: str | None) -> Dict[str, str]:
    kb = await get_knowledge_base_async()
    if kb is None:
        raise RuntimeError("Knowledge base is not available")
    try:
        async with aiofiles.open(info["file_path"], "r", encoding="utf-8") as handle:
            text = await handle.read()
    except UnicodeDecodeError:
        raise ValueError("Only text files can be added to the knowledge base")
    owner_id = info.get("uploaded_by") or user_id
    if not owner_id:
        raise ValueError("The file has no resolvable owner; it is not added to the knowledge base")
    metadata = {
        "source": info["original_filename"],
        "tags": tags or [],
        "origin": "conversation_file",
        "session_id": info["session_id"],
        "uploaded_by": user_id,
        # The uploader's own, never shared: same shape as knowledge/claude_memory_importer.py (#20233).
        "owner_id": owner_id,
        "visibility": ScopeLevel.PRIVATE.value,
    }
    result = await kb.add_document(text, metadata, info["file_id"])
    if result.get("status") != "success":
        raise RuntimeError(result.get("message") or f"Knowledge base ingest {result.get('status')}")
    return {"file_id": info["file_id"], "destination": "kb"}


async def transfer_one(
    info: Dict, destination: str, target_path: str | None, tags: List[str] | None, user_id: str | None
) -> Dict[str, str]:
    """Copy one conversation file to ``destination`` ("kb" or "shared"); raises on any failure."""
    if destination == "shared":
        return await _to_shared(info, target_path)
    if destination == "kb":
        return await _to_knowledge_base(info, tags, user_id)
    raise ValueError(f"Unknown destination '{destination}'")
