# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Every real FastAPI app in the tree strips a 422's echoed payload (#16428 security review).

FastAPI's default `RequestValidationError` handler echoes the submitted value
verbatim (Pydantic v2 puts it in `input`/`ctx`), which leaked a real OAuth
`client_secret` and, on `autobot-slm-backend`, `UserCreate`/`VNCCredentialCreate`
passwords. The fix (`autobot_shared.fastapi_validation_handlers.
register_validation_error_handlers`, or a local duplicate for a server that
cannot import `autobot_shared`) is only as good as every app construction site
actually calling it -- this guard is what keeps a fifth app from missing it the
way the review found the second, third and fourth already had.

**Scope.** Every git-tracked `.py` file, not just `autobot-backend/`: the
review's own gap was in `autobot-slm-backend/` and two files under
`autobot-infrastructure/`, none of which live under `autobot-backend/`.
:data:`REACH` floors what the sweep read, so an empty enumeration fails
instead of passing.

**What counts as a real app.** An assignment whose right-hand side calls
`FastAPI(...)` (`ast.Assign` with a `Call` to a name or attribute named
`FastAPI`) -- catches `app = FastAPI(...)` and `self.app = FastAPI(...)`.
Every test file (`_test.py`/`test_*.py`/anything under a `/tests/` directory)
builds a throwaway app to mount one router in isolation and is excluded by
name, not by an ever-growing per-file list -- there are well over a hundred
of these already. A real app missing the handler fails; a new test file never
does, by construction.

**What is excluded, and why**: see :data:`JUSTIFIED_EXCLUSIONS`. Anything not
in that dict and not a test file must contain a real CALL to
`register_validation_error_handlers` or a real function DEFINITION named
`_validation_error_without_input` -- both matched by AST, not by substring.
A substring match on the import line alone would pass with the actual
registration call removed; that exact bug was caught while writing this.
"""

from __future__ import annotations

import ast
from functools import lru_cache
from pathlib import Path

from repo_tests._paths import repo_root
from repo_tests._reach import declare

from tools.lint._scan_helpers import EmptyEnumeration, tracked_paths

REPO_ROOT = repo_root()

#: Real, non-test FastAPI app-construction sites that do NOT call the shared
#: handler or carry a local duplicate, and why that is reviewed as correct
#: rather than missed.
JUSTIFIED_EXCLUSIONS: dict[str, str] = {
    # A throwaway instance built only to test that a router mounts at the
    # registry's declared prefix -- never run as a server (#16428 review).
    "autobot-infrastructure/shared/scripts/utilities/verify_backend_config.py": (
        "diagnostic script, constructs a disposable app to test router mounting only"
    ),
    # A second, differently-shaped `npu_worker.py` under
    # autobot-infrastructure/shared/scripts/utilities/ -- confirmed NOT the
    # live one (no deploy manifest, installer spec or install script
    # references it; the actual PairRequest/config exposure c0's review
    # found lives only in the Windows package's own npu_worker.py, which is
    # fixed). Tracked separately: #17112.
    "autobot-infrastructure/shared/scripts/utilities/npu_worker.py": "tracked in #17112, not the live copy",
}

#: The marker a server that cannot import autobot_shared carries instead of
#: the real import -- see ai_api_server.py / npu_inference_server.py.
LOCAL_DUPLICATE_MARKER = "_validation_error_without_input"
SHARED_CALL = "register_validation_error_handlers"


def _is_test_file(rel: str) -> bool:
    name = Path(rel).name
    return name.startswith("test_") or name.endswith("_test.py") or name == "conftest.py" or "/tests/" in rel


def _called_names(tree: ast.AST) -> set[str]:
    names = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", None)
        if name:
            names.add(name)
    return names


def _defined_function_names(tree: ast.AST) -> set[str]:
    return {node.name for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}


def _has_the_fix(tree: ast.AST) -> bool:
    """A real CALL to the shared registrar, or a real DEFINITION of the local
    duplicate -- never a bare substring, which an import line or a comment
    satisfies without the app actually being wired (caught this the hard way:
    the first version of this check used `SHARED_CALL in source`, which still
    passed with the registration call commented out, because the import
    statement alone contains that name)."""
    return SHARED_CALL in _called_names(tree) or LOCAL_DUPLICATE_MARKER in _defined_function_names(tree)


def _constructs_fastapi_app(tree: ast.AST) -> bool:
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        call = node.value
        if not isinstance(call, ast.Call):
            continue
        func = call.func
        name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", None)
        if name == "FastAPI":
            return True
    return False


def _candidate_files(root: Path) -> list[str]:
    """Every git-tracked, non-test `.py` file; `[]` for an empty tree."""
    try:
        tracked = tracked_paths(root, "*.py")
    except EmptyEnumeration:
        return []
    return [rel for rel in tracked if not _is_test_file(rel)]


#: Bound at the 3318 non-test tracked .py files measured when this guard was
#: added (5964 tracked .py files total, most of them the *_test.py files this
#: scan excludes by name).
REACH = declare(
    "fastapi-validation-handler",
    discover=_candidate_files,
    floor=3300,
    growth=200,
    skips=0,
    what="git-tracked, non-test python files (candidates for a real FastAPI app construction)",
)


@lru_cache(maxsize=1)
def _real_apps_missing_the_handler() -> dict[str, str]:
    """rel path -> reason, for every real app construction missing the fix."""
    missing: dict[str, str] = {}
    read = 0
    for rel in REACH.examined(REPO_ROOT):
        source = (REPO_ROOT / rel).read_text(encoding="utf-8")
        read += 1
        try:
            tree = ast.parse(source)
        except SyntaxError:
            continue
        if not _constructs_fastapi_app(tree):
            continue
        if _has_the_fix(tree):
            continue
        if rel in JUSTIFIED_EXCLUSIONS:
            continue
        missing[rel] = "constructs FastAPI() but never registers the validation-error handler"
    REACH.completed(read)
    return missing


def test_every_real_fastapi_app_registers_the_validation_error_handler():
    missing = _real_apps_missing_the_handler()
    assert not missing, (
        "these FastAPI apps never strip a 422's echoed payload (#16428) -- call "
        f"{SHARED_CALL}(app) if they can import autobot_shared, duplicate the handler "
        f"if they can't (see ai_api_server.py), or add a reviewed entry to "
        f"JUSTIFIED_EXCLUSIONS with why: {missing}"
    )


def test_every_justified_exclusion_still_constructs_a_real_app():
    """The inverse gap: an exclusion for an app that was fixed (or deleted)
    would hide the day a real regression reintroduces the same file's gap
    under a different guise."""
    stale = []
    for rel in JUSTIFIED_EXCLUSIONS:
        path = REPO_ROOT / rel
        if not path.exists():
            stale.append(f"{rel}: file no longer exists -- drop the exclusion")
            continue
        source = path.read_text(encoding="utf-8")
        if not _constructs_fastapi_app(ast.parse(source)):
            stale.append(f"{rel}: no longer constructs a FastAPI app -- drop the exclusion")
    assert not stale, stale


def test_a_missing_handler_is_detected():
    """Known positive: the detector fires on the construction form it claims
    to see, and an import line ALONE (no call, no local def) is not enough --
    the exact regression a substring check would have missed."""
    tree = ast.parse("from fastapi import FastAPI\nfrom x import register_validation_error_handlers\napp = FastAPI()\n")
    assert _constructs_fastapi_app(tree) is True
    assert _has_the_fix(tree) is False


def test_a_registered_handler_is_not_flagged():
    """Known negative: either form of the real fix satisfies the scan."""
    shared = ast.parse("from fastapi import FastAPI\napp = FastAPI()\nregister_validation_error_handlers(app)\n")
    assert _has_the_fix(shared) is True

    duplicate = ast.parse(
        "from fastapi import FastAPI\napp = FastAPI()\n"
        "async def _validation_error_without_input(request, exc):\n    ...\n"
    )
    assert _has_the_fix(duplicate) is True


def test_a_test_fixtures_throwaway_app_is_not_a_candidate():
    """The bulk case: over a hundred *_test.py files build their own app."""
    assert _is_test_file("autobot-backend/api/secrets_test.py")
    assert _is_test_file("autobot-backend/llc/tests/conftest.py")
    assert _is_test_file("autobot-backend/tests/api/test_canvas.py")
    assert not _is_test_file("autobot-backend/app_factory.py")
