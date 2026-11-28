# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Request bodies of the code-search routes; each names the source whose index it reads or fills (#20402).

Split out of ``schemas_code.py`` (which re-exports them) so that grandfathered module does not grow.
"""

from pydantic import BaseModel

from api.source_scope import SourceIdBody


class CodeSearchIndexRequest(BaseModel):
    root_path: str
    source_id: SourceIdBody  # the source whose index keys this root fills
    force_reindex: bool = False


class CodeSearchRequest(BaseModel):
    query: str
    source_id: SourceIdBody  # search is limited to this source's index
    search_type: str = "semantic"
    language: str | None = None
    max_results: int = 20


class CodeAnalyticsRequest(BaseModel):
    # Only the source's index is read, so no other filter can apply: refuse one, never ignore it (#20014, #20402).
    model_config = {"extra": "forbid"}

    root_path: str
    source_id: SourceIdBody
