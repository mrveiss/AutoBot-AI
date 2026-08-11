# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Graph-shape fingerprint for cache invalidation (#13509).

`CodeIndexer` invalidates on a whole-file content hash, so a reformat, a
copyright-header touch or a docstring typo re-embeds every node in the file.
Our own PostToolUse hook auto-formats every `.py` we write, which makes that
churn routine rather than rare.

**What this hashes, and why it is not an AST signature.** The first attempt at
this hashed the module's *interface* straight from the AST — top-level function
and class signatures, imports, decorators. It was wrong in a way worth recording,
because the failure was silent and permanent:

- the extractor emits a graph node for **every** definition at **any** depth —
  nested closures, defs inside ``if TYPE_CHECKING:``, try/except import
  fallbacks. A top-level AST scan cannot see them, so renaming a nested
  function left the fingerprint equal while the node set changed.
- the extractor also emits **call edges**, which no signature of the interface
  can capture at all. Rewriting a body from ``os.getenv`` to ``os.environ.get``
  changes the persisted edge set with no interface change whatsoever.

In both cases the fingerprint said "unchanged", the skip path ran, and the new
records were never inserted while the old ones stayed frozen — a stale graph,
served indefinitely, that no later run can heal (the content hash was updated
too, so the file short-circuits before it is ever reconsidered).

The fix is to stop *predicting* what the extractor will produce and hash what it
actually produced. So the invariant is mechanical rather than argued: **if this
fingerprint matches, this file extracted to the same graph, and only the line
numbers moved.** It costs nothing — extraction already runs on every indexed
file, before this is called — and it works for every language the indexer
supports rather than only Python.

**What this deliberately does not cover.** A persisted edge also carries
``target_id``/``resolved``/``origin``/``candidate_count``, which come from
resolving the call against every node id known so far. Those are a function of
*other* files, not of this one, so no fingerprint of this extraction could
predict them either — the caller therefore recomputes resolution on the skip
path rather than trusting the fingerprint for it. Without that, a call to a
then-unknown function would stay unresolved forever once the caller's own shape
settled.

**Fail open.** Every error path returns ``None``, and the caller must treat
``None`` as "re-analyse", never as "unchanged". A false negative costs one
re-embed; a false positive serves a stale graph forever — see ``shape_matches``.
"""

import hashlib
from typing import Any, Optional

from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)

#: Bumping this invalidates every stored fingerprint. Raise it whenever the
#: extractor's node/edge shape or the identity fields below change, otherwise a
#: hash computed under the old rules is silently compared against a new one.
GRAPH_SHAPE_FINGERPRINT_VERSION = 1

#: Persisted node fields that are NOT ``line``. ``line`` is the one field the
#: skip path refreshes, so it is deliberately excluded — including it would make
#: every added blank line a full re-embed, i.e. the bug this fixes.
_NODE_IDENTITY_FIELDS = ("id", "name", "kind", "source_path", "parent")

#: Same for edges. ``line`` becomes ``call_line`` on the persisted record and is
#: likewise refreshed rather than re-embedded.
_EDGE_IDENTITY_FIELDS = ("source", "target_name", "module_path", "current_class", "kind", "source_path")


def _identity(item: Any, fields: tuple) -> tuple:
    """Stable tuple of *fields* read off one extracted node/edge dict."""
    return tuple(repr(item.get(f)) for f in fields)


def compute_graph_shape_fingerprint(extracted: Any) -> Optional[str]:
    """Hash everything the extractor will persist except line numbers.

    Returns ``None`` on anything unexpected — the caller must then re-analyse
    rather than assume the file is unchanged.
    """
    if not isinstance(extracted, dict):
        return None
    nodes = extracted.get("nodes")
    edges = extracted.get("edges")
    if not isinstance(nodes, list) or not isinstance(edges, list):
        return None

    try:
        # Sorted, not document order: moving a definition within a file changes
        # only its line, which the refresh path handles. Ordering by position
        # would spend a full re-embed on a pure reorder.
        node_ids = sorted(_identity(n, _NODE_IDENTITY_FIELDS) for n in nodes)
        edge_ids = sorted(_identity(e, _EDGE_IDENTITY_FIELDS) for e in edges)
        payload = repr((GRAPH_SHAPE_FINGERPRINT_VERSION, node_ids, edge_ids))
        digest = hashlib.sha256(payload.encode("utf-8"), usedforsecurity=False).hexdigest()
        return f"v{GRAPH_SHAPE_FINGERPRINT_VERSION}:{digest}"
    except (AttributeError, TypeError) as exc:
        logger.warning("Graph-shape fingerprint failed, falling back to re-analysis: %s", exc)
        return None


def shape_matches(stored: Any, current: Any) -> bool:
    """True only when both fingerprints are present, versioned alike, and equal.

    Every other outcome is False, which the caller reads as "re-analyse". The
    asymmetry is deliberate: a false negative costs one re-embed, a false
    positive serves a stale graph indefinitely.
    """
    if not stored or not current:
        return False
    if not isinstance(stored, str) or not isinstance(current, str):
        return False
    prefix = f"v{GRAPH_SHAPE_FINGERPRINT_VERSION}:"
    if not stored.startswith(prefix) or not current.startswith(prefix):
        # An unknown or older version is not comparable — re-analyse.
        return False
    return stored == current
