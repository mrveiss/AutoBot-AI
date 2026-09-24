# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The severity/category vocabularies shared by the review engines and the API (#14881).

``api/schemas_analytics.py`` used to redeclare all four of these with members
identical to the ``code_intelligence`` originals, while
``api/analytics_precommit.py`` imported ``BUILTIN_CHECKS`` from that same
module -- one symbol imported and its enums hand-copied, with nothing keeping
the copies in step.

WHY THE SHARED TIER OWNS THEM RATHER THAN ``code_intelligence``
----------------------------------------------------------------
Pointing the API schema straight at ``code_intelligence.precommit_analyzer``
was the first attempt, and CI refused it for a reason that turns out to be the
design argument rather than a harness detail. ``autobot-backend/conftest.py``
stubs the whole ``code_intelligence`` package -- its ``__init__`` carries
imports the startup-import smoke environment cannot satisfy -- so the enums
resolved to ``MagicMock`` and every Pydantic model annotated with one failed to
build its schema:

    PydanticSchemaGenerationError: Unable to generate pydantic-core schema
    for <MagicMock ...>

A wire-format vocabulary the API cannot import without dragging in an analysis
engine is not owned by that engine. These four are shared *between* the engines
and the API, so they belong to neither and live here -- the same move #11290
made when it collapsed ``SecretScope``/``VisibilityLevel``/``ScopeLevel`` onto
one shared ``ScopeLevel``.

``str`` mixin on every one: the API serialises them to JSON and FastAPI needs a
real ``str``-enum for query and response models. The engines compare members,
which the mixin does not affect.

Both engines re-export their own pair, so existing
``from code_intelligence.precommit_analyzer import CheckSeverity`` call sites
keep working -- what moved is the definition, not the name.
"""

from __future__ import annotations

from enum import Enum

__all__ = [
    "CheckSeverity",
    "CheckCategory",
    "ReviewSeverity",
    "ReviewCategory",
]


class CheckSeverity(str, Enum):
    """Severity levels for pre-commit checks."""

    BLOCK = "block"  # Prevents commit
    WARN = "warn"  # Shows warning but allows commit
    INFO = "info"  # Informational only


class CheckCategory(str, Enum):
    """Categories of pre-commit checks."""

    SECURITY = "security"
    QUALITY = "quality"
    STYLE = "style"
    DEBUG = "debug"
    DOCS = "docs"


class ReviewSeverity(str, Enum):
    """Review comment severity levels."""

    CRITICAL = "critical"
    WARNING = "warning"
    INFO = "info"
    SUGGESTION = "suggestion"


class ReviewCategory(str, Enum):
    """Categories of review findings."""

    SECURITY = "security"
    PERFORMANCE = "performance"
    STYLE = "style"
    BUG_RISK = "bug_risk"
    MAINTAINABILITY = "maintainability"
    DOCUMENTATION = "documentation"
    TESTING = "testing"
    BEST_PRACTICE = "best_practice"
