# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Import every guard module so its ``declare(...)`` runs, surviving a module-level skip (#18808).

``reach_declarations_test`` imports each guard in turn, catching ``Exception``. A guard that skips
at import raises pytest's ``Skipped``, which is a ``BaseException``. That one escaped the loop,
ended the sweep part way and left a half-initialised ``reach_declarations_test`` in
``sys.modules``, so every guard sorted after it was never imported. A pre-push session that also
collected backend tests got there: the backend conftest stubs chromadb, and
``chromadb_missing_key_serving_where_18820_test`` skips when chromadb is stubbed. Its 12 alphabetic
successors' scopes then went missing from ``reach_scope_claim_17844``.

A skipping module that declares nothing loses nothing, so it is recorded as skipped. One whose
source calls ``declare(`` has lost its declaration, so it counts as an import failure.
"""

from __future__ import annotations

import importlib
import re
from collections.abc import Callable, Iterable
from pathlib import Path

import pytest

# Escaped on purpose: reach_declarations_test greps repo_tests for the call shape, and a bare
# literal of it here would read as a declaration nothing registers.
_DECLARE_CALL = re.compile(r"\bdeclare\(")


def source_declares(path: Path) -> bool:
    """Whether the module at *path* calls ``declare`` (its declarations are lost if it skips)."""
    return bool(_DECLARE_CALL.search(path.read_text(encoding="utf-8")))


def import_guards(
    modules: Iterable[tuple[str, str]],
    *,
    declares: Callable[[str], bool],
    importer: Callable[[str], object] = importlib.import_module,
) -> tuple[dict[str, str], dict[str, str]]:
    """Import each ``(key, dotted)`` module; returns ``(failures, skipped)``, both keyed by *key*."""
    failures: dict[str, str] = {}
    skipped: dict[str, str] = {}
    for key, dotted in modules:
        try:
            importer(dotted)
        except pytest.skip.Exception as exc:
            (failures if declares(key) else skipped)[key] = f"skipped at import: {exc}"
        except Exception as exc:  # noqa: BLE001 - recorded, never discarded
            failures[key] = f"{type(exc).__name__}: {exc}"
    return failures, skipped
