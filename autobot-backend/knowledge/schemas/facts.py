# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Backward-compat re-exports for knowledge-base fact schemas.

Classes have been split into focused sub-modules per Issue #5486:

- :mod:`knowledge.schemas.ingestion` — add/upload/clear response shapes
- :mod:`knowledge.schemas.entries`   — stored entry retrieval shapes
- :mod:`knowledge.schemas.query`     — search/query response shapes

Import directly from those modules in new code.  Existing callers that
import from ``knowledge.schemas.facts`` continue to work unchanged.
"""

from __future__ import annotations

from knowledge.schemas.entries import (  # noqa: F401
    FactByCategoryEntry,
    FactByKeyResponse,
    FactsByCategoryResponse,
    KnowledgeEntriesResponse,
    KnowledgeEntry,
)
from knowledge.schemas.ingestion import (  # noqa: F401
    AddFactResponse,
    AddTextResponse,
    AddUrlResponse,
    AudioIngestResponse,
    ClearAllResponse,
    UploadFileResponse,
)
from knowledge.schemas.query import (  # noqa: F401
    ManPageSearchResponse,
    QueryKnowledgeResponse,
)
