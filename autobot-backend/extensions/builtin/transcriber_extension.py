# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Transcriber builtin extension.

Mounts all transcriber routes under /api/transcriber and manages
DB lifecycle (connect on app startup, close on shutdown).
Enabled via TRANSCRIBER_ENABLED=true in environment.

The module-level ``router`` attribute is consumed by feature_routers.py
(``_load_single_router`` fetches ``module.router`` via ``getattr``).
``get_transcriber_router()`` is provided for callers that prefer the
factory-function style and for unit-test assertions.
"""
import os
from pathlib import Path

from fastapi import APIRouter

from autobot_shared.logging_manager import get_logger
from extensions.base import Extension, HookContext

logger = get_logger(__name__)

_ENABLED = os.getenv("TRANSCRIBER_ENABLED", "true").lower() == "true"
_DATA_DIR = Path(os.getenv("TRANSCRIBER_DATA_DIR", "data/transcriber"))


def get_transcriber_router() -> APIRouter:
    """Return a combined APIRouter with all transcriber sub-routers.

    Both the projects and recordings sub-routers are included under the
    shared /api/transcriber prefix so feature_routers.py can mount the
    result at the top-level application with a single include_router call.
    """
    from transcriber.routes.projects import router as projects_router
    from transcriber.routes.recordings import router as recordings_router

    combined = APIRouter(prefix="/api/transcriber")
    combined.include_router(projects_router)
    combined.include_router(recordings_router)
    return combined


# Module-level router consumed by feature_routers._load_single_router via
# ``getattr(module, "router")``.  Built once at import time so repeated
# calls to load_feature_routers() in test environments get the same object.
router: APIRouter = get_transcriber_router()


class TranscriberExtension(Extension):
    """Builtin extension that registers the transcriber module.

    The Extension base class provides agent-lifecycle hooks (HookPoint-based).
    App-level DB startup/shutdown is wired separately in
    ``initialization/lifespan.py`` via ``_init_transcriber_db()`` and
    ``cleanup_services()``.  This class exists so the extension manager
    can discover and track the transcriber feature by name.

    Attributes:
        name: ``"transcriber"``
        priority: 10 (runs before default-priority extensions)
    """

    name = "transcriber"
    priority = 10
