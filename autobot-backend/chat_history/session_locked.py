# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Locked read-modify-write of a chat file: the one way a session file is changed (#20862).

``_locked_update`` takes the session's Redis lease, re-reads the file under it, applies the
caller's change to what is on disk now, fences the write with the lease's generation and writes.
Save, metadata, owner and rename writes all go through it, so no route writes a snapshot that
was loaded before it waited.
"""

import os
import time
from typing import TYPE_CHECKING, Any, Awaitable, Callable, Dict, Optional, Tuple

from autobot_shared.logging_manager import get_logger
from autobot_shared.security.path_validator import validate_relative_path
from chat_history.file_io import run_in_chat_io_executor
from chat_history.session_lease import (
    ChatFileUnreadable,
    SessionLease,
    SessionLeaseError,
    StaleGenerationError,
    file_generation,
    session_lease,
)

logger = get_logger(__name__)

Mutation = Callable[[Dict[str, Any]], None]
AfterWrite = Callable[[str, Dict[str, Any]], Awaitable[None]]


def _stat_signature(name: str, directory: str) -> Optional[Tuple[int, int]]:
    """Modification time and size of chat file *name* under *directory*, or None when it does not exist.

    Containment is checked here, where the file is touched, like ``existing_chat_path``.
    """
    try:
        stat = os.stat(str(validate_relative_path(name, directory)))
    except FileNotFoundError:
        return None
    return (stat.st_mtime_ns, stat.st_size)


class SessionLockMixin:
    """Lease-guarded session mutations; requires the session and file-I/O mixins."""

    if TYPE_CHECKING:  # provided by SessionMixin / the manager; declared so the types of this mixin check

        @staticmethod
        def _sanitize_session_id(session_id: str) -> None: ...

        def _get_chats_directory(self) -> str: ...

        async def _ensure_chats_directory_exists(self, chats_directory: str) -> None: ...

        async def _resolve_session_file_path(self, session_id: str, chats_directory: str) -> str | None: ...

        async def _load_existing_chat_data(
            self, session_id: str, chat_file: str, chats_directory: str
        ) -> Dict[str, Any]: ...

        async def _write_session_to_storage(
            self, chat_file: str, chat_data: Dict[str, Any], before_replace: Callable[[], Awaitable[None]] | None = None
        ) -> None: ...

        async def _update_redis_session_cache(self, session_id: str, chat_data: Dict[str, Any]) -> None: ...

        async def _delete_session_files(self, session_id: str, chats_directory: str) -> bool: ...

        async def _delete_companion_files(self, session_id: str, chats_directory: str) -> None: ...

        async def _clear_session_redis_cache(self, session_id: str) -> None: ...

    async def _stored_generation(
        self, session_id: str, chats_directory: str, read_generation: int, read_signature: Any
    ) -> int:
        """The generation in the file now; re-read only when the file changed since it was read."""
        name = f"{session_id}_chat.json"
        if await run_in_chat_io_executor(_stat_signature, name, chats_directory) == read_signature:
            return read_generation
        chat_file = str(validate_relative_path(name, chats_directory))
        return file_generation(await self._load_existing_chat_data(session_id, chat_file, chats_directory))

    async def _read_for_update(
        self, session_id: str, chats_directory: str, lease: SessionLease
    ) -> Tuple[Dict[str, Any], int, Any]:
        """Re-read the file under the lease and allocate the fencing generation above the file's."""
        name = f"{session_id}_chat.json"
        signature = await run_in_chat_io_executor(_stat_signature, name, chats_directory)
        chat_file = str(validate_relative_path(name, chats_directory))
        chat_data = await self._load_existing_chat_data(session_id, chat_file, chats_directory)
        read_generation = file_generation(chat_data)
        await lease.begin(read_generation)
        return chat_data, read_generation, signature

    def _fence_at_file(
        self, session_id: str, chats_directory: str, lease: SessionLease, read_generation: int, signature: Any
    ) -> Callable[[], Awaitable[None]]:
        """The check run immediately before ``os.replace``: the lease is ours and the file is not newer.

        The lease can be lost, and another writer land a newer generation, between the fence and the
        rename. Re-reading the file's generation here, as the write's last step before the rename, refuses
        the write (nothing is replaced) instead of overwriting the newer content.
        """

        async def check() -> None:
            await lease.verify()
            on_disk = await self._stored_generation(session_id, chats_directory, read_generation, signature)
            if on_disk > lease.generation:
                raise StaleGenerationError(session_id, lease.generation, on_disk)

        return check

    async def _locked_update(
        self,
        session_id: str,
        operation: str,
        mutate: Mutation,
        *,
        must_exist: bool = False,
        after: Optional[AfterWrite] = None,
    ) -> Optional[Dict[str, Any]]:
        """Apply *mutate* to the session's current file under its lease; None when *must_exist* and absent.

        Raises SessionLeaseTimeout (waited out, holder named), SessionLeaseLost or
        StaleGenerationError (nothing written); never writes unlocked.
        """
        self._sanitize_session_id(session_id)
        chats_directory = self._get_chats_directory()
        await self._ensure_chats_directory_exists(chats_directory)
        chat_file = str(validate_relative_path(f"{session_id}_chat.json", chats_directory))
        async with session_lease(session_id, operation) as lease:
            if must_exist and not await self._resolve_session_file_path(session_id, chats_directory):
                return None
            chat_data, read_generation, signature = await self._read_for_update(session_id, chats_directory, lease)
            mutate(chat_data)
            on_disk = await self._stored_generation(session_id, chats_directory, read_generation, signature)
            await lease.fence(chat_data, on_disk)
            guard = self._fence_at_file(session_id, chats_directory, lease, read_generation, signature)
            await self._write_session_to_storage(chat_file, chat_data, before_replace=guard)
            if after is not None:
                await after(session_id, chat_data)
        return chat_data

    async def update_session(self, session_id: str, updates: Dict[str, Any]) -> bool:
        """Update session fields (name, etc) under the session lease; True when the update was written."""
        try:

            def apply(chat_data: Dict[str, Any]) -> None:
                chat_data.update(updates)
                chat_data["last_modified"] = time.strftime("%Y-%m-%d %H:%M:%S")

            written = await self._locked_update(
                session_id, "update_session", apply, must_exist=True, after=self._update_redis_session_cache
            )
            if written is None:
                logger.warning("Session %s not found for update", session_id)
                return False
            logger.info("Session %s updated successfully", session_id)
            return True
        except SessionLeaseError:
            raise  # a lease timeout is not "not found"; the caller must be able to tell
        except Exception as e:
            logger.error("Error updating session %s: %s", session_id, e)
            return False

    async def update_session_name(self, session_id: str, name: str) -> bool:
        """Rename a chat session under the session lease; True when the new name was written."""
        try:

            def apply(chat_data: Dict[str, Any]) -> None:
                chat_data["name"] = name
                chat_data["last_modified"] = time.strftime("%Y-%m-%d %H:%M:%S")

            written = await self._locked_update(
                session_id, "rename_session", apply, must_exist=True, after=self._update_redis_session_cache
            )
            if written is None:
                logger.warning("Chat session %s not found for name update", session_id)
                return False
            logger.info("Chat session '%s' name updated to '%s'", session_id, name)
            return True
        except SessionLeaseError:
            raise
        except Exception as e:
            logger.error("Error updating chat session %s name: %s", session_id, e)
            return False

    async def update_session_metadata(self, session_id: str, metadata: Dict[str, Any]) -> bool:
        """Merge *metadata* into the stored session metadata under the session lease (#8993).

        The merge runs on the metadata read after the lease is held, so a concurrent owner
        change or message save is kept. True when written, False when the session is absent
        or the write failed.
        """
        try:

            def apply(chat_data: Dict[str, Any]) -> None:
                chat_data["metadata"] = {**(chat_data.get("metadata") or {}), **metadata}
                chat_data["last_modified"] = time.strftime("%Y-%m-%d %H:%M:%S")

            written = await self._locked_update(
                session_id, "update_metadata", apply, must_exist=True, after=self._update_redis_session_cache
            )
            if written is None:
                logger.warning("Session %s not found for metadata update", session_id)
                return False
            logger.info("Session %s metadata updated successfully", session_id)
            return True
        except SessionLeaseError:
            raise
        except Exception as e:
            logger.error("Error updating session metadata %s: %s", session_id, e)
            return False

    async def _peek_generation(self, session_id: str, chats_directory: str) -> int:
        """The file's fencing generation, 0 when it is absent or unreadable (a delete may remove either)."""
        chat_file = str(validate_relative_path(f"{session_id}_chat.json", chats_directory))
        try:
            return file_generation(await self._load_existing_chat_data(session_id, chat_file, chats_directory))
        except ChatFileUnreadable:
            return 0

    async def delete_session(self, session_id: str) -> bool:
        """Delete a chat session and its companion files under the session lease, fenced like a save.

        Without the lease a delete could land between another writer's read and write, and that
        write would bring the session back (#20862). True when a session file was removed.
        """
        try:
            self._sanitize_session_id(session_id)
            chats_directory = self._get_chats_directory()
            async with session_lease(session_id, "delete_session") as lease:
                await lease.begin(await self._peek_generation(session_id, chats_directory))
                await lease.fence({}, await self._peek_generation(session_id, chats_directory))
                deleted = await self._delete_session_files(session_id, chats_directory)
                await self._delete_companion_files(session_id, chats_directory)
                await self._clear_session_redis_cache(session_id)
            if not deleted:
                logger.warning("Chat session %s not found for deletion", session_id)
                return False
            logger.info("Chat session '%s' deleted successfully", session_id)
            return True
        except SessionLeaseError:
            raise
        except Exception as e:
            logger.error("Error deleting chat session %s: %s", session_id, e)
            return False
