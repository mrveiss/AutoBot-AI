# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Dispatch of the session MCP file tools to the file manager (Issue #70).

Split out of ``api/conversation_files.py`` so that route module keeps to its size ceiling (#20678).
"""

from __future__ import annotations

from typing import Any, Dict

from security.upload_filename_policy import is_safe_file
from utils.catalog_http_exceptions import raise_invalid_input, raise_not_found


def _required_file_id(args: Dict) -> str:
    file_id = args.get("file_id")
    if not file_id:
        raise_invalid_input("file_id", "required")
    return file_id


async def _list_files(file_manager, session_id: str, args: Dict, quota_owner: str | None) -> Dict:
    result = await file_manager.list_files(session_id=session_id)
    return {"files": result.get("files", []), "total": result.get("total_files", 0)}


async def _read_file(file_manager, session_id: str, args: Dict, quota_owner: str | None) -> Dict:
    return await file_manager.get_file_content(session_id=session_id, file_id=_required_file_id(args))


async def _write_file(file_manager, session_id: str, args: Dict, quota_owner: str | None) -> Dict:
    filename = args.get("filename")
    content = args.get("content", "")
    if not filename:
        raise_invalid_input("filename", "required")
    if not is_safe_file(filename):
        raise_invalid_input("filename", f"invalid filename: {filename}")
    return await file_manager.create_file(
        session_id=session_id,
        filename=filename,
        content=content,
        mime_type=args.get("mime_type", "text/plain"),
        created_by="agent",
        file_type="generated",
        quota_owner=quota_owner,  # the conversation owner pays, not "agent" (#20678)
    )


async def _search_files(file_manager, session_id: str, args: Dict, quota_owner: str | None) -> Dict:
    query = args.get("query", "")
    results = await file_manager.search_files(session_id=session_id, query=query)
    return {"files": results, "total": len(results)}


async def _delete_file(file_manager, session_id: str, args: Dict, quota_owner: str | None) -> Dict:
    file_id = _required_file_id(args)
    deleted = await file_manager.delete_file(session_id, file_id)
    if not deleted:
        raise_not_found("File", file_id)
    return {"deleted": True, "file_id": file_id}


_HANDLERS = {
    "session_list_files": _list_files,
    "session_read_file": _read_file,
    "session_write_file": _write_file,
    "session_search_files": _search_files,
    "session_delete_file": _delete_file,
}


async def dispatch_mcp_tool(
    file_manager, session_id: str, tool_name: str, args: Dict, quota_owner: str | None = None
) -> Dict[str, Any]:
    """Dispatch an MCP tool call to the file manager; *quota_owner* is who ``session_write_file`` charges."""
    handler = _HANDLERS.get(tool_name)
    if handler is None:
        raise_invalid_input("tool_name", f"unknown tool: {tool_name}")
    return await handler(file_manager, session_id, args, quota_owner)
