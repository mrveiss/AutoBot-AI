#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The modern ``langchain-redis`` arm of the Redis vector-store comparison (#14871).

The three analysis scripts beside this module exist to compare the modern
``langchain_redis.RedisVectorStore`` against the legacy
``langchain_community.vectorstores.redis`` path. ``langchain_redis`` was
declared in no requirements file in the repository, and each script caught its
absence in a broad ``except Exception`` that reported the arm as **FAILED** —
identical to the arm having run and lost.

That is the whole defect: a comparison whose modern arm was never measured
produced a report recommending the legacy path, and nothing in the output said
which of the two had happened. An import that cannot resolve has to be loud,
not quietly reduce what the code does.

The package is now declared in
``autobot-infrastructure/shared/scripts/requirements.txt``, so the arm runs on a
provisioned machine. This module is what makes the remaining case honest: when
the package really is absent, the arm reports ``NOT_MEASURED`` rather than a
verdict, and every consumer renders and reasons about that state separately
from a measured failure.
"""

from __future__ import annotations

from typing import Any, List, Sequence, Tuple

from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)

#: The assessment value every consumer checks for. A run carrying this did not
#: measure the modern arm at all, so no comparison against it is meaningful.
NOT_MEASURED = "NOT_MEASURED"

#: What an operator has to do to make the arm measurable. Named once so the
#: three scripts cannot drift apart on the remediation they print.
INSTALL_HINT = "pip install -r autobot-infrastructure/shared/scripts/requirements.txt"


class ModernArmUnavailable(RuntimeError):
    """``langchain_redis`` is not importable, so the modern arm cannot run."""


def load_redis_vector_store() -> Any:
    """Return ``langchain_redis.RedisVectorStore`` or raise ``ModernArmUnavailable``.

    Deliberately narrow: only ``ImportError`` becomes ``ModernArmUnavailable``.
    Any other exception is a real failure of the modern arm and must reach the
    caller's failure path unchanged.
    """
    try:
        from langchain_redis import RedisVectorStore
    except ImportError as exc:
        raise ModernArmUnavailable(
            "langchain-redis is not installed, so the modern vector-store arm "
            f"was NOT measured. Install it with: {INSTALL_HINT} (#14871)"
        ) from exc
    return RedisVectorStore


def skipped_result(exc: ModernArmUnavailable) -> Tuple[bool, int, str]:
    """The ``(success, count, assessment)`` triple every script returns for a skipped arm.

    ``success`` is False because nothing succeeded, but ``assessment`` is
    ``NOT_MEASURED`` so a reader — and ``was_skipped`` below — can tell this
    apart from an arm that ran and failed.
    """
    logger.warning("Modern langchain-redis arm NOT MEASURED: %s", exc)
    return False, 0, NOT_MEASURED


def skipped_steps(exc: ModernArmUnavailable) -> Tuple[bool, int, List[str]]:
    """``skipped_result`` for the scripts whose third element is a step list.

    ``redis_final_analysis`` reports progress as a list of steps attempted
    rather than a single assessment string, so the marker has to travel inside
    the list. ``was_skipped`` below understands both shapes.
    """
    logger.warning("Modern langchain-redis arm NOT MEASURED: %s", exc)
    return False, 0, [NOT_MEASURED, str(exc)]


def was_skipped(result: Sequence[Any]) -> bool:
    """Did this arm's result come from ``skipped_result``/``skipped_steps``?

    Handles both third-element shapes. A bare ``result[2] == NOT_MEASURED``
    test silently answers False for the list shape, which would put a skipped
    arm straight back into the FAILED bucket this module exists to keep it out
    of.
    """
    if len(result) < 3:
        return False
    marker = result[2]
    if isinstance(marker, str):
        return marker == NOT_MEASURED
    if isinstance(marker, (list, tuple)):
        return NOT_MEASURED in marker
    return False


def status_label(result: Sequence[Any], ok: str = "OK") -> str:
    """Render an arm's outcome without collapsing 'not measured' into 'failed'."""
    if was_skipped(result):
        return "NOT MEASURED"
    return ok if result[0] else "FAILED"
