# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The LLM role's default model lists, read from the role itself (#19862).

No second copy: `roles/llm/defaults/main.yml` is where they live, and the settings page shows them
until someone saves a choice. Without this, Apply sent empty lists that overrode the role's defaults.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import List, Tuple

import yaml

_ROLE_DEFAULTS = Path(__file__).resolve().parents[1] / "ansible" / "roles" / "llm" / "defaults" / "main.yml"


@lru_cache(maxsize=1)
def default_llm_models() -> Tuple[List[str], List[str]]:
    """(GPU models, CPU models). Raises when the role's file cannot be read: nothing to fall back to."""
    defaults = yaml.safe_load(_ROLE_DEFAULTS.read_text(encoding="utf-8"))
    return list(defaults["llm_gpu_models"]), list(defaults["llm_cpu_models"])
