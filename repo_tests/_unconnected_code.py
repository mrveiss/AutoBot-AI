# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Everything the unconnected-code gate measures, as one keyed set (#20512).

Keys are ``<kind>:<identifier>``:

``module:<file>``                    a backend module no production code imports or launches
``route:<file>:<METHOD> <path>``     a route decorator no frontend, client or declared prefix reaches
``queue:<file>:<key>``               a Redis list/stream pushed and never read
``table:<name>``                     a SQL table defined and never read or written
``declared:<symbol>=<files>``        a symbol whose ONLY production references (outside the file(s)
                                     defining it) are the listed files -- see :func:`declared_state`

The first four are detected. ``declared`` is a hand-recorded entry for a case no detector can
see (a function whose only caller is itself unused, a service whose only reader is an admin list
route). It stays true only while its stated reference set is exactly the live one, so wiring the
symbol in anywhere new turns the entry stale and the gate asks for it to be removed.
"""

from __future__ import annotations

import re
from pathlib import Path

from repo_tests import _unconnected_modules as modules
from repo_tests import _unconnected_routes as routes
from repo_tests import _unconnected_stores as stores
from repo_tests._unconnected_common import Tree

BASELINE_REL = "repo_tests/unconnected_code_baseline.txt"
KINDS = ("module", "route", "queue", "table", "declared")


def detected(tree: Tree, audit: "routes.Audit") -> set[str]:
    """Every detected unconnected-code key in *tree*."""
    found = {f"module:{rel}" for rel in modules.unconnected(tree)}
    found.update(f"route:{key}" for key in routes.unconnected(tree, audit))
    found.update(f"queue:{key}" for key in stores.unread_queues(tree))
    found.update(f"table:{name}" for name in stores.unread_tables(tree))
    return found


def parse_baseline(text: str) -> dict[str, str]:
    """``{key: issue}`` from the baseline file's tab-separated, ``#``-commented lines."""
    entries: dict[str, str] = {}
    for line in text.splitlines():
        if line.strip() and not line.startswith("#"):
            key, _, issue = line.rpartition("\t")
            entries[key] = issue.strip()
    return entries


def declared_state(tree: Tree, entry: str) -> tuple[list[str], list[str]]:
    """``(defining files, referencing files)`` for a ``declared:<symbol>=<files>`` key.

    A referencing file is a production ``.py`` file, other than a definition, whose text names the
    symbol as a whole word. Docstring and comment mentions count: a stale entry is loud, a
    missed wiring is silent, so the check errs toward stale.
    """
    symbol = entry.removeprefix("declared:").split("=", 1)[0]
    word = re.compile(rf"\b{re.escape(symbol)}\b")
    defn = re.compile(rf"^\s*(?:async\s+)?(?:def|class)\s+{re.escape(symbol)}\b", re.MULTILINE)
    mentioning = [rel for rel in tree.select(".py") if symbol in tree.text(rel)]  # a substring test first: it is cheap
    defining = [rel for rel in mentioning if defn.search(tree.text(rel))]
    refs = [rel for rel in mentioning if rel not in defining and word.search(tree.text(rel))]
    return defining, refs


def declared_allowed(entry: str) -> list[str]:
    """The reference files an entry says are not real consumers."""
    return sorted(p for p in entry.split("=", 1)[1].split(",") if p)


def repo_state(root: Path) -> tuple[Tree, "routes.Audit"]:
    return Tree.of_repo(root), routes.Audit(root)
