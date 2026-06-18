# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Video providers loader — GH#9016.

The video-generation-plugin lives under ``plugins/core-plugins/`` whose directory
name (hyphenated) is not importable as a Python package. This helper resolves the
plugin's ``providers`` module by file path and registers it in ``sys.modules`` so
the API layer can use the provider abstraction without the plugin loader.

``load_video_providers()`` returns the module (with get_provider/provider_names/
ProviderError) or ``None`` when the plugin tree or aiohttp is unavailable, keeping
startup-import-smoke safe.
"""

from __future__ import annotations

import importlib.util
import logging
from pathlib import Path
from types import ModuleType
from typing import Optional

logger = logging.getLogger(__name__)

_MODULE_NAME = "autobot_video_providers"
_REL_PATH = Path("core-plugins") / "video-generation-plugin" / "tools" / "providers.py"

_cached: Optional[ModuleType] = None
_loaded = False


def _candidate_paths() -> list[Path]:
    """Return candidate providers.py locations, most-canonical first."""
    candidates: list[Path] = []
    try:
        from autobot_shared.ssot_config import config as _cfg

        plugins_root = getattr(getattr(_cfg, "path", None), "plugins_path", None)
        if plugins_root:
            candidates.append(Path(plugins_root) / _REL_PATH)
    except Exception:  # pragma: no cover - config optional during smoke
        pass
    # Repo-relative fallback: api/ -> autobot-backend/ -> repo root -> plugins/
    repo_root = Path(__file__).resolve().parents[2]
    candidates.append(repo_root / "plugins" / _REL_PATH)
    candidates.append(Path("plugins") / _REL_PATH)
    return candidates


def load_video_providers() -> Optional[ModuleType]:
    """Load and cache the video providers module, or None if unavailable."""
    global _cached, _loaded
    if _loaded:
        return _cached
    _loaded = True

    import sys

    for path in _candidate_paths():
        try:
            if not path.exists():
                continue
            spec = importlib.util.spec_from_file_location(_MODULE_NAME, path)
            if spec is None or spec.loader is None:
                continue
            module = importlib.util.module_from_spec(spec)
            # Register before exec so dataclasses can resolve the module.
            sys.modules[_MODULE_NAME] = module
            spec.loader.exec_module(module)
            _cached = module
            logger.info("Video providers loaded from %s", path)
            return _cached
        except Exception as exc:  # pragma: no cover - import guard
            logger.warning("Failed loading video providers from %s: %s", path, exc)
            sys.modules.pop(_MODULE_NAME, None)
            continue

    logger.warning("Video providers module not found in any candidate path")
    return None
