#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""One parse per source text for the repository's guards (#20814).

Guards commonly run several probes over the same file, and each probe used to
call ``ast.parse`` on the text it was handed. ``concept_forks_17856_test`` is
the measured case: nine probes, so every one of its 3,510 files was parsed nine
times, which took 55 s where one parse per file takes about 3 s.

:func:`parse` is ``ast.parse`` with a bounded memo keyed on the exact arguments,
so back-to-back probes on one text share a single tree.

Why so small, and not one tree per file for the whole session: parsing every
tracked Python file and keeping the trees measured about 1.6 GB, once per pytest
worker, and even a few hundred retained trees slow every later guard through
garbage collection (see ``_MEMO_SIZE``). The repeated-probe win comes from calls
on the same text in quick succession, which a handful of entries covers.

**The returned tree is shared and must be treated as read-only.** A caller that
rewrites nodes (``ast.NodeTransformer``, assigning ``.parent`` or editing
``.body``) would hand its edits to the next caller of the same text, so such
callers keep calling ``ast.parse`` directly. ``parse_cache_test.py`` holds that
line for the guards under ``repo_tests/``.

A ``SyntaxError`` is not memoised. It is raised again on every call, exactly as
``ast.parse`` raises it.
"""

from __future__ import annotations

import ast
import functools

#: Probes on one file run back to back, so the memo only has to remember the
#: last few texts. It is kept this small on purpose: holding 256 trees made a
#: guard that parses each file ONCE (no hits possible) take 210 s instead of 90 s,
#: because the cyclic garbage collector re-walks every retained node on each
#: full collection. Four trees cost nothing measurable and keep every repeat hit.
_MEMO_SIZE = 4


@functools.lru_cache(maxsize=_MEMO_SIZE)
def _parse(source: str | bytes, filename: str, mode: str, type_comments: bool) -> ast.AST:
    return ast.parse(source, filename=filename, mode=mode, type_comments=type_comments)


def parse(
    source: str | bytes,
    filename: str = "<unknown>",
    mode: str = "exec",
    *,
    type_comments: bool = False,
) -> ast.AST:
    """``ast.parse(source, ...)``, memoised on its arguments. The result is shared: read only."""
    return _parse(source, filename, mode, type_comments)


def cache_info() -> functools._CacheInfo:
    """Hit and miss counts, for tests that prove the memo is in use."""
    return _parse.cache_info()
