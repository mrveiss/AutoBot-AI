# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Shared type definitions for AutoBot
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class TaskComplexity(Enum):
    SIMPLE = "simple"  # Regular conversation with Knowledge Base integration
    COMPLEX = "complex"  # Requires tools, research, or system actions

    # Legacy values for backward compatibility (map to COMPLEX)
    RESEARCH = "complex"
    INSTALL = "complex"
    SECURITY_SCAN = "complex"


class ClassificationState(str, Enum):
    """Why a complexity value has the value it does (#13807).

    ``COMPLEX`` used to be the answer to four different questions: the request
    really is complex, the classifier is not importable, it failed to build, or
    the call raised. One output for four states meant a permanently disabled
    classifier was indistinguishable from one working correctly.
    """

    CLASSIFIED = "classified"  # the classifier ran and returned this verdict
    UNAVAILABLE_IMPORT = "unavailable_import"  # classification module not importable
    UNAVAILABLE_INIT = "unavailable_init"  # agent could not be constructed
    FAILED = "failed"  # the classifier raised on this request


@dataclass(frozen=True)
class ComplexityVerdict:
    """A complexity value plus whether anything actually judged it.

    ``complexity`` stays usable by callers that only need a value to route on;
    ``classified`` is what lets a caller tell a judgement from a fallback.
    """

    complexity: TaskComplexity
    state: ClassificationState
    detail: Optional[str] = None

    @property
    def classified(self) -> bool:
        """True only when the classifier actually produced this verdict."""
        return self.state is ClassificationState.CLASSIFIED
