# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Service-layer helpers for CodeSource create/delete so non-HTTP callers
(the LLC project layer, #11129) can reuse the same logic as the sources API."""

from __future__ import annotations

import asyncio
import uuid

from autobot_shared.logging_manager import get_logger

from .source_models import CodeSource, SourceAccess, SourceType
from .source_paths import make_clone_path
from .source_storage import save_source

logger = get_logger(__name__)


async def create_github_source(
    *,
    name: str,
    repo: str,
    credential_id: str | None,
    branch: str = "main",
    owner_id: str | None = None,
    access: SourceAccess = SourceAccess.PRIVATE,
    auto_sync: bool = True,
) -> CodeSource:
    """Create + persist a GitHub CodeSource and (optionally) kick off its sync.

    Extracted from endpoints/sources.py::create_code_source (#11129) so the
    LLC project layer can create a CodeSource without going through HTTP.
    """
    source = CodeSource(
        name=name,
        source_type=SourceType.GITHUB,
        repo=repo,
        branch=branch,
        credential_id=credential_id,
        owner_id=owner_id,
        access=access,
    )
    source.clone_path = make_clone_path(source.id)
    await save_source(source)
    logger.info("Created github CodeSource %s for repo %s", source.id, repo)

    if auto_sync:
        # Import here to avoid a circular import with endpoints/sources.py.
        from .endpoints.sources import _create_sync_cleanup, _do_sync
        from .scanner import _active_tasks

        sync_task_id = str(uuid.uuid4())
        task = asyncio.create_task(_do_sync(source))
        _active_tasks[sync_task_id] = task
        task.add_done_callback(_create_sync_cleanup(sync_task_id))
        logger.info("Auto-sync started for new source %s (task %s)", source.id, sync_task_id)

    return source
