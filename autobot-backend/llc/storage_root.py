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

This function reads the env var at call time, and `kb/artifact_ingestor.py`
calls it that way -- which is why a test can set `LLC_STORAGE_PATH` with
`monkeypatch.setenv` and have the ingestor honour it.

`services/attachment_service.py` does NOT get that: it still binds
`_LOCAL_STORAGE_PATH` once at import, exactly as it did before this module
existed, and its tests patch that module attribute directly rather than the
env var. So the freshness is a property of *this function*, not of every
consumer -- stated explicitly because the first version of this docstring
claimed it for "a test or a deployment" generally, which is true for one
caller and false for the other.

The two would only disagree if `LLC_STORAGE_PATH` changed after
`attachment_service` was imported; nothing does that today, and the honest
description is a latent inconsistency rather than a live bug.
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
