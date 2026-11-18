# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The one cron-syntax validator for the backend and the SLM (#18449, contract #18432).

The schedule contract pins cron to the STANDARD 5-field form and reports a bad
expression as the stable code ``schedule.invalid_cron`` (a 6-field or unparseable
cron).  Before this module the backend had a hand-written parser and the SLM
used croniter unrestricted, so the same string validated in one service and not
the other.  croniter is the engine (it is also what the schedulers run), and the
5-field restriction is applied here, once, because croniter on its own happily
accepts a 6th "seconds" field.

This module decides VALIDITY only, not firing semantics, and the two services
deliberately differ there (owner decision on #18449, no stored schedule changes
frequency): the backend triggers evaluate with ``croniter(..., day_or=False)`` so a
schedule restricting both day-of-month and day-of-week fires only when BOTH match
(the behaviour of the parser they replaced), which differs from standard cron. The SLM
schedule executor keeps croniter's default, standard-cron OR.
"""

from __future__ import annotations

import logging

from croniter import croniter  # type: ignore[import-untyped]  # no stubs shipped

#: Stable error code for a 6-field or unparseable cron (#18432).
INVALID_CRON_ERROR_CODE = "schedule.invalid_cron"

CRON_FIELD_COUNT = 5


def validate_cron_expression(expression: str) -> bool:
    """True when *expression* is a valid standard 5-field cron string."""
    if not isinstance(expression, str) or len(expression.split()) != CRON_FIELD_COUNT:
        return False
    try:
        return bool(croniter.is_valid(expression))
    except (ValueError, KeyError, TypeError):
        return False


def log_stored_cron_findings(logger: logging.Logger, kind: str, item_id: str, expression: str) -> bool:
    """Warn about a STORED cron that is no longer valid; True when it is valid.

    The warning names the owner's id and ``schedule.invalid_cron``. Report-only:
    nothing is rewritten, and what to do with an invalid one is the caller's call (#18449).
    """
    if validate_cron_expression(expression):
        return True
    logger.warning("%s %s: stored cron %r is invalid (%s)", kind, item_id, expression, INVALID_CRON_ERROR_CODE)
    return False
