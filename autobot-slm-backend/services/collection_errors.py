# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The one decision between an operational failure and a programming error (#21334).

A lookup that feeds an operator-visible verdict ("nothing to update") must not turn
an error into an empty result. Expected operational failures are reported as
"could not determine"; anything else is a programming error and propagates.
"""

from sqlalchemy.exc import SQLAlchemyError

from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)

# DB session and query failures (SQLAlchemyError) and filesystem reads (OSError).
OPERATIONAL_COLLECTION_ERRORS = (SQLAlchemyError, OSError)


def operational_failure_reason(what: str, exc: BaseException) -> str:
    """Return the operator-facing "could not determine" reason for an operational *exc*.

    Re-raises *exc* when it is not an expected operational error, so a programming
    error is never reported as an empty, successful result.
    """
    if not isinstance(exc, OPERATIONAL_COLLECTION_ERRORS):
        raise exc
    logger.warning("Could not determine %s: %s", what, exc)
    return f"Could not determine {what}: {type(exc).__name__}"
