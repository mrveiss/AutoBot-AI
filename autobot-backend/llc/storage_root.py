# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The one root every LLC artefact path must resolve inside (#17302).

Defined here rather than in `services/attachment_service.py` because it is no
longer only the attachment writer's concern: `kb/artifact_ingestor.py` needs the
same root to decide whether a work product's `storage_path` is somewhere this
service put it, and a second copy of the env var and its default is how the two
drift apart.

Read at call time, not at import, so a test or a deployment that sets
`LLC_STORAGE_PATH` late still gets the root it asked for.
"""

from __future__ import annotations

import os
from pathlib import Path

#: Env var naming the local storage root. Unprefixed and pre-existing; kept as
#: the single spelling rather than introduced here.
LLC_STORAGE_PATH_ENV = "LLC_STORAGE_PATH"


def llc_local_storage_root() -> Path:
    """The configured LLC local-storage root, or the per-user default."""
    configured = os.getenv(LLC_STORAGE_PATH_ENV)
    if configured:
        return Path(configured)
    return Path.home() / ".autobot" / "llc" / "attachments"
