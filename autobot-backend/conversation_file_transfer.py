# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Where ``ConversationFileManager.transfer_files`` sends a file: the knowledge base or the shared root (#20225).

``shared`` is the file browser's sandbox root (the ``file_manager_root`` data path that ``api/files.py``
serves), reached only through the shared sandbox resolver so a target path cannot leave it.
"""

from __future__ import annotations

import asyncio
import shutil
from pathlib import Path, PurePosixPath
from typing import Dict, List

import aiofiles

from autobot_shared.security.path_validator import resolve_within_sandbox
from knowledge_factory import get_knowledge_base_async
from utils.paths_manager import get_data_path

SHARED_ROOT = get_data_path("file_manager_root").resolve()


def _shared_target(info: Dict, target_path: str | None) -> Path:
    """The destination file inside the shared root; an existing file is never overwritten."""
    name = PurePosixPath(info["original_filename"]).name
    relative = str(PurePosixPath(target_path or "") / name)
    target = resolve_within_sandbox(relative, SHARED_ROOT)
    if target.exists():
        raise FileExistsError(f"'{relative}' already exists in shared storage")
    return target


async def _to_shared(info: Dict, target_path: str | None) -> Dict[str, str]:
    target = _shared_target(info, target_path)
    await asyncio.to_thread(target.parent.mkdir, parents=True, exist_ok=True)
    await asyncio.to_thread(shutil.copyfile, info["file_path"], target)
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
    metadata = {
        "source": info["original_filename"],
        "tags": tags or [],
        "origin": "conversation_file",
        "session_id": info["session_id"],
        "uploaded_by": user_id,
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
