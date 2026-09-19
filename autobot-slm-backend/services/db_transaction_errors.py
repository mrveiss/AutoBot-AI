# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tell a connection-level DB failure apart from a row-level one (#17070).

A row-level failure (IntegrityError, a bad value hitting a constraint) is
safely absorbed by a SAVEPOINT rollback -- the connection is fine, only that
one statement's effects are undone. A connection-level failure (a lost or
timed-out connection) can't be recovered that way: a caller must stop
issuing statements on the session and abort the whole operation rather
than continue against a connection that's already gone.
"""

from sqlalchemy.exc import DBAPIError, InterfaceError, OperationalError


def is_connection_level_db_error(exc: BaseException) -> bool:
    """True when *exc* leaves the connection itself unusable, not just one statement."""
    if isinstance(exc, (TimeoutError, OperationalError, InterfaceError)):
        return True
    return isinstance(exc, DBAPIError) and getattr(exc, "connection_invalidated", False)
