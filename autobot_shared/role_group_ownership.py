# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Which role owns an ansible group's service (#19197).

A DETECTED role token grants a group only while the group's own service is
itself detected on the node. ``redis``/``database`` are one service here:
``deploy-database`` installs redis-stack-server on ``database`` hosts and
``role_redis_active`` fires on either group. So a detected ``slm-database`` or
``postgres`` (postgresql, left behind by a mis-targeted play) must not put a node
into them. Declared roles are never filtered.

Audit of the role->group map for tokens granting a service they do not run:
  slm-database -> redis, database  (postgresql)         filtered here
  postgres     -> database         (postgresql)         filtered here
  chromadb, tts-worker -> ai_stack/aiml/ai; celery, scheduler, autobot_shared ->
  backend/main: already withheld from detection by ``_DECLARED_ONLY_GROUPS``.
"""

import logging
from collections.abc import Callable
from typing import Any

# stdlib logging (as inventory_builder.py / setup_wizard.py): get_logger builds a RotatingFileHandler
# from config values (logging.rotation.max_bytes) that the SLM test harness mocks, so it raises at import.
logger = logging.getLogger(__name__)

GROUP_OWNERS: dict[str, frozenset] = {
    "redis": frozenset({"redis"}),
    "database": frozenset({"redis"}),
}


def normalise_tokens(tokens: Any) -> set[str]:
    return {t.strip().lower() for t in (tokens or []) if t and t.strip()}


def withhold_unowned_groups(groups: set[str], detected_tokens: Any) -> set[str]:
    """Drop owner-gated groups whose owning service is not itself detected."""
    present = normalise_tokens(detected_tokens)
    return {g for g in groups if not GROUP_OWNERS.get(g) or GROUP_OWNERS[g] & present}


_WARNED: set[tuple[str, frozenset]] = set()


def warn_stale_detected_roles(node: Any, groups_of: Callable[[list[str]], set[str]] | None = None) -> list[str]:
    """Log (once per node and stale set) roles a node runs but does not declare; return them.

    ``groups_of`` maps tokens to groups so the log names the groups withheld. Never removes anything (#17038).
    """
    declared = normalise_tokens(getattr(node, "roles", None))
    detected = normalise_tokens(getattr(node, "detected_roles", None))
    stale = sorted(detected - declared)
    node_id = getattr(node, "node_id", "?")
    key = (str(node_id), frozenset(stale))
    if stale and key not in _WARNED:
        _WARNED.add(key)
        withheld = ""
        if groups_of is not None:
            granted = groups_of(stale)
            gated = sorted(granted - withhold_unowned_groups(granted, detected))
            withheld = f"; withheld until their own service runs: {', '.join(gated)}" if gated else ""
        logger.warning(
            "node %s runs roles it does not declare: %s -- assign or remove them%s (#19197)",
            node_id,
            ", ".join(stale),
            withheld,
        )
    return stale


def merge_declared_roles(existing: Any, wanted: list[str]) -> list[str]:
    """Existing declared roles plus any of ``wanted`` they lack; order kept, nothing removed."""
    merged = list(existing or [])
    return merged + [r for r in wanted if r not in merged]


def declared_and_detected(
    node: Any, groups_of: Callable[[list[str]], set[str]] | None = None
) -> tuple[list[str], list[str]]:
    """(declared, detected) role tokens for a node; warns on stale detections."""
    warn_stale_detected_roles(node, groups_of)
    return list(getattr(node, "roles", None) or []), list(getattr(node, "detected_roles", None) or [])


def split_node_role_rows(rows: list, declared: list[str]) -> tuple[list[str], list[str]]:
    """(declared, detected) tokens from NodeRole rows: declared is ``Node.roles`` alone (as the builder reads it).

    A row (manual or auto) whose role is not in ``Node.roles`` is detected, so drift cannot split the two paths.
    """
    return list(declared), [nr.role_name for nr in rows if nr.role_name not in declared]
