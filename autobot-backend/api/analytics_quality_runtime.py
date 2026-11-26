# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The runtime-risk map of ONE source's checkout (#11184, #20513).

``build_runtime_risk_map`` aggregates every known failure pattern, keyed by repo-relative file path, and
records no source. A source's quality page may only show the entries whose file is in its own checkout.
"""

from __future__ import annotations

import asyncio
from pathlib import Path


def _files_in_checkout(risk_map: dict[str, float], source_root: Path) -> dict[str, float]:
    """The entries whose file is a real file inside ``source_root`` (a link out of it does not count)."""
    real_root = source_root.resolve()
    kept: dict[str, float] = {}
    for rel_path, risk in risk_map.items():
        try:
            candidate = (real_root / rel_path).resolve()
            if candidate.is_relative_to(real_root) and candidate.is_file():
                kept[rel_path] = risk
        except (OSError, ValueError):
            continue
    return kept


async def runtime_risk_for_source(source_root: Path) -> dict[str, float]:
    """Per-file runtime risk, restricted to the files of the selected source's checkout."""
    from code_analysis.src.runtime_risk import build_runtime_risk_map

    risk_map = await build_runtime_risk_map()
    return await asyncio.to_thread(_files_in_checkout, risk_map, source_root)
