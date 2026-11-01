# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""The manager methods the conversation-file routes call (#20225).

``api/conversation_files.py`` called ``upload_file``, ``get_file_info``, ``delete_file`` and
``transfer_files``, which ``ConversationFileManager`` never defined. They are thin adapters over the
manager's own storage (``add_file``, its SQLite rows, its soft delete) and write no store of their own.
A mixin in its own module because ``conversation_file_manager.py`` is at its size ceiling.
"""

from __future__ import annotations

import mimetypes
from typing import Any, Dict, List

from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)

#: The ``conversation_files`` columns a route returns, named as ``ConversationFileInfo`` names them.
#: ``uploaded_by`` is nullable in storage (agent-created files may have none); it is returned as stored.
FILE_INFO_COLUMNS = """
    cf.file_id, cf.session_id, cf.original_filename AS filename,
    cf.original_filename, cf.stored_filename, cf.file_path,
    cf.file_size AS size, cf.file_hash, cf.mime_type, cf.uploaded_at,
    cf.uploaded_by, cf.is_deleted, cf.deleted_at,
    LOWER(SUBSTR(cf.original_filename, INSTR(cf.original_filename, '.') + 1)) AS extension
"""


class ConversationFileRouteApi:
    """Route-facing methods, mixed into ``ConversationFileManager`` (uses its connection, lock, cache)."""

    async def upload_file(
        self, session_id: str, filename: str, content: bytes, user_id: str | None, description: str | None = None
    ) -> Dict[str, Any]:
        """Store an uploaded file via ``add_file`` and return it shaped as ``ConversationFileInfo``."""
        mime_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
        stored = await self.add_file(
            session_id,
            content,
            filename,
            mime_type=mime_type,
            uploaded_by=user_id,
            metadata={"description": description} if description else None,
        )
        extension = filename.rsplit(".", 1)[-1].lower() if "." in filename else None
        return {**stored, "filename": filename, "size": stored["file_size"], "extension": extension}

    async def get_file_info(self, session_id: str, file_id: str) -> Dict[str, Any] | None:
        """The live file ``file_id`` of ``session_id`` as a ``ConversationFileInfo`` dict, else ``None``."""
        connection = await self._get_async_db_connection()
        try:
            async with connection.execute(
                f"""
                SELECT {FILE_INFO_COLUMNS}
                FROM conversation_files cf
                JOIN session_file_associations sfa ON cf.file_id = sfa.file_id
                WHERE cf.file_id = ? AND sfa.session_id = ? AND cf.is_deleted = 0
                LIMIT 1
                """,  # nosec B608  # FILE_INFO_COLUMNS is a hardcoded constant
                (file_id, session_id),
            ) as cursor:
                row = await cursor.fetchone()
            return dict(row) if row else None
        finally:
            await connection.close()

    async def session_has_file_rows(self, session_id: str) -> bool:
        """Whether any file was ever associated with *session_id*. Raises when the store is unreadable (#20195)."""
        connection = await self._get_async_db_connection()
        try:
            async with connection.execute(
                "SELECT 1 FROM session_file_associations WHERE session_id = ? LIMIT 1", (session_id,)
            ) as cursor:
                return await cursor.fetchone() is not None
        finally:
            await connection.close()

    async def _release_session_file(self, connection, session_id: str, file_id: str) -> None:
        """Drop this session's link to the file; soft-delete the file only if no session still links it."""
        await connection.execute(
            "DELETE FROM session_file_associations WHERE session_id = ? AND file_id = ?", (session_id, file_id)
        )
        async with connection.execute(
            "SELECT 1 FROM session_file_associations WHERE file_id = ? LIMIT 1", (file_id,)
        ) as cursor:
            still_linked = await cursor.fetchone()
        if not still_linked:
            await self._soft_delete_file(connection, file_id)

    async def delete_file(self, session_id: str, file_id: str, user_id: str | None = None) -> bool:
        """Remove one file from a session; soft-delete it only when no other session still links it."""
        async with self._lock:
            connection = await self._get_async_db_connection()
            try:
                try:
                    await self._lookup_session_file(connection, session_id, file_id)
                except RuntimeError:
                    return False
                await self._release_session_file(connection, session_id, file_id)
                await connection.commit()
            except Exception:
                await connection.rollback()
                raise
            finally:
                await connection.close()
        await self._invalidate_session_cache(session_id)
        await self._log_access(file_id, "delete", user_id, {"session_id": session_id})
        return True

    async def transfer_files(
        self,
        session_id: str,
        file_ids: List[str],
        destination: str,
        target_path: str | None = None,
        copy: bool = False,
        tags: List[str] | None = None,
        user_id: str | None = None,
    ) -> Dict[str, Any]:
        """Send files to the knowledge base or the shared file root; a move also removes the source."""
        from conversation_file_transfer import transfer_one

        done: List[Dict[str, str]] = []
        failed: List[Dict[str, str]] = []
        for file_id in file_ids:
            try:
                info = await self.get_file_info(session_id, file_id)
                if info is None:
                    raise LookupError("File not found in this conversation")
                entry = await transfer_one(info, destination, target_path, tags, user_id)
            except Exception as exc:  # one file failing must not abort the rest of the batch
                logger.warning("Transfer of %s failed: %s", file_id, exc)
                failed.append({"file_id": file_id, "error": str(exc)})
                continue
            if not copy:
                await self._remove_moved_source(session_id, file_id, user_id, entry)
            done.append(entry)
        return {
            "transferred_files": done,
            "failed_files": failed,
            "total_transferred": len(done),
            "total_failed": len(failed),
        }

    async def _remove_moved_source(
        self, session_id: str, file_id: str, user_id: str | None, entry: Dict[str, str]
    ) -> None:
        """Remove a moved file's source. The copy exists, so a failure here never un-reports the transfer.

        It is recorded on the transferred entry as ``source_delete_error`` and nothing is rolled back: undoing
        the destination would delete data that is correct and may already be in use there.
        """
        try:
            await self.delete_file(session_id, file_id, user_id)
        except Exception as exc:
            logger.warning("Transferred %s but could not remove its source: %s", file_id, exc)
            entry["source_delete_error"] = str(exc)
