# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Router-level dependencies applied when a registered router is mounted (#16857).

The router registry describes routers as ``(router, prefix, tags, name)``
tuples, which a dozen consumers unpack, so a fifth element would break them.
This mapping is the side channel instead: ``app_factory._register_routers``
looks a router up here by its registry ``name`` and passes the result as
``include_router(..., dependencies=...)``.

Keep entries for cross-cutting controls that must not edit the router's own
module -- e.g. ``api/chat.py`` is at its file-size ceiling.
"""

from __future__ import annotations

from fastapi import Depends
from fastapi.params import Depends as DependsParam

# Imported at module load, not lazily: a broken import must fail startup loudly.
# Lazily, it would raise inside app_factory's per-router try and the whole chat
# router would be skipped with a single log line.
from api.chat_send_rate_limit import enforce_chat_send_rate_limit


def _chat_dependencies() -> list[DependsParam]:
    return [Depends(enforce_chat_send_rate_limit)]


_BY_ROUTER_NAME = {"chat": _chat_dependencies}


def dependencies_for(name: str) -> list[DependsParam]:
    """Dependencies to mount the registry router *name* with; empty when none apply."""
    factory = _BY_ROUTER_NAME.get(name)
    return factory() if factory else []
