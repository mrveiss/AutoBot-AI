# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The stable identity of a self-model entity, computed identically by the SLM and the backend (#22272).

The SLM keys every entity by kind, normalised name and parent key. The backend links a man-page fact to the
``command`` entity it describes by computing the same key, so the formula lives here once.
"""

from __future__ import annotations

import re
from typing import Optional

from autobot_shared.self_model_constants import ENTITY_KINDS

_WHITESPACE = re.compile(r"\s+")


def _normal(text: str) -> str:
    """Canonical form of a name: trimmed, whitespace collapsed, case-folded."""
    return _WHITESPACE.sub(" ", text.strip()).casefold()


def entity_key(kind: str, name: str, parent_key: Optional[str] = None) -> str:
    """The stable identity of an entity, from its kind, normalised name and parent key."""
    if kind not in ENTITY_KINDS:
        raise ValueError(f"unknown self-model kind {kind!r}")
    base = f"{kind}:{_normal(name)}"
    return f"{parent_key}/{base}" if parent_key else base


def command_key(node_id: str, command: str) -> str:
    """The key of the ``command`` entity named *command* on node *node_id* (the inventory's parent is the node)."""
    return entity_key("command", command, entity_key("node", node_id))
