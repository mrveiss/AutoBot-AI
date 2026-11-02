# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tell the caller of a deactivating or deleting route whether the revocation took effect (#20443, option B).

The revocation marker is written after the commit. In the session-scope dependency that happens after
the route has answered, so a failed write reached only the server log and the caller was told 200.
A route that deactivates or deletes commits through :func:`commit_reporting_revocation` instead, so it
learns of the failure while it can still answer.

The change stays committed. The answer is 503 (not 500: nothing is broken in the request, the revocation
store is unavailable) and says the change applied but existing sessions may not have been revoked. Repeating
the request is safe and re-attempts the marker: deactivating an inactive account or organisation queues it
again, and so does deleting one that was soft-deleted. A hard-deleted account or organisation cannot be
retried, because its rows and usernames are gone, and neither can a rename, because the old name is no longer
known; those tokens stay live until they expire, and the rename's answer says so.
"""

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from autobot_shared.db_session import PostCommitCallbackError, commit_and_run_post_commit
from autobot_shared.user_management.password_epoch import PasswordEpochWriteError

#: What the caller is told; no username, store name or count (the server log has them).
REVOCATION_INCOMPLETE_MESSAGE = (
    "The change was applied, but existing sessions may not have been revoked. "
    "Repeat the request to retry the revocation."
)

#: A rename cannot be retried: repeating it changes nothing, so no marker for the old name is queued.
RENAME_REVOCATION_INCOMPLETE_MESSAGE = (
    "The change was applied, but sessions issued under the old username may not have been revoked. "
    "They end when they expire."
)


class RevocationIncompleteError(RuntimeError):
    """The change committed but a revocation marker could not be recorded."""


async def commit_reporting_revocation(session: AsyncSession) -> None:
    """Commit and run the post-commit callbacks; raise :class:`RevocationIncompleteError` if a marker failed.

    Any other failed callback (a cache bump) is not a revocation failure and propagates as it was.
    """
    try:
        await commit_and_run_post_commit(session)
    except PostCommitCallbackError as exc:
        if any(isinstance(error, PasswordEpochWriteError) for error in exc.errors):
            raise RevocationIncompleteError(REVOCATION_INCOMPLETE_MESSAGE) from exc
        raise


async def commit_or_503(session: AsyncSession, message: str = REVOCATION_INCOMPLETE_MESSAGE) -> None:
    """:func:`commit_reporting_revocation`, answering an incomplete revocation as HTTP 503."""
    try:
        await commit_reporting_revocation(session)
    except RevocationIncompleteError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail=message) from exc
