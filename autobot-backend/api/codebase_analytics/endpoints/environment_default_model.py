# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The env-analysis AI filter's default model, served to the UI (#15502).

The frontend holds no model literal; it reads the name from here. This is the same constant the
``llm_model`` query default of ``/env-analysis`` (``environment.py``) binds to. It is its own
module because ``environment.py`` is a grandfathered large file that may not grow.
"""

from fastapi import APIRouter

from autobot_shared.error_boundaries import bounded
from autobot_shared.ssot_config import QUALITY_MODEL

router = APIRouter()


@router.get("/env-analysis/default-model")
@bounded(60.0)
async def get_env_analysis_default_model() -> dict[str, str]:
    """The model the AI false-positive filter uses when the caller names none."""
    return {"model": QUALITY_MODEL}
