# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The one store of live agent attributes (#22275).

Health and presence are not registries of their own: the producer of each fact (the health checker,
the presence heartbeat) writes it here, keyed by the unified agent id (#11251), and
``orchestration.agent_record.agent_records`` reads every agent's record from here. This is a leaf
module (no AutoBot imports) so any producer can write without an import cycle.
"""

from __future__ import annotations

import time
from threading import Lock
from typing import Any, Dict

HEALTH_ATTR = "health"
PRESENCE_ATTR = "presence"


class AgentAttributeStore:
    """``agent id -> attribute -> value``; a value written with a ttl vanishes once it lapses."""

    def __init__(self) -> None:
        self._values: Dict[str, Dict[str, tuple[Any, float | None]]] = {}
        self._lock = Lock()

    def set(self, agent_id: str, attr: str, value: Any, ttl_seconds: float | None = None) -> None:
        """Write one attribute of one agent (a producer re-writing it is the heartbeat)."""
        expires = time.time() + ttl_seconds if ttl_seconds is not None else None
        with self._lock:
            self._values.setdefault(agent_id, {})[attr] = (value, expires)

    def clear(self, agent_id: str, attr: str) -> None:
        """Remove one attribute (the producer stopped: a clean shutdown or an unregistered agent)."""
        with self._lock:
            self._values.get(agent_id, {}).pop(attr, None)

    def snapshot(self) -> Dict[str, Dict[str, Any]]:
        """Every agent's live attributes; lapsed ones are pruned here, at read time."""
        now = time.time()
        with self._lock:
            for attrs in self._values.values():
                for attr in [a for a, (_, exp) in attrs.items() if exp is not None and exp <= now]:
                    del attrs[attr]
            return {aid: {a: v for a, (v, _) in attrs.items()} for aid, attrs in self._values.items() if attrs}


_store = AgentAttributeStore()


def get_agent_attribute_store() -> AgentAttributeStore:
    """The process-wide attribute store."""
    return _store
