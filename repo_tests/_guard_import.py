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
import pkgutil
import re
import subprocess
from collections.abc import Callable, Iterable
from pathlib import Path

import pytest

from autobot_shared.paths import scrubbed_git_env

_REPO_TESTS = Path(__file__).resolve().parent
_REPO_ROOT = _REPO_TESTS.parent
#: The sweep that imports every guard; it is not one of them.
_SWEEP_STEM = "reach_declarations_test"

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


def declaring_modules_outside_repo_tests() -> list[str]:
    """Import paths of modules that call `declare(...)` and do not live here.

    Discovered with `git grep`, not enumerated: an enumeration is exactly what
    reach_declarations_test distrusts everywhere else, and a declaration added under a new
    path tomorrow must be swept without anyone remembering to edit a list.

    Why this is needed (#17144, #17298): `declare(...)` registers into a shared
    REGISTRY as an *import side effect*, and the sweep imports only modules
    under `repo_tests/`. A declaration living elsewhere reached the registry
    only when some other test in the same pytest session happened to import its
    module first -- true in CI's whole-suite run, false under
    `pytest repo_tests/`, where the parametrisation dropped from 36 floors to 35
    and reported a clean pass over the smaller set. Not a weaker check: a check
    of a DIFFERENT set, reported identically. It produced a real wrong answer
    today -- a floor re-pinned against a local run that had never examined it.
    """
    out = subprocess.run(
        ["git", "grep", "-lE", r"(^|\s)declare\(", "--", "*.py"],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
        env=scrubbed_git_env(),
    )
    modules = []
    for rel in out.stdout.splitlines():
        if not rel:
            continue
        path = Path(rel)
        if path.parts[0] == "repo_tests":
            continue
        modules.append(".".join(path.with_suffix("").parts))
    return sorted(modules)


def import_every_guard() -> dict[str, str]:
    """Import every guard module so its `declare(...)` runs; returns ``{module: import error}``.

    Import errors are surfaced, not swallowed: a guard that cannot import is a
    guard that is not running, and reach_declarations_test exists to notice exactly that class
    of silence. Lives here, not in that test file, because repo_tests/_reach_roots.py needs
    the same sweep and a shipped module must not import a file .dockerignore strips (#14127).
    """
    inside = [(m.name, f"repo_tests.{m.name}") for m in pkgutil.iter_modules([str(_REPO_TESTS)])]
    inside = [(name, dotted) for name, dotted in inside if not name.startswith("_") and name != _SWEEP_STEM]
    # Declarations that live outside this package (#17144, #17298) are listed because they declare.
    outside = [(dotted, dotted) for dotted in declaring_modules_outside_repo_tests()]
    failures, _skipped = import_guards(
        inside + outside,
        # An outside module (a dotted key) is listed only because it declares.
        declares=lambda key: "." in key or source_declares(_REPO_TESTS / f"{key}.py"),
    )
    return failures
