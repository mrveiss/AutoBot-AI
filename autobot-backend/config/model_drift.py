#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Startup warning when the deployed config.yaml selects a model the tier map does not (#15502).

The source-of-truth tier map (``autobot_shared.ssot_config``) is the only model authority. A
deployed ``config.yaml`` still carries its own ``selected_model`` values; until the updater
derives them from the tier map, a disagreement is reported once at startup and nothing is
rewritten and no behaviour changes.
"""

import logging  # stdlib: avoids deadlock — config is on the logging-manager init path (GH#7765 pattern)
from typing import Any, Dict, List, Tuple

from autobot_shared.embedding_model import active_embedding_model
from autobot_shared.ssot_config import config

logger = logging.getLogger(__name__)

#: ``(key path, value in the file, value in the source of truth)``.
Drift = Tuple[str, str, str]


def _bare(model: str) -> str:
    """``nomic-embed-text`` and ``nomic-embed-text:latest`` are the same Ollama model."""
    return model.removesuffix(":latest")


def _tier_model(path: List[str]) -> str:
    """The tier-map model a ``backend.llm.*`` provider block should select."""
    return active_embedding_model() if "embedding" in path else config.llm.default_model  # #19377


def _walk(node: Any, path: List[str], out: List[Drift]) -> None:
    if not isinstance(node, dict):
        return
    for key, value in node.items():
        here = [*path, str(key)]
        if key == "selected_model" and "providers" in path and isinstance(value, str) and value:
            expected = _tier_model(path)
            if _bare(value) != _bare(expected):
                out.append((".".join(here), value, expected))
        else:
            _walk(value, here, out)


def selected_model_drift(raw_config: Dict[str, Any]) -> List[Drift]:
    """Every ``backend.llm.*.providers.*.selected_model`` that disagrees with the tier map."""
    found: List[Drift] = []
    _walk(raw_config.get("backend", {}).get("llm", {}), ["backend", "llm"], found)
    return found


def warn_on_selected_model_drift(raw_config: Dict[str, Any]) -> List[Drift]:
    """Log ONE WARNING naming each disagreeing key path, its file value and its tier-map value."""
    drift = selected_model_drift(raw_config)
    if drift:
        logger.warning(
            "Config model drift: config.yaml disagrees with the source-of-truth tier map (%s). "
            "Nothing was changed; the updater derives these values from the tier map.",
            "; ".join(f"{path}: file={file!r} source_of_truth={sot!r}" for path, file, sot in drift),
        )
    return drift
