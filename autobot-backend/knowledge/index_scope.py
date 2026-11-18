# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The one definition of which search index belongs to the knowledge base (#21048, #17038).

RediSearch indexes are global to the server, so a listing of indexes also holds indexes of other
components. The knowledge base owns exactly the index named by the configuration key below. The KB
reads its name here (``knowledge/base.py``), and the approved knowledge wipe (``services/kb_wipe_redis.py``)
drops only what this module names, never an index that merely exists.
"""

from __future__ import annotations

from typing import Any

#: ``config.manager`` key that names the knowledge base's search index.
KB_INDEX_CONFIG_KEY = "redis.indexes.knowledge_base"
#: The index name when the key is unset.
KB_INDEX_DEFAULT_NAME = "llama_index"


def configured_kb_index_name(config_manager: Any) -> Any:
    """The KB's search index name as *config_manager* reports it."""
    return config_manager.get(KB_INDEX_CONFIG_KEY, KB_INDEX_DEFAULT_NAME)


def kb_index_names() -> tuple[str, ...]:
    """Every search index the knowledge base owns; empty when the configured name is not a usable string."""
    from config.manager import get_config_manager

    name = configured_kb_index_name(get_config_manager())
    return (name,) if isinstance(name, str) and name else ()
