# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Canonical code-graph node identity (#13470).

Two incompatible schemes existed before this module:
  - ``services/knowledge/code_indexer.py``: ``<file-stem>::<safe_name>`` —
    collides whenever two files share a basename (``utils.py`` in two
    packages produce the same id) and drops the directory entirely.
  - ``api/codebase_analytics/endpoints/call_graph.py``: dotted
    ``<module_path>.<Class>.<name>`` derived from the file's path relative to
    the project root — globally unique per file, matches Python's own import
    naming, and generalises to non-Python sources by dropping the extension.

This module promotes the second scheme to the single canonical one. Callers
that need a node id from a project-relative source path (not an already
computed dotted module path) should go through :func:`module_path_from_rel_path`
first.
"""

from pathlib import Path, PurePosixPath


def module_path_from_rel_path(rel_path: str) -> str:
    """Convert a project-relative source path into a dotted module path.

    ``"services/knowledge/code_indexer.py"`` -> ``"services.knowledge.code_indexer"``
    ``"src/components/Foo.vue"`` -> ``"src.components.Foo"``

    Backslashes are normalised to forward slashes first so a path produced on
    Windows resolves to the same dotted form as one produced on Linux/macOS.
    """
    posix_path = PurePosixPath(rel_path.replace("\\", "/"))
    return posix_path.with_suffix("").as_posix().replace("/", ".")


# Repo root: this file is autobot_shared/code_graph/identity.py.
_PROJECT_ROOT = Path(__file__).resolve().parents[2]


def compute_node_id(name: str, module_path: str, parent_class: str | None = None) -> str:
    """Compute the canonical id for a function/class/method node.

    Module-level definitions: ``<module_path>.<name>``.
    Methods:                  ``<module_path>.<parent_class>.<name>``.

    Only one level of class nesting is tracked (matching the AST visitor in
    ``call_graph.py``, which only ever tracks a single ``current_class``) — a
    method of a nested class collides with one on the outer class. This is a
    pre-existing characteristic of the scheme being converged on, not a
    regression introduced by this module.
    """
    if parent_class:
        return f"{module_path}.{parent_class}.{name}"
    return f"{module_path}.{name}"


def project_relative_path(path: str) -> str:
    """Return *path* relative to the project root, for node-identity purposes (#13470).

    Node ids are computed from a module path, and a module path is only stable if
    every producer agrees where the tree starts. ``code_indexer`` relativises
    against the root it was handed before extracting; the clone fingerprinter
    walks absolute paths from ``rglob``. Same function, two namespaces, joining
    with nothing — so the normalisation belongs here, beside the identity
    scheme it exists to serve, rather than in one caller.

    A path already relative, or outside the project root, is returned unchanged:
    guessing at a root would invent an identity rather than decline to give one.
    """
    candidate = Path(path)
    if not candidate.is_absolute():
        return path
    try:
        return str(candidate.resolve().relative_to(_PROJECT_ROOT))
    except ValueError:
        return path
